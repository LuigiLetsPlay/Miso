"""The four main pages: Workshop, Library, Active overlays, Settings."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, QRectF, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMenu, QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from . import __version__, hotkeys, i18n, theme, workshop
from .store import CACHE_DIR, UPLOAD_DIR, WORKSHOP_DIR, LibraryItem, OverlayState, Store
from .widgets import (CardGrid, ConfirmDialog, IconButton, ImageLoader, MediaCard, ToggleSwitch, fade_in_window, human_ago,
                      human_count, human_size, rounded)
from .i18n import tr


def page_header(title: str, subtitle: str = "") -> tuple[QWidget, QLabel]:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    s = QLabel(subtitle)
    s.setObjectName("Muted")
    lay.addWidget(t)
    lay.addWidget(s)
    return w, s


def scroll_wrap(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content.setObjectName("ScrollContent")
    area.setWidget(content)
    return area


class EmptyState(QWidget):
    def __init__(self, glyph: str, title: str, text: str, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        icon = QLabel(glyph)
        icon.setFont(theme.icon_font(34))
        icon.setStyleSheet(f"color:{theme.DIM};")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setStyleSheet("font-size:13pt; font-weight:700;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel(text)
        self.text.setObjectName("Muted")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setFixedWidth(420)
        self.text.setMinimumHeight(self.text.heightForWidth(420))
        lay.addSpacing(40)
        lay.addWidget(icon)
        lay.addWidget(t)
        lay.addWidget(self.text, 0, Qt.AlignmentFlag.AlignCenter)


class SkeletonCard(QWidget):
    phase = 0.0

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        a = int(18 + 14 * SkeletonCard.phase)
        c = QColor(255, 255, 255, a)
        p.fillPath(rounded(QRectF(0, 4, w, w), 16), c)
        p.fillPath(rounded(QRectF(2, w + 18, w * .7, 12), 6), c)
        p.fillPath(rounded(QRectF(2, w + 38, w * .4, 10), 5), c)
        p.end()


# ======================================================================================
class WorkshopPage(QWidget):
    place_requested = Signal(object)      # LibraryItem

    def __init__(self, store: Store, downloads: workshop.DownloadManager, loader: ImageLoader,
                 toast) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.store, self.downloads, self.loader, self.toast = store, downloads, loader, toast
        self.sort = "trend"
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

        header, self.subtitle = page_header(tr("Entdecken"), "AnimaEngine Steam Workshop")
        root.addWidget(header)

        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("Workshop durchsuchen …"))
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
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(2)
        self.sort_group = QButtonGroup(self)
        for key, label in workshop.SORTS.items():
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(key == self.sort)
            b.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self.sort_group.addButton(b)
            seg_lay.addWidget(b)
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
        downloads.finished.connect(lambda i, _: self._refresh_card(i))
        downloads.failed.connect(self._on_failed)
        store.library_changed.connect(self._refresh_all_cards)
        store.filter_changed.connect(self.apply_filter)

    # -- loading ------------------------------------------------------------
    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.page == 0 and not self.loading:
            self.reload()

    def reload(self) -> None:
        self.request += 1
        self.page = 0
        self.total_pages = 1
        self.loading = False
        self.cards.clear()
        self.grid.clear()
        self.scroll.verticalScrollBar().setValue(0)
        for _ in range(12):
            self.grid.add(SkeletonCard())
        self.grid.relayout()
        self._skeleton_timer.start()
        self._load_next()

    def _pulse(self) -> None:
        import math
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
        if self.loading or self.page >= self.total_pages:
            return
        self.loading = True
        self.retry.hide()
        if self.page > 0:
            self.footer.setText(tr("Lädt mehr …"))
        job = workshop.BrowseJob(self.sort, self.search, self.page + 1, self.request)
        job.signals.done.connect(self._on_page)
        job.signals.failed.connect(self._on_page_failed)
        self._jobs.append(job.signals)
        self._pool.start(job)

    def _on_page(self, page: workshop.BrowsePage, request: int) -> None:
        if request != self.request:
            return
        self.loading = False
        if self.page == 0:
            self._skeleton_timer.stop()
            self.grid.clear()
        self.page = page.page
        self.total_pages = page.total_pages
        what = f"„{self.search}“" if self.search else workshop.SORTS[self.sort]
        total = f"{page.total:,}".replace(",", "." if i18n.LANG == "de" else ",")
        self.subtitle.setText(f"AnimaEngine Steam Workshop  ·  {total} Items  ·  {what}")
        added = 0
        for item in page.items:
            if item.id in self.cards:
                continue
            meta = tr("{a0} Abos  ·  {a1}", a0=human_count(item.subscriptions), a1=human_size(item.size))
            card = MediaCard(item, item.title, meta, self.loader, item.thumb_url)
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
        if len(self.cards) == hidden and self.page >= self.total_pages:
            self.footer.setText(tr("Keine Treffer.") + note)
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
        self.footer.setText(tr("Workshop konnte nicht geladen werden.\n{a0}", a0=message))
        self.retry.show()

    def _on_scroll(self, *_) -> None:
        sb = self.scroll.verticalScrollBar()
        if sb.maximum() - sb.value() < 700:
            self._load_next()

    # -- cards ----------------------------------------------------------------
    def _refresh_card(self, item_id: str) -> None:
        card = self.cards.get(item_id)
        if not card:
            return
        if self.downloads.is_downloading(item_id):
            card.set_state(progress=self.downloads.fraction(item_id), status=card.status)
        elif self.store.workshop_item(item_id):
            card.set_state(tr("Platzieren"), theme.Icon.PIN, badge=tr("In Bibliothek"))
        else:
            card.set_state(tr("Herunterladen"), theme.Icon.DOWNLOAD)

    def _refresh_all_cards(self) -> None:
        for i in self.cards:
            self._refresh_card(i)

    def _on_card_clicked(self, item: workshop.WorkshopItem) -> None:
        lib = self.store.workshop_item(item.id)
        if lib:
            self.place_requested.emit(lib)
        elif not self.downloads.is_downloading(item.id):
            self.downloads.start(item)

    def _on_card_menu(self, item: workshop.WorkshopItem, pos: QPoint) -> None:
        menu = QMenu(self)
        lib = self.store.workshop_item(item.id)
        if lib:
            menu.addAction(tr("Auf dem Bildschirm platzieren"), lambda: self.place_requested.emit(lib))
        elif self.downloads.is_downloading(item.id):
            menu.addAction(tr("Download abbrechen"), lambda: self.downloads.cancel(item.id))
        else:
            menu.addAction(tr("Herunterladen"), lambda: self.downloads.start(item))
        menu.addAction(tr("Im Steam Workshop ansehen"), lambda: QDesktopServices.openUrl(QUrl(item.page_url)))
        if lib:
            menu.addSeparator()
            menu.addAction(tr("Aus Bibliothek löschen"), lambda: self.window().delete_library_item(lib))
        menu.exec(pos)

    def _on_progress(self, item_id: str, frac: float) -> None:
        card = self.cards.get(item_id)
        if card:
            card.set_state(progress=frac, status=card.status)

    def _on_status(self, item_id: str, text: str) -> None:
        card = self.cards.get(item_id)
        if card:
            card.status = text.rstrip(" …")
            card.update()

    def _on_failed(self, item_id: str, message: str) -> None:
        card = self.cards.get(item_id)
        if card:
            card.status = ""
        self._refresh_card(item_id)
        if message != tr("Abgebrochen"):
            self.toast(tr("Download fehlgeschlagen: {a0}", a0=message), "error")


# ======================================================================================
def pack_entry(pack: LibraryItem, path: str) -> LibraryItem:
    """A single image of a pack, shaped like a library item so it can be placed."""
    stem = Path(path).stem.replace("_", " ").strip()
    return LibraryItem(path=path, title=f"{pack.title} · {stem}", kind=pack.kind,
                       workshop_id=pack.workshop_id)


class PackDialog(QDialog):
    """Browse the images of a workshop pack and place any of them."""

    def __init__(self, parent: QWidget, pack: LibraryItem, loader: ImageLoader, store: Store) -> None:
        super().__init__(parent)
        self.pack, self.loader, self.store = pack, loader, store
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        card = QFrame()
        card.setObjectName("DialogCard")
        card.setStyleSheet(f"QFrame#DialogCard {{ background:{theme.SURFACE_2}; border:1px solid #33333A;"
                           f" border-radius:16px; }}")
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 20, 18)
        lay.setSpacing(14)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(pack.title)
        title.setStyleSheet("font-size:14pt; font-weight:600; background:transparent;")
        sub = QLabel(tr("{a0} Bilder  ·  Klicken zum Platzieren, mehrere nacheinander möglich", a0=len(pack.files)))
        sub.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
        col.addWidget(title)
        col.addWidget(sub)
        head.addLayout(col, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Im Pack suchen …"))
        self.search.addAction(theme.glyph_icon(theme.Icon.SEARCH, theme.MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._filter)
        head.addWidget(self.search, 0, Qt.AlignmentFlag.AlignTop)
        close = QPushButton(tr("Fertig"))
        close.setObjectName("Primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        head.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 8, 8)
        self.grid = CardGrid()
        self.grid.MIN_W = 140
        cl.addWidget(self.grid)
        cl.addStretch()
        lay.addWidget(scroll_wrap(content), 1)

        for i, path in enumerate(pack.files):
            entry = pack_entry(pack, path)
            self.loader.request_file(path)
            c = MediaCard(entry, Path(path).stem.replace("_", " "), human_size(entry.size()), loader,
                          "file:" + path)
            c.set_state(tr("Platzieren"), theme.Icon.PIN)
            c.setToolTip(Path(path).name)
            c.clicked.connect(self._place)
            self.grid.add(c)
            c.animate_in(min(i * 18, 400))
        screen = parent.screen().availableGeometry() if parent else None
        w = min(980, int(screen.width() * 0.8)) if screen else 900
        h = min(700, int(screen.height() * 0.8)) if screen else 640
        self.resize(w, h)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for c in self.grid.cards:
            c.setHidden(bool(text) and text not in c.title.lower())
        self.grid.relayout()

    def _place(self, entry: LibraryItem) -> None:
        self.parentWidget().place(entry)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        parent = self.parentWidget()
        if parent and parent.isVisible():
            self.move(parent.geometry().center() - self.rect().center())
        fade_in_window(self)
        QTimer.singleShot(0, self.grid.relayout)


# ======================================================================================
class UploadZone(QWidget):
    """Big dashed drop/click target at the top of the library."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.fillPath(rounded(r, 14), QColor(theme.SURFACE_2 if self._hover else theme.SURFACE))
        pen = QPen(QColor(255, 255, 255, 70 if self._hover else 38), 1.4)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.drawRoundedRect(r, 14, 14)
        circle = QRectF(22, r.center().y() - 22, 44, 44)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SURFACE_3))
        p.drawEllipse(circle)
        p.setPen(QColor(theme.TEXT))
        p.setFont(theme.icon_font(13))
        p.drawText(circle, Qt.AlignmentFlag.AlignCenter, theme.Icon.UPLOAD)
        p.setFont(theme.ui_font(10.5, theme.QFont.Weight.DemiBold))
        p.drawText(QRectF(84, r.top() + 22, r.width() - 100, 22), Qt.AlignmentFlag.AlignVCenter,
                   tr("Eigene Bilder hochladen"))
        p.setPen(QColor(theme.MUTED))
        p.setFont(theme.ui_font(9))
        p.drawText(QRectF(84, r.top() + 46, r.width() - 100, 20), Qt.AlignmentFlag.AlignVCenter,
                   tr("Klicken, Dateien reinziehen, Bilder direkt aus dem Browser ziehen oder Strg + V  ·  GIF, PNG, APNG, WebP, JPG"))
        p.end()


LIB_FILTERS = {"all": tr("Alle"), "fav": tr("Favoriten"), "workshop": "Workshop", "own": tr("Eigene")}
LIB_SORTS = {"recent": tr("Zuletzt benutzt"), "added": tr("Neu hinzugefügt"), "name": "Name", "size": tr("Größe")}


class LibraryPage(QWidget):
    place_requested = Signal(object)

    def __init__(self, store: Store, loader: ImageLoader, active_paths) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.store, self.loader, self.active_paths = store, loader, active_paths
        self.filter = "all"
        self.query = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 8, 28, 0)
        root.setSpacing(16)

        top = QHBoxLayout()
        header, self.subtitle = page_header(tr("Bibliothek"))
        top.addWidget(header)
        top.addStretch()
        add = QPushButton(tr("  Hochladen"))
        add.setObjectName("Primary")
        add.setIcon(theme.glyph_icon(theme.Icon.UPLOAD, theme.ON_ACCENT))
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(self.pick_files)
        top.addWidget(add, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(top)

        zone = UploadZone()
        zone.clicked.connect(self.pick_files)
        root.addWidget(zone)

        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Bibliothek durchsuchen …"))
        self.search.addAction(theme.glyph_icon(theme.Icon.SEARCH, theme.MUTED), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._set_query)
        bar.addWidget(self.search, 1)
        seg = QWidget()
        seg.setObjectName("SegBar")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(2)
        group = QButtonGroup(self)
        for key, label in LIB_FILTERS.items():
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(key == self.filter)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            group.addButton(b)
            seg_lay.addWidget(b)
        bar.addWidget(seg)
        bar.addStretch()
        self.sort_btn = QPushButton()
        self.sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_btn.clicked.connect(self._sort_menu)
        bar.addWidget(self.sort_btn)
        root.addLayout(bar)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 4, 8, 24)
        self.grid = CardGrid()
        cl.addWidget(self.grid)
        self.empty = EmptyState(theme.Icon.LIBRARY, tr("Noch leer hier"),
                                tr("Lade etwas im Workshop herunter oder lade eigene Bilder hoch."))
        cl.addWidget(self.empty)
        cl.addStretch()
        root.addWidget(scroll_wrap(content), 1)

        store.library_changed.connect(self.rebuild)
        store.overlays_changed.connect(self._update_badges)
        store.filter_changed.connect(self.rebuild)
        self.rebuild()

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("Bilder oder GIFs hochladen"), str(Path.home() / "Pictures"),
                                                tr("Bilder (*.gif *.png *.apng *.webp *.jpg *.jpeg *.bmp)"))
        if files:
            self.window().import_files(files)

    def _set_query(self, text: str) -> None:
        self.query = text.strip().lower()
        self.rebuild(animate=True)

    def _set_filter(self, key: str) -> None:
        self.filter = key
        self.rebuild(animate=True)

    def _sort_menu(self) -> None:
        menu = QMenu(self)
        for key, label in LIB_SORTS.items():
            mark = "●  " if key == self.store.settings.library_sort else "     "
            menu.addAction(mark + label, lambda k=key: self._set_sort(k))
        menu.exec(self.sort_btn.mapToGlobal(QPoint(0, self.sort_btn.height() + 4)))

    def _set_sort(self, key: str) -> None:
        self.store.settings.library_sort = key
        self.store.save()
        self.rebuild(animate=True)

    def _visible_items(self) -> tuple[list[LibraryItem], int]:
        items, nsfw = [], 0
        for item in self.store.library:
            if self.store.hidden(item.title):
                nsfw += 1
                continue
            if self.filter == "fav" and not item.favorite:
                continue
            if self.filter == "workshop" and item.kind != "workshop":
                continue
            if self.filter == "own" and item.kind == "workshop":
                continue
            if self.query and self.query not in item.title.lower():
                continue
            items.append(item)
        sort = self.store.settings.library_sort
        keys = {"recent": lambda i: -i.used, "added": lambda i: -i.added,
                "name": lambda i: i.title.lower(), "size": lambda i: -i.size()}
        items.sort(key=keys.get(sort, keys["recent"]))
        items.sort(key=lambda i: not i.favorite)  # favourites first, stable within
        return items, nsfw

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.rebuild(animate=True)

    def rebuild(self, animate: bool = False) -> None:
        """Rebuild the grid. Cards animate in when `animate`, otherwise only newly added ones do."""
        previous = getattr(self, "_keys", set())
        self._keys = set()
        n = 0
        self.grid.clear()
        self.sort_btn.setText(tr("Sortieren: {a0}  ▾", a0=LIB_SORTS.get(self.store.settings.library_sort, '')))
        items, nsfw = self._visible_items()
        for item in items:
            kind = {"workshop": "Workshop", "upload": tr("Eigenes")}.get(item.kind, tr("Verknüpft"))
            if item.is_pack:
                kind = tr("Pack · {a0} Bilder", a0=len(item.files))
            meta = f"{kind}  ·  {human_size(item.size())}  ·  {human_ago(item.used)}"
            key = item.preview_url and workshop.WorkshopItem(item.workshop_id, "", "", item.preview_url, 0, 0, 0, 0, []).thumb_url
            if key:
                self.loader.request_url(key)
            else:
                key = "file:" + item.path
                self.loader.request_file(item.path)
            card = MediaCard(item, item.title, meta, self.loader, key)
            card.setToolTip(item.title)
            card.favorite = item.favorite
            card.clicked.connect(self._open)
            card.context.connect(self._menu)
            card.favorite_clicked.connect(lambda it: self.store.set_favorite(it, not it.favorite))
            self.grid.add(card)
            self._keys.add(item.key)
            if self.isVisible() and (animate or item.key not in previous):
                card.animate_in(min(n * 30, 450))
                n += 1
        self.grid.relayout()
        total = len(self.store.library) - nsfw
        parts = [f"{total} {tr("Element") if total == 1 else tr("Elemente")}",
                 human_size(sum(i.size() for i in self.store.library if i.deletable))]
        if nsfw:
            parts.append(tr("{a0} NSFW ausgeblendet", a0=nsfw))
        self.subtitle.setText("  ·  ".join(parts))
        self.empty.setVisible(not items)
        if total and not items:
            self.empty.text.setText(tr("Keine Treffer für diesen Filter."))
        else:
            self.empty.text.setText(tr("Lade etwas im Workshop herunter oder lade eigene Bilder hoch."))
        self._update_badges()

    def _update_badges(self) -> None:
        active = self.active_paths()
        for card in self.grid.cards:
            item: LibraryItem = card.payload
            count = sum(active.count(p) for p in item.all_paths)
            card.set_state(tr("Platzieren"), theme.Icon.PIN, badge=tr("Aktiv") + (f" ×{count}" if count > 1 else "") if count else "")

    def _open(self, item: LibraryItem) -> None:
        if item.is_pack:
            PackDialog(self.window(), item, self.loader, self.store).exec()
        else:
            self.place_requested.emit(item)

    def _rename(self, item: LibraryItem) -> None:
        name = ConfirmDialog.ask_text(self.window(), tr("Bild umbenennen"), item.title)
        if name:
            self.store.rename_item(item, name)

    def _menu(self, item: LibraryItem, pos: QPoint) -> None:
        menu = QMenu(self)
        if item.is_pack:
            menu.addAction(tr("Pack öffnen …"), lambda: self._open(item))
        else:
            menu.addAction(tr("Auf dem Bildschirm platzieren"), lambda: self.place_requested.emit(item))
        menu.addAction(tr("Aus Favoriten entfernen") if item.favorite else tr("Favorisieren"),
                       lambda: self.store.set_favorite(item, not item.favorite))
        if item.kind != "workshop":
            menu.addAction(tr("Umbenennen …"), lambda: self._rename(item))
        menu.addAction(tr("Im Explorer zeigen"), lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(Path(item.path).parent))))
        if item.workshop_id:
            menu.addAction(tr("Im Steam Workshop ansehen"), lambda: QDesktopServices.openUrl(
                QUrl(workshop.ITEM_URL.format(item.workshop_id))))
        menu.addSeparator()
        menu.addAction(tr("Löschen …"), lambda: self.window().delete_library_item(item))
        menu.exec(pos)


# ======================================================================================
class OverlayRow(QFrame):
    def __init__(self, state: OverlayState, loader: ImageLoader, manager) -> None:
        super().__init__()
        self.state, self.manager = state, manager
        self.setObjectName("Row")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"QFrame#Row {{ background:{theme.SURFACE}; border:1px solid {theme.BORDER};"
                           f" border-radius:16px; }} QFrame#Row:hover {{ border-color:#34344C; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 14, 12)
        lay.setSpacing(14)

        grip = QLabel(theme.Icon.GRIP)
        grip.setFont(theme.icon_font(10))
        grip.setStyleSheet(f"color:{theme.DIM}; background:transparent;")
        grip.setToolTip(tr("Ziehen zum Sortieren"))
        grip.setCursor(Qt.CursorShape.SizeAllCursor)
        grip.setFixedWidth(16)
        grip.mousePressEvent = self._grip_press
        grip.mouseMoveEvent = self._grip_move
        lay.addWidget(grip)
        self._press: QPoint | None = None
        self.thumb = QLabel()
        self.thumb.setFixedSize(60, 60)
        lay.addWidget(self.thumb)
        self.loader = loader
        loader.loaded.connect(self._thumb_loaded)
        loader.request_file(state.path)
        self._set_thumb(loader.get("file:" + state.path))

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(state.title)
        title.setStyleSheet("font-weight:600; font-size:10.5pt;")
        title.setMaximumWidth(360)
        self.meta = QLabel()
        self.meta.setObjectName("Muted")
        text.addStretch()
        text.addWidget(title)
        text.addWidget(self.meta)
        text.addStretch()
        lay.addLayout(text, 1)

        op = QLabel(theme.Icon.BRIGHTNESS)
        op.setFont(theme.icon_font(9))
        op.setObjectName("Muted")
        op.setToolTip(tr("Deckkraft"))
        lay.addWidget(op)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 100)
        self.slider.setValue(int(state.opacity * 100))
        self.slider.setFixedWidth(130)
        self.slider.setToolTip(tr("Deckkraft"))
        self.slider.valueChanged.connect(self._opacity)
        lay.addWidget(self.slider)
        self.pct = QLabel(f"{int(state.opacity * 100)} %")
        self.pct.setObjectName("Muted")
        self.pct.setFixedWidth(40)
        lay.addWidget(self.pct)

        self.eye = IconButton(theme.Icon.EYE if state.visible else theme.Icon.EYE_OFF, tr("Ein-/Ausblenden"))
        self.eye.clicked.connect(self._toggle_visible)
        center = IconButton(theme.Icon.CENTER, tr("In die Bildschirmmitte"))
        center.clicked.connect(lambda: manager.center(state))
        delete = IconButton(theme.Icon.DELETE, tr("Entfernen"), danger_hover=True)
        delete.clicked.connect(lambda: manager.remove(state))
        for b in (self.eye, center, delete):
            lay.addWidget(b)
        self.refresh()

    def _set_thumb(self, pm: QPixmap | None) -> None:
        out = QPixmap(60 * 2, 60 * 2)
        out.setDevicePixelRatio(2)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(0, 0, 60, 60)
        p.fillPath(rounded(r, 12), QColor(theme.SURFACE_3))
        if pm:
            from .widgets import draw_cover
            draw_cover(p, pm, r, 12)
        p.end()
        self.thumb.setPixmap(out)

    def _thumb_loaded(self, key: str, pm: QPixmap) -> None:
        if key == "file:" + self.state.path:
            self._set_thumb(pm)

    def refresh(self) -> None:
        s = self.state
        self.meta.setText(f"{s.w} × {s.h} px  ·  Position {s.x}, {s.y}" + ("" if s.visible else "  ·  " + tr("ausgeblendet")))
        self.eye.glyph = theme.Icon.EYE if s.visible else theme.Icon.EYE_OFF
        self.eye.update()

    def _opacity(self, v: int) -> None:
        self.pct.setText(f"{v} %")
        self.manager.set_opacity(self.state, v / 100)

    def _grip_press(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()

    def _grip_move(self, e) -> None:
        moved = self._press is not None and \
            (e.globalPosition().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()
        if moved:
            self._press = None
            start_drag(self, OVERLAY_MIME, self.state.uid, self)

    def _toggle_visible(self) -> None:
        self.manager.set_visible(self.state, not self.state.visible)
        self.refresh()


PROFILE_MIME = "application/x-miso-profile"
OVERLAY_MIME = "application/x-miso-overlay"


def start_drag(source: QWidget, mime_type: str, uid: str, preview: QWidget) -> None:
    """Begin an internal drag carrying `uid`, showing a faded snapshot of `preview`."""
    mime = QMimeData()
    mime.setData(mime_type, uid.encode())
    drag = QDrag(source)
    drag.setMimeData(mime)
    snap = preview.grab()
    faded = QPixmap(snap.size())
    faded.setDevicePixelRatio(snap.devicePixelRatio())
    faded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(faded)
    painter.setOpacity(0.85)
    painter.drawPixmap(0, 0, snap)
    painter.end()
    drag.setPixmap(faded)
    drag.setHotSpot(preview.mapFromGlobal(QCursor.pos()))
    drag.exec(Qt.DropAction.MoveAction)


class DropLine(QWidget):
    """Thin accent line showing where a dragged item will land."""

    def __init__(self, parent: QWidget, vertical: bool) -> None:
        super().__init__(parent)
        self.vertical = vertical
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def show_at(self, pos: int, start: int, length: int) -> None:
        if self.vertical:
            self.setGeometry(pos - 1, start, 3, length)
        else:
            self.setGeometry(start, pos - 1, length, 3)
        self.show()
        self.raise_()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillPath(rounded(QRectF(self.rect()), 1.5), QColor(theme.ACCENT))
        p.end()


class ProfileChip(QPushButton):
    """A profile button that can also be dragged to reorder."""

    def __init__(self, text: str, uid: str) -> None:
        super().__init__(text)
        self.uid = uid
        self._press: QPoint | None = None

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        moved = self._press is not None and \
            (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()
        if moved:
            self._press = None
            self.setDown(False)
            start_drag(self, PROFILE_MIME, self.uid, self)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press = None
        super().mouseReleaseEvent(e)


class ProfileBar(QWidget):
    """Profile chips: click to switch, drag to reorder, + to add, right-click / ⋯ to manage."""

    def __init__(self, store: Store, manager) -> None:
        super().__init__()
        self.store, self.manager = store, manager
        self.chips: list[ProfileChip] = []
        self.setAcceptDrops(True)
        self.line = DropLine(self, vertical=True)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        store.profiles_changed.connect(self.rebuild)
        store.hotkeys_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        label = QLabel(tr("Profil"))
        label.setObjectName("Muted")
        self.lay.addWidget(label)
        self.lay.addSpacing(4)
        self.chips = []
        for pr in self.store.profiles:
            chip = ProfileChip(pr.name, pr.uid)
            self.chips.append(chip)
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setChecked(pr.uid == self.store.active_uid)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(tr("{a0} Overlay{a1}  ·  Rechtsklick für Optionen", a0=len(pr.overlays), a1='' if len(pr.overlays) == 1 else 's')
                            + "  ·  " + tr("Ziehen zum Sortieren"))
            chip.clicked.connect(lambda _=False, uid=pr.uid: self.manager.switch_profile(uid))
            chip.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            chip.customContextMenuRequested.connect(lambda pos, pr=pr, c=chip: self.menu(pr, c.mapToGlobal(pos)))
            self.lay.addWidget(chip)
        add = IconButton(theme.Icon.ADD, tr("Neues Profil"), size=32)
        add.clicked.connect(self.add_profile)
        self.lay.addWidget(add)
        self.lay.addStretch()
        hint = QLabel(tr("{a0}  /  {a1} zum Wechseln", a0=self.store.hotkey_text('prev'), a1=self.store.hotkey_text('next')))
        hint.setObjectName("Dim")
        self.lay.addWidget(hint)
        more = IconButton(theme.Icon.MORE, tr("Profil verwalten"), size=32)
        more.clicked.connect(lambda: self.menu(self.store.profile, more.mapToGlobal(QPoint(0, more.height() + 4))))
        self.lay.addWidget(more)

    # -- drag & drop reordering ---------------------------------------------------------
    def _slot(self, x: int) -> tuple[int, int]:
        for i, chip in enumerate(self.chips):
            g = chip.geometry()
            if x < g.center().x():
                return i, g.left() - 4
        last = self.chips[-1].geometry()
        return len(self.chips), last.right() + 5

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(PROFILE_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(PROFILE_MIME) and self.chips:
            _, x = self._slot(e.position().toPoint().x())
            g = self.chips[0].geometry()
            self.line.show_at(x, g.top() + 2, g.height() - 4)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:
        self.line.hide()

    def dropEvent(self, e) -> None:
        self.line.hide()
        if e.mimeData().hasFormat(PROFILE_MIME) and self.chips:
            uid = bytes(e.mimeData().data(PROFILE_MIME)).decode()
            index, _ = self._slot(e.position().toPoint().x())
            self.store.move_profile(uid, index)
            e.acceptProposedAction()

    def add_profile(self) -> None:
        name = ConfirmDialog.ask_text(self.window(), tr("Neues Profil"), self.store.unique_name(tr("Profil")), tr("Anlegen"),
                                      tr("Ein neues, leeres Profil. Die Bibliothek teilen sich alle Profile."))
        if name:
            pr = self.store.add_profile(name)
            self.manager.switch_profile(pr.uid)

    def menu(self, pr, pos: QPoint) -> None:
        menu = QMenu(self)
        if pr.uid != self.store.active_uid:
            menu.addAction(tr("Aktivieren"), lambda: self.manager.switch_profile(pr.uid))
        menu.addAction(tr("Umbenennen …"), lambda: self.rename(pr))
        menu.addAction(tr("Duplizieren"), lambda: self.duplicate(pr))
        menu.addSeparator()
        delete = menu.addAction(tr("Löschen …"), lambda: self.delete(pr))
        delete.setEnabled(len(self.store.profiles) > 1)
        menu.exec(pos)

    def rename(self, pr) -> None:
        name = ConfirmDialog.ask_text(self.window(), tr("Profil umbenennen"), pr.name)
        if name:
            self.store.rename_profile(pr, name)

    def duplicate(self, pr) -> None:
        copy = self.store.add_profile(tr("{a0} Kopie", a0=pr.name), copy_from=pr)
        self.manager.switch_profile(copy.uid)

    def delete(self, pr) -> None:
        n = len(pr.overlays)
        if ConfirmDialog.ask(self.window(), tr("Profil „{a0}“ löschen?", a0=pr.name),
                             tr("Die Anordnung mit {a0} Overlay{a1} geht verloren. Die Bilder selbst bleiben in deiner Bibliothek.", a0=n, a1='' if n == 1 else 's'), tr("Profil löschen")):
            self.manager.delete_profile(pr)


class ActivePage(QWidget):
    def __init__(self, store: Store, loader: ImageLoader, manager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.store, self.loader, self.manager = store, loader, manager
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 8, 28, 0)
        root.setSpacing(18)

        top = QHBoxLayout()
        header, self.subtitle = page_header(tr("Auf dem Bildschirm"))
        top.addWidget(header)
        top.addStretch()
        self.hide_btn = QPushButton()
        self.hide_btn.clicked.connect(lambda: manager.set_all_hidden(not manager.all_hidden))
        clear = QPushButton(tr("Alle entfernen"))
        clear.setObjectName("Danger")
        clear.clicked.connect(self._remove_all)
        top.addWidget(self.hide_btn, 0, Qt.AlignmentFlag.AlignBottom)
        top.addWidget(clear, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(top)
        root.addWidget(ProfileBar(store, manager))

        self.tips = QLabel()
        self.tips.setWordWrap(True)
        self.tips.setStyleSheet(f"background:{theme.SURFACE}; border:1px solid {theme.BORDER}; border-radius:14px; padding:14px 16px;")
        root.addWidget(self.tips)
        self._update_tips()
        store.hotkeys_changed.connect(self._update_tips)

        content = QWidget()
        self.content = content
        self.rows: dict[str, OverlayRow] = {}
        self.line = DropLine(content, vertical=False)
        content.setAcceptDrops(True)
        content.installEventFilter(self)
        self.list = QVBoxLayout(content)
        self.list.setContentsMargins(0, 0, 8, 24)
        self.list.setSpacing(10)
        self.empty = EmptyState(theme.Icon.LAYERS, tr("Nichts platziert"),
                                tr("Wähle etwas aus deiner Bibliothek oder dem Workshop, um es auf den Bildschirm zu legen."))
        root.addWidget(scroll_wrap(content), 1)
        self.rows: dict[str, OverlayRow] = {}
        store.overlays_changed.connect(self.rebuild)
        store.filter_changed.connect(self.rebuild)
        store.profiles_changed.connect(self.rebuild)
        manager.changed.connect(self._refresh_rows)
        self.rebuild()

    def rebuild(self) -> None:
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w and w is not self.empty:
                w.deleteLater()
        self.rows = {}
        shown = self.manager.shown_states()
        for s in shown:
            row = OverlayRow(s, self.loader, self.manager)
            self.rows[s.uid] = row
            self.list.addWidget(row)
        self.list.addWidget(self.empty)
        self.empty.setVisible(not shown)
        self.list.addStretch()
        n, hidden = len(shown), len(self.store.overlays) - len(shown)
        text = tr("{a0} aktive{a1} Overlay{a2}  ·  Profil „{a3}“", a0=n, a1='s' if n == 1 else '', a2='' if n == 1 else 's', a3=self.store.profile.name)
        self.subtitle.setText(text + ("  ·  " + tr("{a0} NSFW ausgeblendet", a0=hidden) if hidden else ""))
        self._refresh_rows()

    # -- drag & drop reordering ---------------------------------------------------------
    def _slot(self, y: int) -> tuple[int, int]:
        rows = list(self.rows.values())
        for i, row in enumerate(rows):
            g = row.geometry()
            if y < g.center().y():
                return i, g.top() - 5
        return len(rows), rows[-1].geometry().bottom() + 6

    def eventFilter(self, obj, e) -> bool:
        if obj is getattr(self, "content", None) and getattr(self, "rows", None):
            t = e.type()
            if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove) and e.mimeData().hasFormat(OVERLAY_MIME):
                _, y = self._slot(e.position().toPoint().y())
                first = next(iter(self.rows.values())).geometry()
                self.line.show_at(y, first.left() + 12, first.width() - 24)
                e.acceptProposedAction()
                return True
            if t == QEvent.Type.DragLeave:
                self.line.hide()
                return True
            if t == QEvent.Type.Drop and e.mimeData().hasFormat(OVERLAY_MIME):
                self.line.hide()
                uid = bytes(e.mimeData().data(OVERLAY_MIME)).decode()
                index, _ = self._slot(e.position().toPoint().y())
                shown = list(self.rows)
                # the list may hide NSFW overlays: map the visible position to the full profile list
                overlays = self.store.overlays
                if index >= len(shown):
                    target = len(overlays)
                else:
                    target = next(i for i, o in enumerate(overlays) if o.uid == shown[index])
                self.store.move_overlay(uid, target)
                e.acceptProposedAction()
                return True
        return super().eventFilter(obj, e)

    def _update_tips(self) -> None:
        b = f'<b style="color:{theme.TEXT}">'
        self.tips.setText(
            tr("<span style=\"color:{a0}\">Im {a1}Bearbeiten-Modus</b> kannst du Overlays ziehen, an den Ecken skalieren oder mit dem {a2}Mausrad</b> zoomen. Rechtsklick öffnet mehr Optionen. Danach mit {a3}{a4}</b> fixieren: Dann lassen sich die Overlays durchklicken.</span>", a0=theme.MUTED, a1=b, a2=b, a3=b, a4=self.store.hotkey_text("edit")))

    def _remove_all(self) -> None:
        n = len(self.manager.shown_states())
        if n and ConfirmDialog.ask(self.window(), tr("Alle {a0} Overlays entfernen?", a0=n),
                                   tr("Sie verschwinden vom Bildschirm. Die Bilder bleiben in deiner Bibliothek."),
                                   tr("Alle entfernen")):
            for s in self.manager.shown_states():
                self.manager.remove(s)

    def _refresh_rows(self, *_) -> None:
        for row in self.rows.values():
            row.refresh()
        self.hide_btn.setText(tr("Alle einblenden") if self.manager.all_hidden else tr("Alle ausblenden"))


# ======================================================================================
class SettingRow(QFrame):
    def __init__(self, glyph: str, title: str, text: str, control: QWidget) -> None:
        super().__init__()
        self.setObjectName("Setting")
        self.setStyleSheet(f"QFrame#Setting {{ background:{theme.SURFACE}; border:1px solid {theme.BORDER};"
                           f" border-radius:14px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(16)
        icon = QLabel(glyph)
        icon.setFont(theme.icon_font(14))
        icon.setFixedWidth(26)
        icon.setStyleSheet(f"color:{theme.MUTED};")
        lay.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight:600;")
        d = QLabel(text)
        d.setObjectName("Muted")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        lay.addWidget(control)


def dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*") if path.exists() else []:
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


class StorageBar(QWidget):
    """Stacked bar: how much space Workshop / own uploads / cache take."""

    COLORS = ("#C9C9CF", "#8B8B93", "#4A4A52")

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[tuple[str, int]] = []
        self.setFixedHeight(64)

    def set_parts(self, parts: list[tuple[str, int]]) -> None:
        self.parts = parts
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v in self.parts) or 1
        bar = QRectF(0, 6, self.width(), 10)
        p.fillPath(rounded(bar, 5), QColor(theme.SURFACE_3))
        p.save()
        p.setClipPath(rounded(bar, 5))
        x = 0.0
        for (_, v), color in zip(self.parts, self.COLORS):
            w = bar.width() * v / total
            p.fillRect(QRectF(x, bar.top(), w, bar.height()), QColor(color))
            x += w
        p.restore()
        x = 0.0
        p.setFont(theme.ui_font(9))
        for (label, v), color in zip(self.parts, self.COLORS):
            p.setBrush(QColor(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x, 36, 9, 9))
            text = f"{label}  {human_size(v) if v else '0 KB'}"
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(x + 15, 28, 220, 24), Qt.AlignmentFlag.AlignVCenter, text)
            x += p.fontMetrics().horizontalAdvance(text) + 40
        p.end()


class HotkeyControl(QWidget):
    """Shows a hotkey; click it and press a new combination to change it."""

    def __init__(self, store: Store, action: str) -> None:
        super().__init__()
        self.store, self.action = store, action
        self.recording = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.button = QPushButton()
        self.button.setMinimumWidth(170)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setToolTip(tr("Klicken und neue Tastenkombination drücken"))
        self.button.clicked.connect(self.start)
        self.button.installEventFilter(self)
        self.reset = IconButton(theme.Icon.REFRESH, tr("Auf Standard zurücksetzen"), size=32)
        self.reset.clicked.connect(lambda: self._apply(None))
        lay.addWidget(self.button)
        lay.addWidget(self.reset)
        store.hotkeys_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        if self.recording:
            return
        self.button.setText(self.store.hotkey_text(self.action))
        self.button.setStyleSheet("")
        self.reset.setVisible(self.store.hotkey(self.action) != hotkeys.default(self.action))

    def start(self) -> None:
        if self.recording:
            return
        self.recording = True
        self.window().unregister_hotkeys()   # otherwise the current combo never reaches us
        self.button.setText(tr("Tasten drücken …"))
        self.button.setStyleSheet(f"border-color:{theme.ACCENT}; color:{theme.TEXT};")
        self.button.setFocus()
        self.button.grabKeyboard()

    def stop(self) -> None:
        if not self.recording:
            return
        self.recording = False
        self.button.releaseKeyboard()
        self.refresh()

    def _apply(self, combo: str | None) -> None:
        self.stop()
        self.window().change_hotkey(self.action, combo)
        self.refresh()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.button and self.recording:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self.stop()
                    self.window().register_hotkeys()
                    return True
                combo = hotkeys.from_key(event.key(), event.modifiers())
                if combo:
                    self._apply(combo)
                else:
                    held = [hotkeys.MOD_TEXT[m] for m in hotkeys.modifiers_text(event.modifiers())]
                    self.button.setText(" + ".join(held + ["…"]) if held else tr("Tasten drücken …"))
                return True
            if event.type() == QEvent.Type.FocusOut:
                self.stop()
                self.window().register_hotkeys()
        return super().eventFilter(obj, event)


CLOSE_MODES = {"auto": tr("Automatisch"), "tray": tr("Immer in den Tray"), "quit": tr("Immer beenden")}

AUTO_DELETE = [(0, tr("Nie")), (7, tr("Nach 7 Tagen")), (14, tr("Nach 14 Tagen")), (30, tr("Nach 30 Tagen")),
               (60, tr("Nach 60 Tagen")), (90, tr("Nach 90 Tagen"))]


class SettingsPage(QWidget):
    def __init__(self, store: Store, on_autostart) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.store = store
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 8, 28, 0)
        root.setSpacing(18)
        header, _ = page_header(tr("Einstellungen"), tr("Miso so, wie du es willst"))
        root.addWidget(header)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 24)
        lay.setSpacing(10)
        s = store.settings

        def toggle(attr: str, callback=None) -> ToggleSwitch:
            t = ToggleSwitch(checked=getattr(s, attr))

            def changed(on: bool) -> None:
                setattr(s, attr, on)
                store.save()
                if callback:
                    callback(on)
            t.toggled.connect(changed)
            return t

        def section(title: str, first: bool = False) -> None:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            if not first:
                lay.addSpacing(12)
            lay.addWidget(label)

        section(tr("Inhalt"), first=True)
        nsfw = ToggleSwitch(checked=s.hide_nsfw)
        nsfw.toggled.connect(store.set_hide_nsfw)
        lay.addWidget(SettingRow(theme.Icon.SHIELD, tr("NSFW ausblenden"),
                                 tr("Blendet alles mit 18+, NSFW, hentai usw. im Titel aus: im Workshop, in der Bibliothek und auf dem Bildschirm. Gelöscht wird dabei nichts."), nsfw))

        # -- storage --------------------------------------------------------------
        section(tr("Speicher"))
        card = QFrame()
        card.setObjectName("Setting")
        card.setStyleSheet(f"QFrame#Setting {{ background:{theme.SURFACE}; border:1px solid {theme.BORDER};"
                           f" border-radius:14px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 12)
        cl.setSpacing(8)
        head = QHBoxLayout()
        self.storage_total = QLabel()
        self.storage_total.setStyleSheet("font-size:15pt; font-weight:600; background:transparent;")
        self.storage_total.setMinimumWidth(260)
        head.addWidget(self.storage_total)
        head.addStretch()
        clear_cache = QPushButton(tr("Cache leeren"))
        clear_cache.clicked.connect(self._clear_cache)
        open_dir = QPushButton(tr("Ordner öffnen"))
        open_dir.clicked.connect(lambda: (WORKSHOP_DIR.parent.mkdir(parents=True, exist_ok=True),
                                          QDesktopServices.openUrl(QUrl.fromLocalFile(str(WORKSHOP_DIR.parent)))))
        head.addWidget(clear_cache)
        head.addWidget(open_dir)
        cl.addLayout(head)
        self.storage_bar = StorageBar()
        cl.addWidget(self.storage_bar)
        lay.addWidget(card)

        self.auto_combo = QComboBox()
        for days, label in AUTO_DELETE:
            self.auto_combo.addItem(label, days)
        self.auto_combo.setCurrentIndex(next((i for i, (d, _) in enumerate(AUTO_DELETE) if d == s.auto_delete_days), 0))
        self.auto_combo.currentIndexChanged.connect(self._auto_delete_changed)
        self.auto_combo.setMinimumWidth(160)
        lay.addWidget(SettingRow(theme.Icon.CLOCK, tr("Ungenutztes automatisch löschen"),
                                 tr("Elemente, die so lange nicht auf dem Bildschirm waren, werden gelöscht. Favoriten und Overlays, die gerade laufen, bleiben immer. Du wirst vorher gefragt."),
                                 self.auto_combo))
        unused_btn = QPushButton(tr("Jetzt aufräumen …"))
        unused_btn.setObjectName("Danger")
        unused_btn.clicked.connect(lambda: self.window().delete_unused())
        lay.addWidget(SettingRow(theme.Icon.DELETE, tr("Alle ungenutzten löschen"),
                                 tr("Löscht alles aus der Bibliothek, was gerade nicht auf dem Bildschirm ist und kein Favorit ist."), unused_btn))

        section(tr("Allgemein"))
        lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            lang_combo.addItem(name, code)
        lang_combo.setCurrentIndex(list(i18n.LANGUAGES).index(i18n.LANG))
        lang_combo.setMinimumWidth(190)

        def lang_changed(index: int) -> None:
            code = lang_combo.itemData(index)
            if code == i18n.LANG:
                return
            if ConfirmDialog.ask(self.window(), tr("Sprache ändern?"),
                                 tr("Miso startet dafür kurz neu. Deine Overlays bleiben, wo sie sind."),
                                 tr("Neu starten"), danger=False):
                s.language = code
                store.save_now()
                self.window().restart()
            else:
                lang_combo.blockSignals(True)
                lang_combo.setCurrentIndex(list(i18n.LANGUAGES).index(i18n.LANG))
                lang_combo.blockSignals(False)
        lang_combo.currentIndexChanged.connect(lang_changed)
        lay.addWidget(SettingRow(theme.Icon.GLOBE, tr("Sprache"),
                                 tr("Sprache der Oberfläche. Wird nach einem Neustart von Miso übernommen."),
                                 lang_combo))
        close_combo = QComboBox()
        for key, label in CLOSE_MODES.items():
            close_combo.addItem(label, key)
        close_combo.setCurrentIndex(max(0, list(CLOSE_MODES).index(s.close_mode) if s.close_mode in CLOSE_MODES else 0))
        close_combo.setMinimumWidth(190)

        def close_changed(i: int) -> None:
            s.close_mode = close_combo.itemData(i)
            store.save()
        close_combo.currentIndexChanged.connect(close_changed)
        lay.addWidget(SettingRow(theme.Icon.MIN, tr("Beim Schließen des Fensters"),
                                 tr("Automatisch: Solange Overlays auf dem Bildschirm sind, läuft Miso im Infobereich (Tray) weiter. Ohne Overlays wird Miso einfach beendet."), close_combo))
        def set_animations(on: bool) -> None:
            theme.ANIMATIONS = on and theme.system_animations_enabled()
        lay.addWidget(SettingRow(theme.Icon.SPARKLE, tr("Animationen"),
                                 tr("Weiche Übergänge, Einblendungen und Bewegungen. Sind Animationen in Windows ausgeschaltet, bleibt Miso ebenfalls ruhig."), toggle("animations", set_animations)))
        lay.addWidget(SettingRow(theme.Icon.SPARKLE, tr("Mit Windows starten"),
                                 tr("Overlays sind direkt nach dem Hochfahren wieder da."),
                                 toggle("autostart", on_autostart)))
        lay.addWidget(SettingRow(theme.Icon.EYE_OFF, tr("Unsichtbar starten"),
                                 tr("Beim Start nur die Overlays zeigen, nicht dieses Fenster."),
                                 toggle("start_hidden")))

        section(tr("Updates"))
        check_btn = QPushButton(tr("Nach Updates suchen"))
        check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        check_btn.clicked.connect(lambda: self.window().check_updates(manual=True))
        lay.addWidget(SettingRow(theme.Icon.REFRESH, f"Miso {__version__}",
                                 tr("Neue Versionen kommen direkt von GitHub. Das Setup wird vor der Installation auf Vollständigkeit und Prüfsumme kontrolliert."), check_btn))
        lay.addWidget(SettingRow(theme.Icon.GLOBE, tr("Automatisch nach Updates suchen"),
                                 tr("Beim Start und alle 12 Stunden. Du wirst gefragt, bevor etwas installiert wird."),
                                 toggle("update_check")))
        lay.addWidget(SettingRow(theme.Icon.DOWNLOAD, tr("Updates ohne Nachfrage installieren"),
                                 tr("Lädt neue Versionen automatisch und startet Miso danach neu (nur bei installiertem Miso, nicht bei der portablen Version)."),
                                 toggle("update_auto_install")))

        section(tr("Tastenkürzel"))
        hint = QLabel(tr("Klick auf ein Kürzel und drück die neue Tastenkombination (mit Strg, Alt, Umschalt oder Win). Esc bricht ab. Die Kürzel funktionieren überall, auch wenn Miso im Tray ist."))
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        descriptions = {
            "edit": tr("Overlays verschieben oder fixieren (durchklickbar)."),
            "hide": tr("Blendet alle Overlays schnell aus und wieder ein."),
            "prev": tr("Zum vorherigen Profil springen."),
            "next": tr("Zum nächsten Profil springen."),
        }
        for action, text in descriptions.items():
            lay.addWidget(SettingRow(theme.Icon.KEYBOARD, hotkeys.ACTIONS[action][1], text,
                                     HotkeyControl(store, action)))
        chip = QLabel(tr("Strg + V"))
        chip.setStyleSheet(f"background:{theme.SURFACE_3}; border:1px solid {theme.BORDER}; border-radius:8px;"
                           f" padding:5px 10px; font-weight:600;")
        lay.addWidget(SettingRow(theme.Icon.KEYBOARD, tr("Bild einfügen"),
                                 tr("Kopiertes Bild, GIF oder Bild-Link direkt in die Bibliothek (im Miso-Fenster)."), chip))

        section(tr("Spiele"))
        good = QLabel(tr("Gut"))
        good.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:600;")
        lay.addWidget(SettingRow(theme.Icon.SPARKLE, tr("Vollbild-Spiele"),
                                 tr("Overlays bleiben über Spielen im Modus „Vollbild (Fenster)“ bzw. „Rahmenlos“. "
                                    "Wechselt ein Spiel die Auflösung, bleiben sie an derselben Stelle. Bei "
                                    "exklusivem Vollbild kann Windows keine fremden Fenster darüber zeigen; Miso "
                                    "greift absichtlich nicht ins Spiel ein (kein Anti-Cheat-Risiko)."), good))

        section("Steam Workshop")
        info = QLabel(tr("Direkt"))
        info.setStyleSheet(f"color:{theme.SUCCESS}; font-weight:600;")
        lay.addWidget(SettingRow(theme.Icon.GLOBE, tr("Steam-Verbindung"),
                                 tr("Miso lädt Workshop-Items selbst über das Steam-Netzwerk (anonymer Login, Steam CDN). Kein Steam, kein SteamCMD nötig."), info))
        lay.addStretch()
        root.addWidget(scroll_wrap(content), 1)
        store.library_changed.connect(self.refresh_storage)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.refresh_storage()

    def refresh_storage(self) -> None:
        if not self.isVisible():
            return
        parts = [("Workshop", dir_size(WORKSHOP_DIR)), (tr("Eigene Bilder"), dir_size(UPLOAD_DIR)),
                 (tr("Cache"), dir_size(CACHE_DIR))]
        used = sum(v for _, v in parts)
        self.storage_total.setText(tr("{a0} belegt", a0=human_size(used) if used else '0 KB'))
        self.storage_bar.set_parts(parts)

    def _clear_cache(self) -> None:
        size = dir_size(CACHE_DIR)
        if not ConfirmDialog.ask(self.window(), tr("Cache leeren?"),
                                 tr("Löscht zwischengespeicherte Vorschaubilder ({a0}). Deine Bibliothek bleibt unberührt, Vorschauen werden bei Bedarf neu geladen.", a0=human_size(size) if size else '0 KB'),
                                 tr("Cache leeren")):
            return
        self.window().loader.nam.cache().clear()
        shutil.rmtree(CACHE_DIR / "thumbs", ignore_errors=True)
        self.refresh_storage()
        self.window().toast(tr("Cache geleert · {a0} frei", a0=human_size(size) if size else '0 KB'), "ok")

    def _auto_delete_changed(self, index: int) -> None:
        days = self.auto_combo.itemData(index)
        if days and not ConfirmDialog.ask(
                self.window(), tr("Automatisch löschen nach {a0} Tagen?", a0=days),
                tr("Elemente, die {a0} Tage nicht auf dem Bildschirm waren, werden gelöscht. Favoriten und aktive Overlays bleiben immer. Vor jedem Löschen fragt Miso dich noch einmal.", a0=days),
                tr("Aktivieren"), danger=False):
            self.auto_combo.blockSignals(True)
            self.auto_combo.setCurrentIndex(next(i for i, (d, _) in enumerate(AUTO_DELETE)
                                                 if d == self.store.settings.auto_delete_days))
            self.auto_combo.blockSignals(False)
            return
        self.store.settings.auto_delete_days = days
        self.store.save()
        if days:
            self.window().check_auto_delete()
