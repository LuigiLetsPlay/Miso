"""The Discover page: browse online galleries ("sources"), download into the library.

A source is a small object (see `Source`) that knows how to list, describe and download
its items. The page shows a switch in the top right as soon as there is more than one.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget

from . import i18n, theme
from .i18n import tr
from .pages import SkeletonCard, page_header, scroll_wrap
from .store import LibraryItem, Store
from .widgets import CardGrid, IconButton, ImageLoader, MediaCard


@dataclass
class Page:
    items: list
    page: int
    pages: int
    total: int


class Cancelled(Exception):
    pass


class Source:
    """Base class. Items need at least `.id`, `.title` and `.thumb_url`."""

    key = ""
    label = ""
    sorts: dict[str, str] = {}
    default_sort = ""
    search_placeholder = ""

    def browse(self, sort: str, search: str, page: int) -> Page:          # worker thread
        raise NotImplementedError

    def download(self, item, cancel: threading.Event, progress, status) -> tuple[str, list[str]]:  # worker thread
        """Fetch the item; return (main file, all image files). Raise Cancelled when `cancel` is set."""
        raise NotImplementedError

    def make_library_item(self, item, main: str, files: list[str]) -> LibraryItem:
        raise NotImplementedError

    def find(self, store: Store, item_id: str) -> LibraryItem | None:
        return None

    def subtitle(self, page: Page, sort: str, search: str) -> str:
        return ""

    def meta(self, item) -> str:
        return ""

    def badge(self, item) -> str:
        """Extra state shown on the card (e.g. waiting for review). Empty = none."""
        return ""

    def can_download(self, item) -> bool:
        return True

    def extend_menu(self, page: "DiscoverPage", menu: QMenu, item) -> None:
        pass

    def header_widgets(self, page: "DiscoverPage") -> list[QWidget]:
        return []

    def empty_text(self, sort: str, search: str) -> str:
        return tr("Keine Treffer.")


def _drop(layout, widget: QWidget) -> None:
    """Take a widget out right away (deleteLater alone leaves it in the layout until later)."""
    layout.removeWidget(widget)
    widget.hide()
    widget.deleteLater()


def fmt_count(n: int) -> str:
    return f"{n:,}".replace(",", "." if i18n.LANG == "de" else ",")


# ======================================================================================
class _JobSignals(QObject):
    progress = Signal(str, int, int)
    status = Signal(str, str)
    finished = Signal(str, str, object)
    failed = Signal(str, str)


class _DownloadJob(QRunnable):
    def __init__(self, job_id: str, source: Source, item, cancel: threading.Event) -> None:
        super().__init__()
        self.job_id, self.source, self.item, self.cancel = job_id, source, item, cancel
        self.signals = _JobSignals()

    def run(self) -> None:
        s, jid = self.signals, self.job_id
        try:
            main, files = self.source.download(self.item, self.cancel,
                                               lambda done, total: s.progress.emit(jid, done, total),
                                               lambda text: s.status.emit(jid, text))
            s.finished.emit(jid, main, files)
        except Cancelled:
            s.failed.emit(jid, tr("Abgebrochen"))
        except RuntimeError as e:
            try:
                s.failed.emit(jid, str(e))
            except RuntimeError:
                pass  # app is shutting down and the signal object is gone
        except Exception as e:
            s.failed.emit(jid, str(e))


class DownloadManager(QObject):
    """Runs downloads of any source in the background and files them into the library."""

    progress = Signal(str, float)       # job id, 0..1
    status = Signal(str, str)
    finished = Signal(str, object)      # job id, LibraryItem
    failed = Signal(str, str)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.active: dict[str, tuple] = {}     # job id -> (source, item, cancel event, fraction)
        self._signals: dict[str, _JobSignals] = {}

    @staticmethod
    def job_id(source: Source, item_id: str) -> str:
        return f"{source.key}:{item_id}"

    def is_downloading(self, job_id: str) -> bool:
        return job_id in self.active

    def fraction(self, job_id: str) -> float:
        entry = self.active.get(job_id)
        return entry[3] if entry else 0.0

    def start(self, source: Source, item) -> None:
        jid = self.job_id(source, item.id)
        if jid in self.active:
            return
        cancel = threading.Event()
        self.active[jid] = (source, item, cancel, 0.0)
        job = _DownloadJob(jid, source, item, cancel)
        job.signals.progress.connect(self._on_progress)
        job.signals.status.connect(self.status)
        job.signals.finished.connect(self._on_finished)
        job.signals.failed.connect(self._on_failed)
        self._signals[jid] = job.signals
        self.pool.start(job)
        self.progress.emit(jid, 0.0)

    def cancel(self, job_id: str) -> None:
        entry = self.active.get(job_id)
        if entry:
            entry[2].set()

    def cancel_source(self, source: Source) -> None:
        for jid, entry in self.active.items():
            if entry[0] is source:
                entry[2].set()

    def cancel_all(self) -> None:
        for entry in self.active.values():
            entry[2].set()

    def _on_progress(self, jid: str, done: int, total: int) -> None:
        if jid in self.active:
            source, item, ev, _ = self.active[jid]
            frac = done / total if total else 0.0
            self.active[jid] = (source, item, ev, frac)
            self.progress.emit(jid, frac)

    def _on_finished(self, jid: str, main: str, files: list) -> None:
        source, item, _, _ = self.active.pop(jid)
        self._signals.pop(jid, None)
        lib = self.store.add_library(source.make_library_item(item, main, files))
        self.finished.emit(jid, lib)

    def _on_failed(self, jid: str, message: str) -> None:
        self.active.pop(jid, None)
        self._signals.pop(jid, None)
        self.failed.emit(jid, message)


# ======================================================================================
class _BrowseSignals(QObject):
    done = Signal(object, int)
    failed = Signal(str, int)


class _BrowseJob(QRunnable):
    def __init__(self, source: Source, sort: str, search: str, page: int, request: int) -> None:
        super().__init__()
        self.source, self.args, self.request = source, (sort, search, page), request
        self.signals = _BrowseSignals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.source.browse(*self.args), self.request)
        except Exception as e:
            try:
                self.signals.failed.emit(str(e), self.request)
            except RuntimeError:
                pass


class DiscoverPage(QWidget):
    place_requested = Signal(object)      # LibraryItem

    def __init__(self, store: Store, downloads: DownloadManager, loader: ImageLoader, toast) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.store, self.downloads, self.loader, self.toast = store, downloads, loader, toast
        self.sources: list[Source] = []
        self.source: Source | None = None
        self._state: dict[str, tuple[str, str]] = {}   # source key -> (sort, search)
        self.sort = ""
        self.search = ""
        self.page = 0
        self.total_pages = 1
        self.loading = False
        self.request = 0
        self.cards: dict[str, MediaCard] = {}
        self._jobs = []
        self._pool = QThreadPool(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 8, 28, 0)
        root.setSpacing(18)

        top = QHBoxLayout()
        header, self.subtitle = page_header(tr("Entdecken"))
        top.addWidget(header)
        top.addStretch()
        self.header_box = QHBoxLayout()            # source-specific buttons (e.g. upload)
        self.header_box.setSpacing(10)
        top.addLayout(self.header_box)
        self.source_seg = QWidget()
        self.source_seg.setObjectName("SegBar")
        self.source_lay = QHBoxLayout(self.source_seg)
        self.source_lay.setContentsMargins(4, 4, 4, 4)
        self.source_lay.setSpacing(2)
        self.source_group = QButtonGroup(self)
        self.source_seg.hide()
        top.addSpacing(6)
        top.addWidget(self.source_seg, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(top)

        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search_box = QLineEdit()
        self.search_box.addAction(theme.glyph_icon(theme.Icon.SEARCH, theme.MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(260)
        self.search_box.setMaximumWidth(420)
        self._debounce = QTimer(self, singleShot=True, interval=450, timeout=self._apply_search)
        self.search_box.textChanged.connect(lambda: self._debounce.start())
        self.search_box.returnPressed.connect(self._apply_search)
        bar.addWidget(self.search_box, 1)
        seg = QWidget()
        seg.setObjectName("SegBar")
        self.sort_lay = QHBoxLayout(seg)
        self.sort_lay.setContentsMargins(4, 4, 4, 4)
        self.sort_lay.setSpacing(2)
        self.sort_group = QButtonGroup(self)
        bar.addWidget(seg)
        bar.addStretch()
        refresh = IconButton(theme.Icon.REFRESH, tr("Neu laden"), size=38)
        refresh.clicked.connect(self.reload)
        bar.addWidget(refresh)
        root.addLayout(bar)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 4, 8, 24)
        cl.setSpacing(16)
        self.grid = CardGrid()
        cl.addWidget(self.grid)
        self.footer = QLabel("")
        self.footer.setObjectName("Muted")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setWordWrap(True)
        self.footer.setMinimumHeight(40)
        cl.addWidget(self.footer)
        self.retry = QPushButton(tr("Erneut versuchen"))
        self.retry.hide()
        self.retry.clicked.connect(self._load_next)
        cl.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignCenter)
        cl.addStretch()
        self.scroll = scroll_wrap(content)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.scroll, 1)

        self._skeleton_timer = QTimer(self, interval=50, timeout=self._pulse)
        self._skeleton_t = 0

        downloads.progress.connect(self._on_progress)
        downloads.status.connect(self._on_status)
        downloads.finished.connect(lambda jid, _: self._refresh_job(jid))
        downloads.failed.connect(self._on_failed)
        store.library_changed.connect(self._refresh_all_cards)
        store.filter_changed.connect(self.apply_filter)

    # -- sources --------------------------------------------------------------------------
    def add_source(self, source: Source, index: int | None = None) -> None:
        if source in self.sources:
            return
        self.sources.insert(len(self.sources) if index is None else index, source)
        self._build_source_switch()
        if self.source is None:
            self.set_source(source)

    def remove_source(self, source: Source) -> None:
        if source not in self.sources:
            return
        self.downloads.cancel_source(source)
        self.sources.remove(source)
        self._state.pop(source.key, None)
        self._build_source_switch()
        if self.source is source:
            self.source = None
            if self.sources:
                self.set_source(self.sources[0])

    def _build_source_switch(self) -> None:
        for b in self.source_group.buttons():
            self.source_group.removeButton(b)
            _drop(self.source_lay, b)
        for src in self.sources:
            b = QPushButton(src.label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(src is self.source)
            b.clicked.connect(lambda _=False, s=src: self.set_source(s))
            self.source_group.addButton(b)
            self.source_lay.addWidget(b)
        self.source_seg.setVisible(len(self.sources) > 1)

    def set_source(self, source: Source) -> None:
        if self.source is not None:
            self._state[self.source.key] = (self.sort, self.search)
        self.source = source
        self.sort, self.search = self._state.get(source.key, (source.default_sort, ""))
        for b, src in zip(self.source_group.buttons(), self.sources):
            b.setChecked(src is source)
        # header buttons
        while self.header_box.count():
            w = self.header_box.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        for w in source.header_widgets(self):
            self.header_box.addWidget(w, 0, Qt.AlignmentFlag.AlignBottom)
        # sort buttons
        for b in self.sort_group.buttons():
            self.sort_group.removeButton(b)
            _drop(self.sort_lay, b)
        for key, label in source.sorts.items():
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(key == self.sort)
            b.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self.sort_group.addButton(b)
            self.sort_lay.addWidget(b)
        self.search_box.blockSignals(True)
        self.search_box.setText(self.search)
        self.search_box.setPlaceholderText(source.search_placeholder or tr("Durchsuchen …"))
        self.search_box.blockSignals(False)
        self.page = 0
        if self.isVisible():
            self.reload()
        else:
            self.cards.clear()
            self.grid.clear()

    # -- loading ----------------------------------------------------------------------------
    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.page == 0 and not self.loading:
            self.reload()

    def reload(self) -> None:
        if self.source is None:
            return
        self.request += 1
        self.page = 0
        self.total_pages = 1
        self.loading = False
        self.cards.clear()
        self.grid.clear()
        self.footer.setText("")
        self.scroll.verticalScrollBar().setValue(0)
        for _ in range(12):
            self.grid.add(SkeletonCard())
        self.grid.relayout()
        self._skeleton_timer.start()
        self._load_next()

    def _pulse(self) -> None:
        self._skeleton_t += 1
        SkeletonCard.phase = (math.sin(self._skeleton_t / 6) + 1) / 2
        for c in self.grid.cards:
            if isinstance(c, SkeletonCard):
                c.update()

    def _set_sort(self, key: str) -> None:
        if key != self.sort or self.search:
            self.sort = key
            if self.search:
                self.search_box.blockSignals(True)
                self.search_box.clear()
                self.search_box.blockSignals(False)
                self.search = ""
            self.reload()

    def _apply_search(self) -> None:
        self._debounce.stop()
        text = self.search_box.text().strip()
        if text != self.search:
            self.search = text
            self.reload()

    def _load_next(self) -> None:
        if self.loading or self.page >= self.total_pages or self.source is None:
            return
        self.loading = True
        self.retry.hide()
        if self.page > 0:
            self.footer.setText(tr("Lädt mehr …"))
        job = _BrowseJob(self.source, self.sort, self.search, self.page + 1, self.request)
        sig = job.signals
        sig.done.connect(self._on_page)
        sig.failed.connect(self._on_page_failed)
        # keep the signal object alive until it delivered, then let it go
        sig.done.connect(lambda *_, s=sig: QTimer.singleShot(0, lambda: self._drop_job(s)))
        sig.failed.connect(lambda *_, s=sig: QTimer.singleShot(0, lambda: self._drop_job(s)))
        self._jobs.append(sig)
        self._pool.start(job)

    def _drop_job(self, sig) -> None:
        if sig in self._jobs:
            self._jobs.remove(sig)

    def _on_page(self, page: Page, request: int) -> None:
        if request != self.request:
            return
        self.loading = False
        if self.page == 0:
            self._skeleton_timer.stop()
            self.grid.clear()
        self.page = page.page
        self.total_pages = page.pages
        self.subtitle.setText(self.source.subtitle(page, self.sort, self.search))
        added = 0
        for item in page.items:
            if item.id in self.cards:
                continue
            card = MediaCard(item, item.title, self.source.meta(item), self.loader, item.thumb_url)
            card.setToolTip(item.title)
            card.clicked.connect(self._on_card_clicked)
            card.context.connect(self._on_card_menu)
            self.cards[item.id] = card
            self.grid.add(card)
            card.animate_in(min(added * 30, 450))
            added += 1
            self.loader.request_url(item.thumb_url)
            self._refresh_card(item.id)
        self.apply_filter()

    def apply_filter(self) -> None:
        """Hide NSFW cards (by title) without dropping them, so toggling back is instant."""
        hidden = 0
        for card in self.cards.values():
            hide = self.store.hidden(card.payload.title)
            hidden += hide
            card.setHidden(hide)
        self.grid.relayout()
        note = "  ·  " + tr("{a0} NSFW ausgeblendet", a0=hidden) if hidden else ""
        if self.loading and self.page == 0:
            return
        if len(self.cards) == hidden and self.page >= self.total_pages:
            empty = self.source.empty_text(self.sort, self.search) if self.source else tr("Keine Treffer.")
            self.footer.setText(empty + note)
        elif self.page >= self.total_pages:
            self.footer.setText(tr("Das war alles") + note)
        else:
            self.footer.setText(note.strip(" ·"))
        QTimer.singleShot(50, self._on_scroll)

    def _on_page_failed(self, message: str, request: int) -> None:
        if request != self.request:
            return
        self.loading = False
        self._skeleton_timer.stop()
        if self.page == 0:
            self.grid.clear()
        self.footer.setText(tr("Konnte nicht geladen werden.\n{a0}", a0=message))
        self.retry.show()

    def _on_scroll(self, *_) -> None:
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() - sb.value() < 700:
            self._load_next()

    # -- cards ------------------------------------------------------------------------------
    def _jid(self, item_id: str) -> str:
        return DownloadManager.job_id(self.source, item_id)

    def _refresh_job(self, jid: str) -> None:
        key, _, item_id = jid.partition(":")
        if self.source is not None and key == self.source.key:
            self._refresh_card(item_id)

    def _refresh_card(self, item_id: str) -> None:
        card = self.cards.get(item_id)
        if not card or self.source is None:
            return
        item = card.payload
        jid = self._jid(item_id)
        extra = self.source.badge(item)
        if self.downloads.is_downloading(jid):
            card.set_state(progress=self.downloads.fraction(jid), status=card.status)
        elif self.source.find(self.store, item_id):
            card.set_state(tr("Platzieren"), theme.Icon.PIN, badge=extra or tr("In Bibliothek"))
        elif not self.source.can_download(item):
            card.set_state("", "", badge=extra)
        else:
            card.set_state(tr("Herunterladen"), theme.Icon.DOWNLOAD, badge=extra)

    def _refresh_all_cards(self) -> None:
        for i in self.cards:
            self._refresh_card(i)

    def update_card(self, item) -> None:
        """A source changed an item (e.g. after deleting it): drop or refresh its card."""
        card = self.cards.pop(item.id, None)
        if card is not None:
            self.grid.remove(card) if hasattr(self.grid, "remove") else card.hide()
            self.grid.relayout()

    def start_download(self, item) -> None:
        self.downloads.start(self.source, item)

    def _on_card_clicked(self, item) -> None:
        lib = self.source.find(self.store, item.id)
        if lib and lib.is_pack:
            self.window().open_pack(lib)
        elif lib:
            self.place_requested.emit(lib)
        elif self.source.can_download(item) and not self.downloads.is_downloading(self._jid(item.id)):
            self.start_download(item)

    def _on_card_menu(self, item, pos: QPoint) -> None:
        menu = QMenu(self)
        lib = self.source.find(self.store, item.id)
        jid = self._jid(item.id)
        if lib and lib.is_pack:
            menu.addAction(tr("Pack öffnen …"), lambda: self.window().open_pack(lib))
        elif lib:
            menu.addAction(tr("Auf dem Bildschirm platzieren"), lambda: self.place_requested.emit(lib))
        elif self.downloads.is_downloading(jid):
            menu.addAction(tr("Download abbrechen"), lambda: self.downloads.cancel(jid))
        elif self.source.can_download(item):
            menu.addAction(tr("Herunterladen"), lambda: self.start_download(item))
        self.source.extend_menu(self, menu, item)
        if lib:
            menu.addSeparator()
            menu.addAction(tr("Aus Bibliothek löschen"), lambda: self.window().delete_library_item(lib))
        if not menu.isEmpty():
            menu.exec(pos)

    def _on_progress(self, jid: str, frac: float) -> None:
        card = self._card_for(jid)
        if card:
            card.set_state(progress=frac, status=card.status)

    def _on_status(self, jid: str, text: str) -> None:
        card = self._card_for(jid)
        if card:
            card.status = text.rstrip(" …")
            card.update()

    def _card_for(self, jid: str) -> MediaCard | None:
        key, _, item_id = jid.partition(":")
        if self.source is not None and key == self.source.key:
            return self.cards.get(item_id)
        return None

    def _on_failed(self, jid: str, message: str) -> None:
        card = self._card_for(jid)
        if card:
            card.status = ""
        self._refresh_job(jid)
        if message != tr("Abgebrochen"):
            self.toast(tr("Download fehlgeschlagen: {a0}", a0=message), "error")
