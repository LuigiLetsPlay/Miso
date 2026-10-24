"""Main window, overlay manager, tray icon and application entry point."""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QCursor, QDesktopServices, QGuiApplication, QKeySequence, QPainter,
                           QPen, QShortcut)
import shiboken6
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QApplication, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from . import __version__, hotkeys, importer, media, theme, updater, winapi, workshop
from .overlay import OverlayWindow, ProfileOSD
from .pages import ActivePage, LibraryPage, SettingsPage, WorkshopPage
from .store import APP_NAME, DATA_DIR, UPLOAD_DIR, LibraryItem, OverlayState, Store
from .widgets import (ConfirmDialog, FadeStack, IconButton, ImageLoader, NavButton, NavIndicator, ProgressDialog,
                      TitleButton, ToastHost, ToggleSwitch, human_size)
from .i18n import tr

TITLEBAR_H = 44
# one instance per data folder
SINGLETON = "Miso-" + hashlib.sha1(str(DATA_DIR).lower().encode()).hexdigest()[:10]


# ======================================================================================
class OverlayManager(QObject):
    changed = Signal()
    edit_changed = Signal(bool)

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.edit = False
        self.all_hidden = False
        self.windows: dict[str, OverlayWindow] = {}
        self.osd = ProfileOSD()
        store.filter_changed.connect(self.apply_filter)
        # games in (exclusive) fullscreen push themselves to the top and may switch the resolution
        self._topmost = QTimer(self, interval=2000, timeout=self.keep_on_top)
        self._topmost.start()
        self._remap = QTimer(self, singleShot=True, interval=150, timeout=self.remap)
        app = QGuiApplication.instance()
        for screen in app.screens():
            self._watch_screen(screen)
        app.screenAdded.connect(lambda sc: (self._watch_screen(sc), self._remap.start()))
        app.screenRemoved.connect(lambda sc: self._remap.start())

    def _watch_screen(self, screen) -> None:
        screen.geometryChanged.connect(lambda *_: self._remap.start())

    def _alive(self) -> list[OverlayWindow]:
        return [w for w in self.windows.values() if shiboken6.isValid(w)]

    def remap(self) -> None:
        """Screen size changed (e.g. a game set another resolution): keep overlays at the same spot."""
        for win in self._alive():
            win.place_on_screen()

    def keep_on_top(self) -> None:
        for win in self._alive():
            win.keep_on_top()

    def should_show(self, state: OverlayState) -> bool:
        return state.visible and not self.all_hidden and not self.store.hidden(state.title)

    def shown_states(self) -> list[OverlayState]:
        """Overlays the UI lists (everything except NSFW-filtered ones)."""
        return [s for s in self.store.overlays if not self.store.hidden(s.title)]

    def apply_filter(self) -> None:
        for s in self.store.overlays:
            win = self.windows.get(s.uid)
            if win:
                win.set_shown(self.should_show(s))
        self.changed.emit()

    def restore(self) -> None:
        for state in self.store.overlays:
            self._create(state)

    def _create(self, state: OverlayState) -> OverlayWindow:
        win = OverlayWindow(state, self.edit)
        win.changed.connect(self._on_changed)
        win.remove_requested.connect(lambda w: self.remove(w.state))
        win.edit_toggle_requested.connect(lambda: self.set_edit(not self.edit))
        self.windows[state.uid] = win
        if self.should_show(state):
            win.show()
        return win

    def place(self, item: LibraryItem, near: QWidget | None = None) -> None:
        try:
            info = media.probe(item.path)
        except Exception:
            return
        screen = (near.screen() if near else None) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        side = 340
        scale = min(1.0, side / max(info.width, info.height))
        w, h = max(48, round(info.width * scale)), max(48, round(info.height * scale))
        offset = 28 * (len(self.store.overlays) % 6)
        x = area.center().x() - w // 2 + offset
        y = area.center().y() - h // 2 + offset
        state = OverlayState(path=item.path, title=item.title, x=x, y=y, w=w, h=h)
        self.store.add_overlay(state)
        if self.all_hidden:
            self.set_all_hidden(False)
        self.set_edit(True)
        win = self._create(state)
        win.raise_()
        self.changed.emit()

    def remove(self, state: OverlayState) -> None:
        win = self.windows.pop(state.uid, None)
        if win:
            win.fade_out_and_close()
        self.store.remove_overlay(state)
        self.changed.emit()

    def remove_path(self, path: str) -> None:
        """Remove `path` from the screen and from every profile."""
        for s in [s for s in self.store.overlays if s.path == path]:
            self.remove(s)
        self.store.drop_path(path)

    # -- profiles -------------------------------------------------------------
    def switch_profile(self, uid: str, announce: bool = True) -> None:
        if uid == self.store.active_uid:
            if announce:
                self.osd.announce(self.store)
            return
        self.close_all(animate=True)
        self.store.set_active(uid)
        self.restore()
        self.changed.emit()
        if announce:
            self.osd.announce(self.store)

    def cycle_profile(self, step: int) -> None:
        profiles = self.store.profiles
        i = profiles.index(self.store.profile)
        self.switch_profile(profiles[(i + step) % len(profiles)].uid)

    def delete_profile(self, profile) -> None:
        if len(self.store.profiles) < 2:
            return
        if profile is self.store.profile:
            i = self.store.profiles.index(profile)
            self.switch_profile(self.store.profiles[i - 1 if i else 1].uid, announce=False)
        self.store.remove_profile(profile)

    def remove_all(self) -> None:
        for s in list(self.store.overlays):
            self.remove(s)

    def active_paths(self) -> list[str]:
        return [s.path for s in self.store.overlays]

    def set_edit(self, edit: bool) -> None:
        if edit == self.edit:
            return
        self.edit = edit
        for w in self.windows.values():
            w.set_edit_mode(edit)
        self.edit_changed.emit(edit)

    def set_all_hidden(self, hidden: bool) -> None:
        self.all_hidden = hidden
        self.apply_filter()

    def set_visible(self, state: OverlayState, visible: bool) -> None:
        state.visible = visible
        win = self.windows.get(state.uid)
        if win:
            win.set_shown(self.should_show(state))
        self.store.save()
        self.changed.emit()

    def set_opacity(self, state: OverlayState, value: float) -> None:
        state.opacity = value
        win = self.windows.get(state.uid)
        if win:
            win.apply_state()
        self.store.save()

    def center(self, state: OverlayState) -> None:
        win = self.windows.get(state.uid)
        if win:
            win.center_on_screen()

    def _on_changed(self, state: OverlayState) -> None:
        self.store.save()
        self.changed.emit()

    def close_all(self, animate: bool = False) -> None:
        for w in self.windows.values():
            w.fade_out_and_close() if animate else w.dispose()
        self.windows.clear()


# ======================================================================================
class EditModeCard(QWidget):
    """Sidebar card with the big edit-mode switch."""

    def __init__(self, manager: OverlayManager) -> None:
        super().__init__()
        self.manager = manager
        self.setMinimumHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 14, 14)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:700; background:transparent;")
        row.addWidget(self.title)
        row.addStretch()
        self.switch = ToggleSwitch(checked=manager.edit)
        self.switch.toggled.connect(manager.set_edit)
        row.addWidget(self.switch)
        lay.addLayout(row)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{theme.MUTED}; font-size:8.5pt; background:transparent;")
        lay.addWidget(self.hint)
        manager.edit_changed.connect(self.refresh)
        manager.store.hotkeys_changed.connect(lambda: self.refresh(manager.edit))
        self.refresh(manager.edit)

    def refresh(self, edit: bool) -> None:
        self.switch.blockSignals(True)
        self.switch.setChecked(edit)
        self.switch._set(1.0 if edit else 0.0)
        self.switch.blockSignals(False)
        self.title.setText(tr("Bearbeiten") if edit else tr("Fixiert"))
        key = self.manager.store.hotkey_text("edit")
        self.hint.setText(tr("Overlays ziehen & skalieren\n{a0} zum Fixieren", a0=key) if edit
                          else tr("Overlays sind durchklickbar\n{a0} zum Bearbeiten", a0=key))
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.manager.edit:
            p.setBrush(QColor(theme.SURFACE_2))
            p.setPen(QColor("#45454C"))
        else:
            p.setBrush(QColor(theme.SURFACE))
            p.setPen(QColor(theme.BORDER))
        p.drawRoundedRect(r, 14, 14)
        p.end()


class ProfileSwitcher(QWidget):
    """Sidebar card: current profile with ◀ ▶ to cycle; click the name to manage."""

    def __init__(self, store: Store, manager: OverlayManager, on_open) -> None:
        super().__init__()
        self.store = store
        self.setFixedHeight(62)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        prev = IconButton(theme.Icon.CHEVRON_LEFT, tr("Vorheriges Profil"), size=30)
        nxt = IconButton(theme.Icon.CHEVRON_RIGHT, tr("Nächstes Profil"), size=30)
        self._buttons = (prev, nxt)
        prev.clicked.connect(lambda: manager.cycle_profile(-1))
        nxt.clicked.connect(lambda: manager.cycle_profile(1))
        self.name = QPushButton()
        self.name.setObjectName("Ghost")
        self.name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name.setToolTip(tr("Profile verwalten"))
        self.name.clicked.connect(on_open)
        lay.addWidget(prev)
        lay.addWidget(self.name, 1)
        lay.addWidget(nxt)
        store.profiles_changed.connect(self.refresh)
        store.hotkeys_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        prev, nxt = self._buttons
        prev.setToolTip(tr("Vorheriges Profil ({a0})", a0=self.store.hotkey_text('prev')))
        nxt.setToolTip(tr("Nächstes Profil ({a0})", a0=self.store.hotkey_text('next')))
        pr = self.store.profile
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(pr.name, Qt.TextElideMode.ElideRight, 120))
        self.setToolTip(tr("Profil {a0} von {a1}", a0=self.store.profiles.index(pr) + 1, a1=len(self.store.profiles)))

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(theme.SURFACE))
        p.setPen(QColor(theme.BORDER))
        p.drawRoundedRect(r, 14, 14)
        p.end()


class DropHint(QWidget):
    """Full-window hint while something is dragged over Miso."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(8, 8, 10, 205))
        r = QRectF(self.rect()).adjusted(24, 24, -24, -24)
        pen = QPen(QColor(255, 255, 255, 110), 2)
        pen.setDashPattern([6, 5])
        p.setPen(pen)
        p.drawRoundedRect(r, 18, 18)
        p.setPen(QColor(theme.TEXT))
        p.setFont(theme.icon_font(30))
        p.drawText(r.adjusted(0, -70, 0, 0), Qt.AlignmentFlag.AlignCenter, theme.Icon.UPLOAD)
        p.setFont(theme.ui_font(15, theme.QFont.Weight.DemiBold, display=True))
        p.drawText(r.adjusted(0, 20, 0, 0), Qt.AlignmentFlag.AlignCenter, tr("Loslassen zum Hinzufügen"))
        p.setPen(QColor(theme.MUTED))
        p.setFont(theme.ui_font(10))
        p.drawText(r.adjusted(0, 80, 0, 0), Qt.AlignmentFlag.AlignCenter,
                   tr("Dateien, oder Bilder und GIFs direkt aus dem Browser"))
        p.end()


class Logo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(64)
        self.pm = theme.app_icon_pixmap(128)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(QRectF(4, 13, 38, 38), self.pm, QRectF(self.pm.rect()))
        f = theme.ui_font(16, theme.QFont.Weight.Bold, display=True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(52, 14, 150, 36), Qt.AlignmentFlag.AlignVCenter, APP_NAME)
        p.end()


# ======================================================================================
class MainWindow(QWidget):
    def __init__(self, store: Store, manager: OverlayManager, downloads: workshop.DownloadManager) -> None:
        super().__init__()
        self.store, self.manager, self.downloads = store, manager, downloads
        self.setObjectName("Root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(900, 600)
        self.resize(1240, 800)
        self.setAcceptDrops(True)
        self.loader = ImageLoader()
        self.toasts = ToastHost(self)
        self.updater = updater.Updater()
        self.updater.available.connect(self._on_update_available)
        self.updater.up_to_date.connect(self._on_up_to_date)
        self.updater.failed.connect(self._on_update_check_failed)
        self.importer = importer.Importer()
        self.importer.imported.connect(self._on_imported)
        self.importer.failed.connect(lambda m: self.toast(tr("Hinzufügen fehlgeschlagen: {a0}", a0=m), "error"))
        self.importer.busy.connect(self._on_import_busy)
        QShortcut(QKeySequence.StandardKey.Paste, self, self.paste,
                  context=Qt.ShortcutContext.WindowShortcut)
        self._native_ready = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # sidebar ---------------------------------------------------------------
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        side.setFixedWidth(236)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 4, 14, 16)
        sl.setSpacing(4)
        sl.addWidget(Logo())
        sl.addSpacing(14)
        self.nav: list[NavButton] = []
        for glyph, label in ((theme.Icon.COMPASS, tr("Entdecken")), (theme.Icon.LIBRARY, tr("Bibliothek")),
                             (theme.Icon.LAYERS, tr("Overlays")),(theme.Icon.SETTINGS, tr("Einstellungen"))):
            b = NavButton(glyph, label)
            b.clicked.connect(lambda _=False, i=len(self.nav): self.go(i))
            sl.addWidget(b)
            self.nav.append(b)
        self.nav_indicator = NavIndicator(side)
        sl.addStretch()
        self.update_pill = QPushButton()
        self.update_pill.setObjectName("UpdatePill")
        self.update_pill.setIcon(theme.glyph_icon(theme.Icon.DOWNLOAD, theme.ON_ACCENT))
        self.update_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_pill.setStyleSheet(f"QPushButton#UpdatePill {{ background:{theme.ACCENT}; color:{theme.ON_ACCENT};"
                                       f" border:none; border-radius:12px; padding:10px; }}"
                                       f"QPushButton#UpdatePill:hover {{ background:#E8E8EC; }}")
        self.update_pill.clicked.connect(lambda: self.offer_update(self.updater.latest, manual=True))
        self.update_pill.hide()
        sl.addWidget(self.update_pill)
        sl.addSpacing(6)
        sl.addWidget(ProfileSwitcher(store, manager, lambda: self.go(2)))
        sl.addSpacing(6)
        sl.addWidget(EditModeCard(manager))
        root.addWidget(side)

        # content -----------------------------------------------------------------
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(0)
        bar.addStretch()
        self.btn_min = TitleButton(theme.Icon.MIN)
        self.btn_max = TitleButton(theme.Icon.MAX)
        self.btn_close = TitleButton(theme.Icon.CLOSE, close=True)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max)
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            bar.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        titlebar = QWidget()
        titlebar.setFixedHeight(TITLEBAR_H)
        titlebar.setLayout(bar)
        ml.addWidget(titlebar)

        self.stack = FadeStack()
        self.workshop_page = WorkshopPage(store, downloads, self.loader, self.toast)
        self.library_page = LibraryPage(store, self.loader, manager.active_paths)
        self.active_page = ActivePage(store, self.loader, manager)
        self.settings_page = SettingsPage(store, self.apply_autostart)
        for page in (self.workshop_page, self.library_page, self.active_page, self.settings_page):
            self.stack.addWidget(page)
        ml.addWidget(self.stack, 1)
        root.addWidget(main, 1)

        self.workshop_page.place_requested.connect(self.place)
        self.library_page.place_requested.connect(self.place)
        self.drop_hint = DropHint(self)
        self.drop_hint.hide()
        manager.changed.connect(self._update_badge)
        store.overlays_changed.connect(self._update_badge)
        store.filter_changed.connect(self._update_badge)
        downloads.finished.connect(self._on_download_done)
        self._update_badge()
        self.go(0 if not store.library else 1)

    # -- native frame ---------------------------------------------------------
    def init_native(self) -> None:
        """Create the HWND (even while hidden) so hotkeys work from the start."""
        if not self._native_ready and winapi.IS_WIN:
            self._native_ready = True
            hwnd = int(self.winId())
            style = winapi.user32.GetWindowLongPtrW(hwnd, -16)
            # caption + thick frame give us Aero snap, animations and the DWM shadow
            winapi.user32.SetWindowLongPtrW(hwnd, -16, style | 0x00C00000 | 0x00040000 | 0x00020000 | 0x00010000)
            winapi.style_window(hwnd)
            winapi.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)  # FRAMECHANGED
            self.failed_hotkeys = self.register_hotkeys()

    def nativeEvent(self, event_type, message):
        if event_type != b"windows_generic_MSG" and event_type != "windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        msg = winapi.msg_from(message)
        if msg.message == winapi.WM_NCCALCSIZE and msg.wParam:
            if winapi.is_maximized(msg.hWnd):
                params = winapi.NCCALCSIZE_PARAMS.from_address(msg.lParam)
                t = winapi.frame_thickness()
                rc = params.rgrc[0]
                rc.left += t
                rc.top += t
                rc.right -= t
                rc.bottom -= t
            return True, 0
        if msg.message == winapi.WM_NCHITTEST:
            return True, self._hit_test()
        if msg.message == winapi.WM_HOTKEY:
            action = next((a for a, (hid, _, _) in hotkeys.ACTIONS.items() if hid == msg.wParam), None)
            if action == "edit":
                self.manager.set_edit(not self.manager.edit)
            elif action == "hide":
                self.manager.set_all_hidden(not self.manager.all_hidden)
            elif action == "prev":
                self.manager.cycle_profile(-1)
            elif action == "next":
                self.manager.cycle_profile(1)
            return True, 0
        return super().nativeEvent(event_type, message)

    # -- global hotkeys ----------------------------------------------------------
    def unregister_hotkeys(self) -> None:
        if self._native_ready:
            for hid, _, _ in hotkeys.ACTIONS.values():
                winapi.unregister_hotkey(int(self.winId()), hid)

    def register_hotkeys(self) -> list[str]:
        """(Re)register all global hotkeys; returns actions whose combo another app already uses."""
        self.unregister_hotkeys()
        failed = []
        for action, (hid, _, _) in hotkeys.ACTIONS.items():
            parsed = hotkeys.parse(self.store.hotkey(action))
            if not parsed or not winapi.register_hotkey(int(self.winId()), hid, *parsed):
                failed.append(action)
        return failed

    def change_hotkey(self, action: str, combo: str | None) -> bool:
        """Set a hotkey from the settings page (None = default). Keeps the old one if the new can't be used."""
        new = combo or hotkeys.default(action)
        clash = next((a for a in hotkeys.ACTIONS if a != action and self.store.hotkey(a) == new), None)
        if clash:
            self.toast(tr("{a0} ist schon für „{a1}“ vergeben", a0=hotkeys.display(new), a1=hotkeys.ACTIONS[clash][1]), "error")
            self.register_hotkeys()
            return False
        old = self.store.settings.hotkeys.get(action)
        self.store.set_hotkey(action, combo)
        if action in self.register_hotkeys():
            self.store.set_hotkey(action, old)
            self.register_hotkeys()
            self.toast(tr("{a0} wird schon von einem anderen Programm benutzt", a0=hotkeys.display(new)), "error")
            return False
        self.toast(f"{hotkeys.ACTIONS[action][1]}: {self.store.hotkey_text(action)}", "ok")
        return True

    def _hit_test(self) -> int:
        pos = self.mapFromGlobal(QCursor.pos())
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        if not self.isMaximized():
            b = 6
            left, right, top, bottom = x < b, x >= w - b, y < b, y >= h - b
            if top and left:
                return winapi.HTTOPLEFT
            if top and right:
                return winapi.HTTOPRIGHT
            if bottom and left:
                return winapi.HTBOTTOMLEFT
            if bottom and right:
                return winapi.HTBOTTOMRIGHT
            if left:
                return winapi.HTLEFT
            if right:
                return winapi.HTRIGHT
            if top:
                return winapi.HTTOP
            if bottom:
                return winapi.HTBOTTOM
        child = self.childAt(pos)
        interactive = (QAbstractButton, QLineEdit, QAbstractSlider)
        if child is not None and (isinstance(child, interactive) or isinstance(child.parent(), QLineEdit)):
            return winapi.HTCLIENT
        in_titlebar = y < TITLEBAR_H
        in_logo = x < 236 and y < 70
        return winapi.HTCAPTION if in_titlebar or in_logo else winapi.HTCLIENT

    def restart(self) -> None:
        restart_app()

    def toggle_max(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange:
            self.btn_max.glyph = theme.Icon.RESTORE if self.isMaximized() else theme.Icon.MAX
            self.btn_max.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        # buttons only have real geometry once laid out
        QTimer.singleShot(0, lambda: self.nav_indicator.move_to(self.nav[self.stack.currentIndex()], animate=False))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.toasts.reposition()

    # -- navigation & actions -------------------------------------------------
    def go(self, index: int) -> None:
        self.nav[index].setChecked(True)
        self.nav_indicator.move_to(self.nav[index], animate=self.isVisible())
        self.stack.setCurrentIndex(index)

    def toast(self, text: str, kind: str = "info") -> None:
        self.toasts.show(text, kind)

    def _update_badge(self) -> None:
        self.nav[2].set_badge(len(self.manager.shown_states()))

    def place(self, item: LibraryItem) -> None:
        first = not self.store.overlays
        self.manager.place(item, near=self)
        if first and self.store.settings.show_tips:
            self.toast(tr("Ziehen zum Verschieben, Mausrad zum Skalieren. {a0} fixiert die Overlays.", a0=self.store.hotkey_text('edit')))
        else:
            self.toast(tr("„{a0}“ platziert", a0=item.title), "ok")

    def _on_download_done(self, item_id: str, item: LibraryItem) -> None:
        self.toast(tr("„{a0}“ heruntergeladen. Klick drauf zum Platzieren", a0=item.title), "ok")

    # -- uploads (files, browser drops, Ctrl+V) ---------------------------------
    def import_files(self, files: list[str]) -> None:
        self.import_sources([("file", f) for f in files])

    def import_sources(self, sources: list) -> None:
        if not sources:
            self.toast(tr("Da war kein Bild dabei"), "error")
            return
        n = self.importer.run(sources)
        self.toast(tr("{a0} Bild{a1} wird hinzugefügt …", a0=n, a1='er' if n > 1 else '') if any(k == "url" for k, _ in sources)
                   else tr("{a0} Bild{a1} wird hochgeladen …", a0=n, a1='er' if n > 1 else ''))

    def paste(self) -> None:
        if QApplication.focusWidget() and isinstance(QApplication.focusWidget(), QLineEdit):
            QApplication.focusWidget().paste()
            return
        self.import_sources(importer.sources_from_mime(QApplication.clipboard().mimeData()))

    def _on_imported(self, path: str, title: str) -> None:
        self._import_count = getattr(self, "_import_count", 0) + 1
        self.store.add_library(LibraryItem(path=path, title=title, kind="upload"))
        if self.stack.currentIndex() != 1:
            self.go(1)

    def _on_import_busy(self, pending: int) -> None:
        if pending == 0 and getattr(self, "_import_count", 0):
            n = self._import_count
            self._import_count = 0
            self.toast(tr("{a0} Bild{a1} in der Bibliothek", a0=n, a1='er' if n > 1 else ''), "ok")

    # -- deleting (always confirmed by the caller) ------------------------------
    def delete_items(self, items: list[LibraryItem]) -> int:
        freed = 0
        for item in items:
            freed += item.size() if item.deletable else 0
            for path in item.all_paths:
                self.manager.remove_path(path)
            self.store.remove_library(item)
            workshop.delete_workshop_files(item)
            path = Path(item.path)
            if item.kind == "upload" and path.parent.resolve() == UPLOAD_DIR.resolve():
                path.unlink(missing_ok=True)
        return freed

    def delete_library_item(self, item: LibraryItem) -> None:
        on_screen = bool(set(item.all_paths) & set(self.manager.active_paths()))
        text = (tr("Die Datei wird von deinem PC gelöscht.") if item.deletable
                else tr("Der Eintrag verschwindet aus der Bibliothek, die Originaldatei bleibt."))
        if on_screen:
            text += tr(" Es wird auch vom Bildschirm entfernt.")
        if ConfirmDialog.ask(self, tr("„{a0}“ löschen?", a0=item.title), text, tr("Löschen")):
            freed = self.delete_items([item])
            self.toast(tr("„{a0}“ gelöscht", a0=item.title) + (tr(" · {a0} frei", a0=human_size(freed)) if freed else ""))

    def delete_unused(self, days: int | None = None, auto: bool = False) -> None:
        items = self.store.unused(days)
        if not items:
            if not auto:
                self.toast(tr("Nichts zu löschen. Alles wird gerade benutzt oder ist favorisiert."))
            return
        size = sum(i.size() for i in items if i.deletable)
        names = ", ".join(i.title for i in items[:4]) + (tr(" und {a0} weitere", a0=len(items) - 4) if len(items) > 4 else "")
        when = tr("seit {a0} Tagen nicht benutzt", a0=days) if days else tr("gerade nicht auf dem Bildschirm")
        title = tr("{a0} ungenutzte{a1} Element{a2} löschen?", a0=len(items), a1='s' if len(items) == 1 else '', a2='' if len(items) == 1 else 'e')
        text = (tr("{a0}.\n\nDiese Elemente sind {a1} und nicht favorisiert. Das gibt {a2} frei. Favoriten werden nie gelöscht.", a0=names, a1=when, a2=human_size(size)))
        if ConfirmDialog.ask(self, title, text, tr("Löschen"), cancel=tr("Diesmal nicht") if auto else tr("Abbrechen")):
            freed = self.delete_items(items)
            self.toast(tr("{a0} gelöscht · {a1} frei", a0=len(items), a1=human_size(freed)), "ok")

    def check_auto_delete(self) -> None:
        days = self.store.settings.auto_delete_days
        if days and self.isVisible():
            self.delete_unused(days, auto=True)

    # -- updates (GitHub releases) ------------------------------------------------
    def check_updates(self, manual: bool = False) -> None:
        if not manual and not self.store.settings.update_check:
            return
        self._manual_update_check = manual
        if manual:
            self.toast(tr("Suche nach Updates …"))
        self.updater.check()

    def _on_update_available(self, release) -> None:
        self.update_pill.setText(tr("  Update auf {a0}", a0=release.version))
        self.update_pill.show()
        manual = getattr(self, "_manual_update_check", False)
        self._manual_update_check = False
        s = self.store.settings
        if not manual and s.update_auto_install and updater.is_installed():
            self.start_update(release)
        elif manual or s.update_dismissed != release.version:
            self.offer_update(release, manual)

    def _on_up_to_date(self) -> None:
        if getattr(self, "_manual_update_check", False):
            self._manual_update_check = False
            self.toast(tr("Miso ist aktuell (Version {a0})", a0=__version__), "ok")

    def _on_update_check_failed(self, message: str) -> None:
        if getattr(self, "_manual_update_check", False):
            self._manual_update_check = False
            self.toast(tr("Update-Suche fehlgeschlagen: {a0}", a0=message), "error")

    def offer_update(self, release, manual: bool = False) -> None:
        if release is None:
            return
        if not self.isVisible():
            self.bring_to_front()
        notes = re.sub(r"[#*`>]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", release.notes).strip()
        notes = re.sub(r"\n{3,}", "\n\n", notes)
        if len(notes) > 600:
            notes = notes[:600].rsplit("\n", 1)[0] + "\n…"
        text = tr("Du hast Version {a0}.\n\n{a1}", a0=__version__, a1=notes) if notes else tr("Du hast Version {a0}.", a0=__version__)
        if not updater.is_installed():
            text += tr("\n\nDiese Kopie ist nicht installiert (portabel). Die Release-Seite wird im Browser geöffnet.")
        if ConfirmDialog.ask(self, tr("Miso {a0} ist da", a0=release.version), text, tr("Jetzt aktualisieren"),
                             cancel=tr("Später"), danger=False):
            self.start_update(release)
        else:
            self.store.settings.update_dismissed = release.version
            self.store.save()

    def start_update(self, release) -> None:
        if not updater.is_installed():
            QDesktopServices.openUrl(QUrl(release.page_url))
            return
        dlg = ProgressDialog(self, tr("Miso {a0} wird heruntergeladen", a0=release.version))
        self.updater.progress.connect(dlg.set_progress)
        dlg.cancelled.connect(lambda: (self.updater.cancel.set(), dlg.reject()))

        def done(path: str) -> None:
            dlg.status.setText(tr("Wird installiert, Miso startet gleich neu …"))
            dlg.cancel_btn.setEnabled(False)
            updater.launch_installer(Path(path))
            self._quitting = True
            QTimer.singleShot(400, request_quit)

        def failed(message: str) -> None:
            dlg.reject()
            if message != tr("Abgebrochen"):
                self.toast(tr("Update fehlgeschlagen: {a0}", a0=message), "error")

        self.updater.downloaded.connect(done)
        self.updater.download_failed.connect(failed)
        dlg.finished.connect(lambda *_: self._disconnect_update(dlg, done, failed))
        self.updater.download(release)
        dlg.show()

    def _disconnect_update(self, dlg, done, failed) -> None:
        for sig, slot in ((self.updater.progress, dlg.set_progress), (self.updater.downloaded, done),
                          (self.updater.download_failed, failed)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def apply_autostart(self, on: bool) -> None:
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}" --hidden'
        else:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            entry = Path(__file__).resolve().parent.parent / "Miso.pyw"
            cmd = f'"{pyw}" "{entry}" --hidden'
        winapi.set_autostart(APP_NAME, cmd if on else None)

    # -- drag & drop ------------------------------------------------------------
    def dragEnterEvent(self, e) -> None:
        m = e.mimeData()
        if m.hasUrls() or m.hasImage() or m.hasHtml():
            e.acceptProposedAction()
            self.drop_hint.setGeometry(self.rect())
            self.drop_hint.show()
            self.drop_hint.raise_()

    def dragLeaveEvent(self, e) -> None:
        self.drop_hint.hide()

    def dropEvent(self, e) -> None:
        self.drop_hint.hide()
        self.import_sources(importer.sources_from_mime(e.mimeData()))
        e.acceptProposedAction()

    # -- lifecycle ---------------------------------------------------------------
    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _close_to_tray(self) -> bool:
        mode = self.store.settings.close_mode
        if mode == "tray":
            return True
        if mode == "quit":
            return False
        # auto: only keep running while something is actually on screen
        return any(self.manager.should_show(s) for s in self.store.overlays)

    def closeEvent(self, e) -> None:
        if self._close_to_tray() and not getattr(self, "_quitting", False):
            e.ignore()
            self.hide()
            app = QApplication.instance()
            if not getattr(self, "_tray_hint", False) and hasattr(app, "tray"):
                self._tray_hint = True
                why = (tr("Deine Overlays bleiben auf dem Bildschirm.") if self.store.settings.close_mode == "auto"
                       else tr("Miso läuft im Hintergrund weiter."))
                app.tray.showMessage(APP_NAME, tr("{a0} Rechtsklick aufs Tray-Icon für Optionen.", a0=why),
                                     theme.app_icon(), 3500)
            return
        e.accept()
        request_quit()


# ======================================================================================
def request_quit() -> None:
    """Really quit Miso (tray "Quit", updates, restarts, Windows shutdown)."""
    app = QApplication.instance()
    for w in app.topLevelWidgets():
        if isinstance(w, MainWindow):
            w._quitting = True
    app.exit(0)


def make_tray(app: QApplication, window: MainWindow, manager: OverlayManager) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(theme.app_icon(), app)
    tray.setToolTip(APP_NAME)
    menu = QMenu()
    menu.addAction(tr("Miso öffnen"), window.bring_to_front)
    menu.addSeparator()
    edit = QAction(tr("Bearbeiten-Modus"), menu, checkable=True)
    edit.setChecked(manager.edit)
    edit.toggled.connect(manager.set_edit)
    manager.edit_changed.connect(edit.setChecked)
    menu.addAction(edit)
    profiles = menu.addMenu(tr("Profil"))

    def fill_profiles() -> None:
        profiles.clear()
        for pr in manager.store.profiles:
            a = QAction(pr.name, profiles, checkable=True)
            a.setChecked(pr.uid == manager.store.active_uid)
            a.triggered.connect(lambda _=False, uid=pr.uid: manager.switch_profile(uid))
            profiles.addAction(a)
    profiles.aboutToShow.connect(fill_profiles)
    hide = QAction(tr("Overlays ausblenden"), menu, checkable=True)
    hide.toggled.connect(manager.set_all_hidden)
    manager.changed.connect(lambda: hide.setChecked(manager.all_hidden))
    menu.addAction(hide)
    menu.addSeparator()

    menu.addAction(tr("Beenden"), request_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.bring_to_front()
                           if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                                         QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    tray._menu = menu
    tray.show()
    return tray


def _wait_for_previous_instance() -> None:
    """After an in-app restart (language change) wait until the old process has really exited,
    otherwise its global hotkeys would still be registered."""
    arg = next((a for a in sys.argv if a.startswith("--restart-from=")), None)
    if not arg or not winapi.IS_WIN:
        return
    try:
        pid = int(arg.split("=", 1)[1])
    except ValueError:
        return
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.WaitForSingleObject(handle, 8000)
        ctypes.windll.kernel32.CloseHandle(handle)


def restart_app() -> None:
    """Start a fresh Miso and quit this one (used after switching the language)."""
    app = QApplication.instance()
    server = getattr(app, "single_instance", None)
    if server:
        server.close()
    args = [a for a in sys.argv[1:] if not a.startswith("--restart-from=") and a != "--hidden"]
    if not getattr(sys, "frozen", False):
        args = [str(Path(sys.argv[0]).resolve())] + args
    args.append(f"--restart-from={os.getpid()}")
    QProcess.startDetached(sys.executable, args)
    request_quit()


def main() -> int:
    _wait_for_previous_instance()
    if winapi.IS_WIN:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Miso.Overlay")
        # lets the installer/uninstaller notice a running Miso (Inno Setup "AppMutex")
        main.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "MisoAppMutex")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    # single instance: a second launch just brings the first one to the front
    socket = QLocalSocket()
    socket.connectToServer(SINGLETON)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(SINGLETON)
    server = QLocalServer()
    server.listen(SINGLETON)
    app.single_instance = server
    # Windows log-off / shutdown: don't let the "keep running in the tray" logic block it
    app.commitDataRequest.connect(lambda *_: request_quit())

    theme.setup_fonts()
    app.setStyleSheet(theme.STYLESHEET)
    app.setFont(theme.ui_font(10))
    app.setWindowIcon(theme.app_icon())

    store = Store()
    workshop.migrate_packs(store)
    theme.ANIMATIONS = store.settings.animations and theme.system_animations_enabled()
    manager = OverlayManager(store)
    downloads = workshop.DownloadManager(store)
    window = MainWindow(store, manager, downloads)
    window.init_native()
    app.tray = make_tray(app, window, manager)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window.bring_to_front()))

    manager.restore()
    if not ("--hidden" in sys.argv or store.settings.start_hidden):
        window.show()

    # auto-cleanup: shortly after start and then every few hours (always asks first)
    QTimer.singleShot(2500, window.check_auto_delete)
    cleanup = QTimer(app, interval=6 * 3600 * 1000, timeout=window.check_auto_delete)
    cleanup.start()

    # update check: a few seconds after start, then twice a day
    QTimer.singleShot(5000, window.check_updates)
    update_timer = QTimer(app, interval=12 * 3600 * 1000, timeout=window.check_updates)
    update_timer.start()

    def shutdown() -> None:
        downloads.cancel_all()
        store.save_now()
        manager.close_all()
        if winapi.IS_WIN:
            window.unregister_hotkeys()
        app.tray.hide()
    app.aboutToQuit.connect(shutdown)
    return app.exec()
