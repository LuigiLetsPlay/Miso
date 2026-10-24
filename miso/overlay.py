"""The floating, always-on-top windows that show a GIF/image on the desktop."""
from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPen,
                           QTransform)
from PySide6.QtWidgets import QMenu, QWidget

from . import media, theme, winapi
from .store import OverlayState

HANDLE = 16          # px grab zone for the corner handles
SNAP = 14            # px screen-edge snapping distance
MIN_SIDE = 48


class OverlayWindow(QWidget):
    changed = Signal(object)            # OverlayState
    remove_requested = Signal(object)   # OverlayWindow
    edit_toggle_requested = Signal()

    def __init__(self, state: OverlayState, edit_mode: bool) -> None:
        super().__init__(None)
        self.state = state
        self.edit = edit_mode
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setWindowTitle(f"Miso – {state.title}")

        self.frames: media.Frames | None = None
        self.index = 0
        self.error = ""
        self._job: media.DecodeJob | None = None
        self._request = 0
        self._hover = False
        self._drag: tuple[str, QPoint, QRect] | None = None

        self._timer = QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._next_frame)
        self._redecode = QTimer(self, singleShot=True, interval=350, timeout=self._maybe_decode)

        self.setGeometry(state.x, state.y, max(MIN_SIDE, state.w), max(MIN_SIDE, state.h))
        self._maybe_decode()

    # -- decoding -----------------------------------------------------------
    def _target_side(self) -> int:
        return int(max(self.width(), self.height()) * self.devicePixelRatioF())

    def _maybe_decode(self) -> None:
        target = self._target_side()
        if self.frames:
            cached = max(self.frames.size.width(), self.frames.size.height())
            native = max(self.frames.native.width(), self.frames.native.height())
            too_small = cached < target * 0.92 and cached < native
            too_big = cached > target * 2.5
            if not (too_small or too_big):
                return
        if self._job:
            self._job.cancelled = True
        self._request += 1
        job = media.DecodeJob(self.state.path, max(64, int(target * 1.15)), self._request)
        job.signals.done.connect(self._on_decoded)
        job.signals.failed.connect(self._on_failed)
        self._job = job
        media.submit(job)

    def _on_decoded(self, frames: media.Frames, request: int) -> None:
        if request != self._request:
            return
        self._job = None
        first = self.frames is None
        self.frames = frames
        self.index %= max(1, len(frames.images))
        if first:
            self._fit_aspect()
        self.update()
        if len(frames.images) > 1 and not self._timer.isActive():
            self._schedule()

    def _on_failed(self, message: str, request: int) -> None:
        if request == self._request:
            self.error = message
            self.update()

    def _fit_aspect(self) -> None:
        """Make the window match the media's aspect ratio (keeps the width)."""
        n = self.frames.native
        if n.width() <= 0 or n.height() <= 0:
            return
        h = round(self.width() * n.height() / n.width())
        if abs(h - self.height()) > 1:
            self.resize(self.width(), h)

    def aspect(self) -> float:
        if self.frames and self.frames.native.height():
            return self.frames.native.width() / self.frames.native.height()
        return self.width() / max(1, self.height())

    # -- playback -----------------------------------------------------------
    def _schedule(self) -> None:
        if not self.frames or len(self.frames.images) < 2:
            return
        d = self.frames.durations[self.index] / max(0.1, self.state.speed)
        self._timer.start(max(5, int(d)))

    def _next_frame(self) -> None:
        if not self.frames:
            return
        self.index = (self.index + 1) % len(self.frames.images)
        self.update()
        self._schedule()

    # -- modes --------------------------------------------------------------
    def set_edit_mode(self, edit: bool) -> None:
        self.edit = edit
        self._apply_click_through()
        self.setCursor(Qt.CursorShape.SizeAllCursor if edit else Qt.CursorShape.ArrowCursor)
        self.update()

    def _apply_click_through(self) -> None:
        winapi.set_click_through(int(self.winId()), not self.edit)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_click_through()
        self.set_edit_mode(self.edit)

    def apply_state(self) -> None:
        """Re-read opacity/speed/flip after they were changed elsewhere."""
        self.update()
        if self.frames and len(self.frames.images) > 1:
            self._timer.stop()
            self._schedule()

    # -- painting -----------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())

        if self.edit:
            # near-invisible fill so the whole rectangle is grabbable
            bg = QPainterPath()
            bg.addRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
            p.fillPath(bg, QColor(20, 16, 32, 70 if self._hover else 28))

        if self.frames and self.frames.images:
            img = self.frames.images[self.index]
            p.save()
            p.setOpacity(self.state.opacity)
            if self.state.flip:
                p.setTransform(QTransform(-1, 0, 0, 1, r.width(), 0))
            p.drawImage(r, img)
            p.restore()
        elif self.error:
            p.setPen(QColor(theme.DANGER))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       f"Kann nicht geladen werden\n{self.error[:80]}")
        else:
            p.setPen(QColor(255, 255, 255, 140))
            p.setFont(theme.ui_font(9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Lädt …")

        if self.edit:
            self._paint_edit_chrome(p, r)
        p.end()

    def _paint_edit_chrome(self, p: QPainter, r: QRectF) -> None:
        frame = r.adjusted(1.5, 1.5, -1.5, -1.5)
        pen = QPen(QColor(255, 255, 255, 200 if self._hover else 120), 1.5)
        if not self._hover:
            pen.setDashPattern([4, 3])
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(frame, 10, 10)

        # corner handles
        for c in (frame.topLeft(), frame.topRight(), frame.bottomLeft(), frame.bottomRight()):
            p.setPen(QPen(QColor(20, 20, 22, 220), 1.5))
            p.setBrush(QColor(theme.TEXT))
            p.drawEllipse(c, 4.5, 4.5)

        if self._hover and self.width() > 120:
            label = self.state.title
            p.setFont(theme.ui_font(8.5, display=False))
            fm = p.fontMetrics()
            label = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(self.width() - 40))
            chip = QRectF(10, 10, fm.horizontalAdvance(label) + 18, fm.height() + 8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 12, 20, 210))
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            p.setPen(QColor("white"))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, label)

            size = f"{self.width()} × {self.height()}"
            sw = fm.horizontalAdvance(size) + 16
            chip = QRectF(r.width() - sw - 10, r.height() - fm.height() - 18, sw, fm.height() + 8)
            p.setBrush(QColor(12, 12, 20, 210))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            p.setPen(QColor(theme.MUTED))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, size)

    # -- interaction --------------------------------------------------------
    def _corner_at(self, pos: QPoint) -> str | None:
        w, h = self.width(), self.height()
        near_l, near_r = pos.x() < HANDLE, pos.x() > w - HANDLE
        near_t, near_b = pos.y() < HANDLE, pos.y() > h - HANDLE
        if near_t and near_l:
            return "tl"
        if near_t and near_r:
            return "tr"
        if near_b and near_l:
            return "bl"
        if near_b and near_r:
            return "br"
        return None

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if not self.edit:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            corner = self._corner_at(event.position().toPoint())
            self._drag = (corner or "move", event.globalPosition().toPoint(), self.geometry())
            self.raise_()

    def mouseMoveEvent(self, event) -> None:
        if not self.edit:
            return
        pos = event.position().toPoint()
        if self._drag is None:
            corner = self._corner_at(pos)
            shapes = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                      "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor}
            self.setCursor(shapes.get(corner, Qt.CursorShape.SizeAllCursor))
            return
        mode, start, geo = self._drag
        delta = event.globalPosition().toPoint() - start
        if mode == "move":
            self.move(self._snap(geo.topLeft() + delta, geo.size()))
        else:
            self._resize_from(mode, geo, delta)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag:
            self._drag = None
            self._commit()

    def mouseDoubleClickEvent(self, event) -> None:
        if self.edit and event.button() == Qt.MouseButton.LeftButton:
            self.edit_toggle_requested.emit()

    def wheelEvent(self, event) -> None:
        if not self.edit:
            return
        steps = event.angleDelta().y() / 120
        if not steps:
            return
        self.scale_by(1.08 ** steps)

    def scale_by(self, factor: float, anchor: QPointF | None = None) -> None:
        geo = self.geometry()
        center = anchor or QPointF(geo.center())
        w = max(MIN_SIDE, round(geo.width() * factor))
        h = max(MIN_SIDE, round(w / self.aspect()))
        self.setGeometry(round(center.x() - w / 2), round(center.y() - h / 2), w, h)
        self._commit()

    def _resize_from(self, corner: str, geo: QRect, delta: QPoint) -> None:
        aspect = self.aspect()
        dx = delta.x() if "r" in corner else -delta.x()
        dy = delta.y() if "b" in corner else -delta.y()
        # follow whichever axis moved more, keep the aspect ratio
        w = geo.width() + dx
        if abs(dy) * aspect > abs(dx):
            w = (geo.height() + dy) * aspect
        w = max(MIN_SIDE, round(w))
        h = max(MIN_SIDE, round(w / aspect))
        x = geo.left() if "l" not in corner else geo.right() - w + 1
        y = geo.top() if "t" not in corner else geo.bottom() - h + 1
        self.setGeometry(x, y, w, h)

    def _snap(self, top_left: QPoint, size: QSize) -> QPoint:
        screen = QGuiApplication.screenAt(QCursor.pos()) or self.screen()
        area = screen.availableGeometry()
        x, y = top_left.x(), top_left.y()
        if abs(x - area.left()) < SNAP:
            x = area.left()
        if abs(x + size.width() - area.right() - 1) < SNAP:
            x = area.right() + 1 - size.width()
        if abs(y - area.top()) < SNAP:
            y = area.top()
        if abs(y + size.height() - area.bottom() - 1) < SNAP:
            y = area.bottom() + 1 - size.height()
        return QPoint(x, y)

    def keyPressEvent(self, event) -> None:
        if not self.edit:
            return
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if event.key() in moves:
            dx, dy = moves[event.key()]
            self.move(self.x() + dx, self.y() + dy)
            self._commit()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_requested.emit(self)
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.scale_by(1.1)
        elif event.key() == Qt.Key.Key_Minus:
            self.scale_by(1 / 1.1)

    def contextMenuEvent(self, event) -> None:
        if not self.edit:
            return
        menu = QMenu(self)
        title = menu.addAction(self.state.title)
        title.setEnabled(False)
        menu.addSeparator()

        opacity = menu.addMenu("Deckkraft")
        for v in (1.0, 0.85, 0.7, 0.5, 0.3):
            a = opacity.addAction(("●  " if math.isclose(self.state.opacity, v) else "     ") + f"{int(v * 100)} %")
            a.triggered.connect(lambda _=False, v=v: self._set("opacity", v))
        speed = menu.addMenu("Geschwindigkeit")
        for v in (0.5, 0.75, 1.0, 1.5, 2.0):
            a = speed.addAction(("●  " if math.isclose(self.state.speed, v) else "     ") + f"{v:g}×")
            a.triggered.connect(lambda _=False, v=v: self._set("speed", v))

        flip = QAction(("●  " if self.state.flip else "") + "Horizontal spiegeln", menu)
        flip.triggered.connect(lambda: self._set("flip", not self.state.flip))
        menu.addAction(flip)
        menu.addAction("Originalgröße", self.original_size)
        menu.addAction("Bildschirm-Mitte", self.center_on_screen)
        menu.addSeparator()
        menu.addAction("Fertig (Overlay fixieren)", self.edit_toggle_requested.emit)
        menu.addAction("Entfernen", lambda: self.remove_requested.emit(self))
        menu.exec(event.globalPos())

    def _set(self, attr: str, value) -> None:
        setattr(self.state, attr, value)
        self.apply_state()
        self.changed.emit(self.state)

    def original_size(self) -> None:
        if not self.frames:
            return
        n = self.frames.native
        area = self.screen().availableGeometry()
        scale = min(1.0, area.width() * 0.9 / n.width(), area.height() * 0.9 / n.height())
        c = self.geometry().center()
        w, h = round(n.width() * scale), round(n.height() * scale)
        self.setGeometry(c.x() - w // 2, c.y() - h // 2, w, h)
        self._commit()

    def center_on_screen(self) -> None:
        area = self.screen().availableGeometry()
        self.move(area.center() - QPoint(self.width() // 2, self.height() // 2))
        self._commit()

    # -- state sync ---------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._redecode.start()

    def _commit(self) -> None:
        g = self.geometry()
        self.state.x, self.state.y, self.state.w, self.state.h = g.x(), g.y(), g.width(), g.height()
        self.changed.emit(self.state)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self._job:
            self._job.cancelled = True
        super().closeEvent(event)


class ProfileOSD(QWidget):
    """Small pill at the top of the screen that names the profile you switched to."""

    W, H = 340, 92

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.name, self.index, self.count, self.overlays = "", 0, 1, 0
        self._hide = QTimer(self, singleShot=True, interval=1400, timeout=self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(180)
        self._fade.finished.connect(lambda: self.hide() if self.windowOpacity() < 0.05 else None)

    def announce(self, store) -> None:
        self.name = store.profile.name
        self.index = store.profiles.index(store.profile)
        self.count = len(store.profiles)
        self.overlays = len(store.overlays)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.center().x() - self.W // 2, area.top() + 36)
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            winapi.set_click_through(int(self.winId()), True)
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()
        self.update()
        self._hide.start()

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        p.fillPath(path, QColor(18, 18, 21, 236))
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.drawPath(path)

        p.setPen(QColor(theme.DIM))
        p.setFont(theme.icon_font(10))
        p.drawText(QRectF(r.left() + 14, r.top(), 24, 52), Qt.AlignmentFlag.AlignCenter, "\uE76B")   # chevron left
        p.drawText(QRectF(r.right() - 38, r.top(), 24, 52), Qt.AlignmentFlag.AlignCenter, "\uE76C")  # chevron right

        p.setPen(QColor(theme.TEXT))
        p.setFont(theme.ui_font(13, theme.QFont.Weight.DemiBold, display=True))
        fm = p.fontMetrics()
        name = fm.elidedText(self.name, Qt.TextElideMode.ElideRight, int(r.width() - 90))
        p.drawText(QRectF(r.left(), r.top() + 6, r.width(), 40), Qt.AlignmentFlag.AlignCenter, name)

        p.setPen(QColor(theme.MUTED))
        p.setFont(theme.ui_font(8.5))
        sub = f"Profil {self.index + 1} von {self.count}  ·  {self.overlays} Overlay{'' if self.overlays == 1 else 's'}"
        p.drawText(QRectF(r.left(), r.top() + 40, r.width(), 18), Qt.AlignmentFlag.AlignCenter, sub)

        # position dots
        n = min(self.count, 12)
        x0 = r.center().x() - (n - 1) * 6
        for i in range(n):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.TEXT) if i == self.index else QColor(255, 255, 255, 50))
            p.drawEllipse(QPointF(x0 + i * 12, r.bottom() - 12), 2.6, 2.6)
        p.end()
