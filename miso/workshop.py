"""Steam Workshop browsing (parsed from the community page) and download queue."""
from __future__ import annotations

import html
import json
import re
import shutil
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import media
from .steam.depot import Cancelled, WorkshopDownloader
from .store import WORKSHOP_DIR, LibraryItem, Store

APP_ID = 3474900
BROWSE_URL = "https://steamcommunity.com/workshop/browse/"
ITEM_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"
PER_PAGE = 30

SORTS = {
    "trend": "Im Trend",
    "totaluniquesubscribers": "Beliebt",
    "mostrecent": "Neu",
    "toprated": "Top bewertet",
}


@dataclass
class WorkshopItem:
    id: str
    title: str
    description: str
    preview_url: str
    manifest: int
    size: int
    subscriptions: int
    favorited: int
    tags: list[str]

    @property
    def thumb_url(self) -> str:
        sep = "&" if "?" in self.preview_url else "?"
        return f"{self.preview_url}{sep}imw=320&imh=320&ima=fit&impolicy=Letterbox&letterbox=false"

    @property
    def page_url(self) -> str:
        return ITEM_URL.format(self.id)


@dataclass
class BrowsePage:
    items: list[WorkshopItem]
    page: int
    total_pages: int
    total: int


def browse(sort: str = "trend", search: str = "", page: int = 1) -> BrowsePage:
    params = {"appid": APP_ID, "section": "readytouseitems", "p": page, "numperpage": PER_PAGE,
              "browsesort": "textsearch" if search else sort, "actualsort": sort}
    if search:
        params["searchtext"] = search
    else:
        params["days"] = -1 if sort in ("toprated", "totaluniquesubscribers") else 7
    url = BROWSE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Miso/1.0",
        "Cookie": "Steam_Language=english",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        page_html = r.read().decode("utf-8", "replace")

    m = re.search(r'<script type="application/json" id="valve-ssr-data"[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        raise RuntimeError("Workshop-Seite hat ein unbekanntes Format")
    ssr = json.loads(m.group(1))
    queries = json.loads(ssr["renderContext"]["queryData"])["queries"]
    data = next((q["state"]["data"] for q in queries if q["queryKey"][0] == "workshop_browse"), None)
    if not data:
        raise RuntimeError("Keine Workshop-Daten gefunden")

    items = []
    for r in data.get("results", []):
        if not r.get("hcontent_file"):
            continue
        items.append(WorkshopItem(
            id=str(r["publishedfileid"]),
            title=html.unescape(r.get("title") or "Ohne Titel"),
            description=html.unescape(r.get("short_description") or ""),
            preview_url=r.get("preview_url", ""),
            manifest=int(r["hcontent_file"]),
            size=int(r.get("file_size") or 0),
            subscriptions=int(r.get("subscriptions") or 0),
            favorited=int(r.get("favorited") or 0),
            tags=[t.get("display_name") or t.get("tag") for t in r.get("tags", [])],
        ))
    return BrowsePage(items, int(data.get("current_page", page)), int(data.get("total_pages", 1)),
                      int(data.get("total_count", len(items))))


# -- Qt plumbing -------------------------------------------------------------

class _BrowseSignals(QObject):
    done = Signal(object, int)
    failed = Signal(str, int)


class BrowseJob(QRunnable):
    def __init__(self, sort: str, search: str, page: int, request: int) -> None:
        super().__init__()
        self.args = (sort, search, page)
        self.request = request
        self.signals = _BrowseSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(browse(*self.args), self.request)
        except Exception as e:
            self.signals.failed.emit(str(e), self.request)


class _DownloadSignals(QObject):
    progress = Signal(str, int, int)
    status = Signal(str, str)
    finished = Signal(str, str)
    failed = Signal(str, str)


class DownloadJob(QRunnable):
    def __init__(self, item: WorkshopItem, cancel: threading.Event) -> None:
        super().__init__()
        self.item = item
        self.cancel = cancel
        self.signals = _DownloadSignals()

    def run(self) -> None:
        try:
            self._run()
        except RuntimeError:
            pass  # app is shutting down and the signal object is gone

    def _run(self) -> None:
        item = self.item
        target = WORKSHOP_DIR / item.id
        tmp = WORKSHOP_DIR / f".{item.id}.part"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            dl = WorkshopDownloader(
                APP_ID,
                log=lambda text: self.signals.status.emit(item.id, text),
                progress=lambda done, total: self.signals.progress.emit(item.id, done, total),
                cancel_event=self.cancel,
            )
            files = dl.download(item.manifest, tmp)
            shutil.rmtree(target, ignore_errors=True)
            tmp.rename(target)
            files = [target / f.relative_to(tmp) for f in files]
            playable = [f for f in files if media.is_supported(f.name)]
            if not playable:
                raise RuntimeError("Item enthält kein Bild/GIF")
            main = max(playable, key=lambda f: f.stat().st_size)
            self.signals.finished.emit(item.id, str(main))
        except Cancelled:
            shutil.rmtree(tmp, ignore_errors=True)
            self.signals.failed.emit(item.id, "Abgebrochen")
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            self.signals.failed.emit(item.id, str(e))


class DownloadManager(QObject):
    """Runs workshop downloads in the background and files them into the library."""

    progress = Signal(str, float)       # id, 0..1
    status = Signal(str, str)
    finished = Signal(str, object)      # id, LibraryItem
    failed = Signal(str, str)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.active: dict[str, tuple[WorkshopItem, threading.Event, float]] = {}
        self._signals: dict[str, _DownloadSignals] = {}  # keep alive until delivered

    def is_downloading(self, item_id: str) -> bool:
        return item_id in self.active

    def fraction(self, item_id: str) -> float:
        entry = self.active.get(item_id)
        return entry[2] if entry else 0.0

    def start(self, item: WorkshopItem) -> None:
        if item.id in self.active:
            return
        cancel = threading.Event()
        self.active[item.id] = (item, cancel, 0.0)
        job = DownloadJob(item, cancel)
        job.signals.progress.connect(self._on_progress)
        job.signals.status.connect(self.status)
        job.signals.finished.connect(self._on_finished)
        job.signals.failed.connect(self._on_failed)
        self._signals[item.id] = job.signals
        self.pool.start(job)
        self.progress.emit(item.id, 0.0)

    def cancel(self, item_id: str) -> None:
        entry = self.active.get(item_id)
        if entry:
            entry[1].set()

    def cancel_all(self) -> None:
        for _, ev, _ in self.active.values():
            ev.set()

    def _on_progress(self, item_id: str, done: int, total: int) -> None:
        if item_id in self.active:
            item, ev, _ = self.active[item_id]
            frac = done / total if total else 0.0
            self.active[item_id] = (item, ev, frac)
            self.progress.emit(item_id, frac)

    def _on_finished(self, item_id: str, path: str) -> None:
        item, _, _ = self.active.pop(item_id)
        self._signals.pop(item_id, None)
        lib =self.store.add_library(LibraryItem(path=path, title=item.title, kind="workshop",
                                                 workshop_id=item.id, preview_url=item.preview_url))
        self.finished.emit(item_id, lib)

    def _on_failed(self, item_id: str, message: str) -> None:
        self.active.pop(item_id, None)
        self._signals.pop(item_id, None)
        self.failed.emit(item_id, message)


def delete_workshop_files(item: LibraryItem) -> None:
    if item.kind == "workshop" and item.workshop_id:
        folder = WORKSHOP_DIR / item.workshop_id
        if folder.is_dir() and folder.resolve().parent == WORKSHOP_DIR.resolve():
            shutil.rmtree(folder, ignore_errors=True)
