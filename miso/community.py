"""The Miso community gallery (miso.luigilp.de): browse, download, upload, report.

Uploads are checked by a human before anyone else can see them. The server only gets a
random id of this install (to rate-limit and to show you your own uploads), never your
name, Windows account or anything else from your PC.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QLineEdit, QMenu, QPushButton, QWidget

from . import __version__, media, theme
from .discover import Cancelled, DiscoverPage, Page, Source, fmt_count
from .i18n import tr
from .store import LOCAL_DIR, LibraryItem, Store
from .widgets import ConfirmDialog, human_size

SERVER = os.environ.get("MISO_SERVER", "https://miso.luigilp.de").rstrip("/")
KIND = "community"
DIR = LOCAL_DIR / "community"
MAX_UPLOAD = 15 * 1024 * 1024
USER_AGENT = f"Miso/{__version__} (Windows)"

ERRORS = {
    "rate_limited": tr("Zu viele Anfragen. Bitte versuch es später nochmal."),
    "too_large": tr("Die Datei ist zu groß (höchstens 15 MB)."),
    "bad_image": tr("Das ist kein gültiges Bild (GIF, PNG, APNG, WebP oder JPG, höchstens 4096 Pixel)."),
    "bad_title": tr("Der Titel muss 2 bis 60 Zeichen lang sein."),
    "banned": tr("Von diesem PC können keine Bilder mehr hochgeladen werden."),
    "queue_full": tr("Gerade warten sehr viele Bilder auf Prüfung. Bitte versuch es später nochmal."),
    "duplicate": tr("Dieses Bild wurde schon hochgeladen."),
    "not_found": tr("Nicht mehr verfügbar."),
}

REASONS = {"nsfw": tr("Nicht jugendfrei (NSFW)"), "copyright": tr("Verletzt Urheberrechte"),
           "spam": tr("Spam oder Werbung"), "hate": tr("Hass, Gewalt oder Belästigung"), "other": tr("Etwas anderes")}


class ServerError(RuntimeError):
    pass


def client_token(store: Store) -> str:
    if not store.settings.client_token:
        store.settings.client_token = secrets.token_urlsafe(32)
        store.save()
    return store.settings.client_token


def _request(store: Store, method: str, path: str, body: bytes | None = None, ctype: str = "",
             timeout: int = 25):
    headers = {"User-Agent": USER_AGENT, "X-Miso-Client": client_token(store), "Accept": "application/json"}
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(SERVER + path, data=body, headers=headers, method=method)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            code = json.loads(e.read().decode("utf-8", "replace")).get("error", "")
        except ValueError:
            code = ""
        # nginx answers limits itself (HTML, no JSON)
        code = code or {404: "not_found", 413: "too_large", 429: "rate_limited"}.get(e.code, "")
        raise ServerError(ERRORS.get(code, tr("Fehler vom Server ({a0})", a0=e.code))) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ServerError(tr("Der Miso-Server ist gerade nicht erreichbar.")) from None


def _json(store: Store, method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    with _request(store, method, path, body, "application/json" if body else "") as r:
        return json.loads(r.read().decode("utf-8"))


def _multipart(fields: dict[str, str], file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----miso" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    safe = "".join(c for c in filename if c.isalnum() or c in "._-") or "image"
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{safe}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


@dataclass
class CommunityItem:
    id: str
    title: str
    thumb_url: str
    size: int
    downloads: int
    frames: int
    ext: str
    status: str = "approved"     # approved | pending | rejected (only in "my uploads")
    mine: bool = False


def _item(d: dict, mine: bool = False) -> CommunityItem:
    return CommunityItem(str(d["id"]), str(d.get("title", "")), SERVER + str(d.get("thumb", "")),
                         int(d.get("size") or 0), int(d.get("downloads") or 0), int(d.get("frames") or 1),
                         str(d.get("ext") or "gif"), str(d.get("status") or "approved"), mine)


# ======================================================================================
class _UploadSignals(QObject):
    done = Signal(str)
    failed = Signal(str)


class _Task(QRunnable):
    """Runs `fn` in the thread pool; reports back on the GUI thread."""

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _UploadSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn() or "")
        except Exception as e:
            try:
                self.signals.failed.emit(str(e))
            except RuntimeError:
                pass


class MisoSource(Source):
    key = "miso"
    label = "Miso"
    default_sort = "trend"
    search_placeholder = tr("Miso durchsuchen …")

    def __init__(self, store: Store) -> None:
        self.store = store
        self.sorts = {"trend": tr("Im Trend"), "popular": tr("Beliebt"), "new": tr("Neu"), "mine": tr("Meine Uploads")}
        self.pool = QThreadPool()
        self._tasks: list = []

    # -- browsing ---------------------------------------------------------------------
    def browse(self, sort: str, search: str, page: int) -> Page:
        if sort == "mine":
            data = _json(self.store, "GET", "/api/mine")
            items = [_item(d, mine=True) for d in data.get("items", [])]
            if search:
                items = [i for i in items if search.lower() in i.title.lower()]
            return Page(items, 1, 1, len(items))
        q = urllib.parse.urlencode({"sort": sort, "q": search, "page": page})
        data = _json(self.store, "GET", f"/api/items?{q}")
        return Page([_item(d) for d in data.get("items", [])], int(data.get("page", page)),
                    int(data.get("pages", 1)), int(data.get("total", 0)))

    def subtitle(self, page: Page, sort: str, search: str) -> str:
        what = f"„{search}“" if search else self.sorts.get(sort, "")
        if sort == "mine":
            return tr("Deine Uploads  ·  {a0}", a0=fmt_count(page.total))
        return tr("Miso Community  ·  {a0} Bilder  ·  {a1}", a0=fmt_count(page.total), a1=what)

    def meta(self, item: CommunityItem) -> str:
        n = item.downloads
        dl = tr("1 Download") if n == 1 else tr("{a0} Downloads", a0=fmt_count(n))
        return f"{dl}  ·  {human_size(item.size)}"

    def badge(self, item: CommunityItem) -> str:
        if not item.mine:
            return ""
        return {"pending": tr("Wartet auf Freigabe"), "rejected": tr("Abgelehnt")}.get(item.status, tr("Veröffentlicht"))

    def can_download(self, item: CommunityItem) -> bool:
        return item.status == "approved"

    def empty_text(self, sort: str, search: str) -> str:
        if sort == "mine":
            return tr("Du hast noch nichts hochgeladen. Teile ein Bild über „Hochladen“.")
        if search:
            return tr("Keine Treffer.")
        return tr("Hier ist noch nichts. Lade das erste Bild hoch!")

    # -- library ------------------------------------------------------------------------
    def find(self, store: Store, item_id: str) -> LibraryItem | None:
        return next((i for i in store.library if i.kind == KIND and i.extra.get("community_id") == item_id), None)

    def download(self, item: CommunityItem, cancel: threading.Event, progress, status) -> tuple[str, list[str]]:
        folder = DIR / item.id
        ext = item.ext if item.ext in ("gif", "png", "webp", "jpg") else "gif"
        tmp = DIR / f".{item.id}.part.{ext}"    # real extension: the content check looks at it too
        DIR.mkdir(parents=True, exist_ok=True)
        try:
            with _request(self.store, "GET", f"/api/items/{item.id}/file", timeout=40) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or item.size or 0)
                done = 0
                while chunk := r.read(1 << 16):
                    if cancel.is_set():
                        raise Cancelled()
                    done += len(chunk)
                    if done > MAX_UPLOAD + 1024 * 1024:
                        raise ServerError(tr("Datei ist größer als erwartet"))
                    f.write(chunk)
                    progress(done, total)
            if not media.is_real_image(tmp):
                raise ServerError(tr("Die Datei ist kein Bild"))
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
            target = folder / f"{item.id}.{ext}"
            tmp.replace(target)
            return str(target), [str(target)]
        finally:
            tmp.unlink(missing_ok=True)

    def make_library_item(self, item: CommunityItem, main: str, files: list[str]) -> LibraryItem:
        return LibraryItem(path=main, title=item.title, kind=KIND, extra={"community_id": item.id})

    # -- menus & header -------------------------------------------------------------
    def extend_menu(self, page: DiscoverPage, menu: QMenu, item: CommunityItem) -> None:
        if item.mine:
            menu.addSeparator()
            menu.addAction(tr("Upload zurückziehen …"), lambda: self.withdraw(page, item))
        elif item.status == "approved":
            menu.addSeparator()
            menu.addAction(tr("Melden …"), lambda: report(page.window(), self.store, item.id, item.title))

    def header_widgets(self, page: DiscoverPage) -> list[QWidget]:
        b = QPushButton(tr("  Hochladen"))
        b.setObjectName("Primary")
        b.setIcon(theme.glyph_icon(theme.Icon.UPLOAD, theme.ON_ACCENT))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: pick_and_share(page.window(), self.store, on_done=lambda: _after_upload(page)))
        return [b]

    def withdraw(self, page: DiscoverPage, item: CommunityItem) -> None:
        win = page.window()
        if not ConfirmDialog.ask(win, tr("„{a0}“ zurückziehen?", a0=item.title),
                                 tr("Das Bild wird vom Miso-Server gelöscht. Wer es schon heruntergeladen hat, behält es."),
                                 tr("Zurückziehen")):
            return
        run(lambda: _json(self.store, "DELETE", f"/api/mine/{item.id}") and "",
            lambda _: (win.toast(tr("„{a0}“ zurückgezogen", a0=item.title), "ok"), page.update_card(item)),
            lambda msg: win.toast(msg, "error"))


def _after_upload(page: DiscoverPage) -> None:
    if page.sort == "mine":
        page.reload()


# -- background helper ----------------------------------------------------------------------
_running: list = []


def run(fn, on_done, on_failed) -> None:
    task = _Task(fn)
    task.signals.done.connect(on_done)
    task.signals.failed.connect(on_failed)
    _running.append(task.signals)
    task.signals.done.connect(lambda *_: _running.remove(task.signals) if task.signals in _running else None)
    task.signals.failed.connect(lambda *_: _running.remove(task.signals) if task.signals in _running else None)
    QThreadPool.globalInstance().start(task)


# -- uploading ------------------------------------------------------------------------------
def accept_terms(win, store: Store) -> bool:
    if store.settings.community_terms:
        return True
    text = tr("Bevor du etwas teilst:\n\n"
              "• Lade nur Bilder hoch, die du selbst gemacht hast oder teilen darfst.\n"
              "• Nichts Anstößiges, keine Gewalt, keine echten Personen ohne deren Einverständnis.\n"
              "• Jedes Bild wird vor der Veröffentlichung geprüft und kann jederzeit entfernt werden.\n\n"
              "Datenschutz: Miso schickt das Bild, den Titel und eine zufällige ID dieser Installation an "
              "miso.luigilp.de. Deine IP-Adresse wird nur verschlüsselt (gehasht) gespeichert, um Missbrauch "
              "zu verhindern. Abgelehnte Bilder werden nach 30 Tagen gelöscht, eigene Uploads kannst du "
              "jederzeit zurückziehen.")
    if ConfirmDialog.ask(win, tr("Bilder mit der Community teilen"), text, tr("Verstanden"), danger=False):
        store.settings.community_terms = True
        store.save()
        return True
    return False


def pick_and_share(win, store: Store, on_done=None) -> None:
    if not accept_terms(win, store):
        return
    path, _ = QFileDialog.getOpenFileName(win, tr("Bild zum Teilen auswählen"), str(Path.home() / "Pictures"),
                                          tr("Bilder (*.gif *.png *.apng *.webp *.jpg *.jpeg)"))
    if path:
        share(win, store, path, Path(path).stem.replace("_", " "), on_done)


def share(win, store: Store, path: str, title: str, on_done=None) -> None:
    """Ask for title + rights, then upload `path` in the background."""
    if not accept_terms(win, store):
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        win.toast(tr("Datei nicht gefunden"), "error")
        return
    if size > MAX_UPLOAD:
        win.toast(ERRORS["too_large"], "error")
        return
    if not media.is_real_image(path):
        win.toast(ERRORS["bad_image"], "error")
        return
    rights = QCheckBox(tr("Ich darf dieses Bild teilen und es ist nicht anstößig."))
    rights.setStyleSheet("background:transparent; margin-top:6px;")
    dlg = ConfirmDialog(win, tr("Auf Miso teilen"),
                        tr("Gib dem Bild einen kurzen Titel. Nach der Prüfung sieht es jeder unter „Entdecken“."),
                        tr("Hochladen"), danger=False, field=title[:60], extra=[rights])
    dlg.edit.setMaxLength(60)
    dlg.confirm_button.setEnabled(False)

    def check() -> None:
        dlg.confirm_button.setEnabled(rights.isChecked() and 2 <= len(dlg.edit.text().strip()) <= 60)
    rights.toggled.connect(check)
    dlg.edit.textChanged.connect(check)
    dlg.edit.returnPressed.disconnect()
    dlg.edit.returnPressed.connect(lambda: dlg.accept() if dlg.confirm_button.isEnabled() else None)
    if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
        return
    final_title = dlg.edit.text().strip()

    win.toast(tr("„{a0}“ wird hochgeladen …", a0=final_title))
    run(lambda: upload_file(store, path, final_title),
        lambda t: (win.toast(tr("„{a0}“ hochgeladen. Es erscheint, sobald es geprüft wurde.", a0=t), "ok"),
                   on_done() if on_done else None),
        lambda msg: win.toast(tr("Hochladen fehlgeschlagen: {a0}", a0=msg), "error"))


def upload_file(store: Store, path: str, title: str) -> str:
    """Send one image to the server (worker thread). Returns the title; raises ServerError."""
    data = Path(path).read_bytes()
    body, ctype = _multipart({"title": title, "rights": "1"}, "file", Path(path).name, data)
    with _request(store, "POST", "/api/upload", body, ctype, timeout=90) as r:
        r.read()
    return title


# -- reporting ------------------------------------------------------------------------------
def report(win, store: Store, item_id: str, title: str) -> None:
    combo = QComboBox()
    for key, label in REASONS.items():
        combo.addItem(label, key)
    note = QLineEdit()
    note.setPlaceholderText(tr("Details (optional)"))
    note.setMaxLength(500)
    dlg = ConfirmDialog(win, tr("„{a0}“ melden", a0=title),
                        tr("Was stimmt mit diesem Bild nicht? Die Meldung geht anonym an die Moderation."),
                        tr("Melden"), danger=True, extra=[combo, note])
    if dlg.exec() != ConfirmDialog.DialogCode.Accepted:
        return
    payload = {"reason": combo.currentData(), "note": note.text().strip()}
    run(lambda: _json(store, "POST", f"/api/items/{item_id}/report", payload) and "",
        lambda _: win.toast(tr("Danke! Die Meldung wurde gesendet."), "ok"),
        lambda msg: win.toast(tr("Melden fehlgeschlagen: {a0}", a0=msg), "error"))


# -- library extras -------------------------------------------------------------------------
class LibraryHooks:
    """Community filter, label and menu entries for the library page."""

    filter = (KIND, "Community")

    def __init__(self, store: Store) -> None:
        self.store = store

    def matches(self, item: LibraryItem) -> bool:
        return item.kind == KIND

    def label(self, item: LibraryItem) -> str | None:
        return "Community" if item.kind == KIND else None

    def extend_menu(self, menu: QMenu, item: LibraryItem) -> None:
        win = menu.parentWidget().window() if menu.parentWidget() else None
        if win is None:
            return
        if item.kind == KIND and item.extra.get("community_id"):
            menu.addAction(tr("Melden …"), lambda: report(win, self.store, item.extra["community_id"], item.title))
        elif item.kind in ("upload", "local") and not item.is_pack:
            menu.addAction(tr("Auf Miso teilen …"), lambda: share(win, self.store, item.path, item.title))
