"""Reusable custom-painted widgets: cards, grid, toggle, toasts, image loading."""
from __future__ import annotations

import hashlib

from PySide6.QtCore import (Property, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRectF, QSize,
                            Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QAbstractButton, QDialog, QFrame, QGraphicsDropShadowEffect,
                               QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import media, theme
from .store import CACHE_DIR
from .i18n import tr


def human_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} Mio"
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def human_ago(ts: float) -> str:
    import time
    s = max(0, time.time() - ts)
    if s < 120:
        return tr("gerade eben")
    if s < 3600:
        return tr("vor {a0} Min.", a0=int(s // 60))
    if s < 86400:
        return tr("vor {a0} Std.", a0=int(s // 3600))
    d = int(s // 86400)
    return "gestern" if d == 1 else tr("vor {a0} Tagen", a0=d)


def human_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{max(1, n // 1024)} KB"


# -- image loading -------------------------------------------------------------

class ImageLoader(QObject):
    """Loads remote thumbnails (disk-cached) and local thumbnails (decoded once)."""

    loaded = Signal(str, QPixmap)

    def __init__(self) -> None:
        super().__init__()
        self.nam = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(str(CACHE_DIR / "http"))
        cache.setMaximumCacheSize(300 * 1024 * 1024)
        self.nam.setCache(cache)
        self.memory: dict[str, QPixmap] = {}
        self.pending: set[str] = set()
        self._local_jobs: dict[str, media.DecodeJob] = {}

    def get(self, key: str) -> QPixmap | None:
        return self.memory.get(key)

    def request_url(self, url: str) -> None:
        if not url or url in self.memory or url in self.pending:
            return
        self.pending.add(url)
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                         QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self.nam.get(req)
        reply.finished.connect(lambda: self._done(url, reply))

    def _done(self, url: str, reply: QNetworkReply) -> None:
        self.pending.discard(url)
        img = QImage()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            img.loadFromData(reply.readAll())
        reply.deleteLater()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
            self.memory[url] = pm
            self.loaded.emit(url, pm)

    def request_file(self, path: str) -> None:
        key = "file:" + path
        if key in self.memory or key in self.pending:
            return
        thumb = CACHE_DIR / "thumbs" / (hashlib.sha1(path.encode()).hexdigest() + ".png")
        if thumb.exists():
            pm = QPixmap(str(thumb))
            if not pm.isNull():
                self.memory[key] = pm
                self.loaded.emit(key, pm)
                return
        self.pending.add(key)
        job = _ThumbJob(path, 320, 0)
        job.signals.done.connect(lambda frames, _r: self._file_done(key, thumb, frames))
        job.signals.failed.connect(lambda *_: self.pending.discard(key))
        self._local_jobs[key] = job
        media.submit(job)

    def _file_done(self, key: str, thumb, frames: media.Frames) -> None:
        self.pending.discard(key)
        self._local_jobs.pop(key, None)
        if not frames.images:
            return
        pm = QPixmap.fromImage(frames.images[0])
        thumb.parent.mkdir(parents=True, exist_ok=True)
        pm.save(str(thumb), "PNG")
        self.memory[key] = pm
        self.loaded.emit(key, pm)


class _ThumbJob(media.DecodeJob):
    """Decodes only the first frame."""

    def run(self) -> None:
        try:
            from PIL import Image
            with Image.open(self.path) as im:
                im.seek(0)
                frame = im.convert("RGBA")
                frame.thumbnail((self.max_side, self.max_side))
                w, h = frame.size
                img = QImage(frame.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
            self.signals.done.emit(media.Frames([img], [0], QSize(w, h)), self.request)
        except Exception as e:
            self.signals.failed.emit(str(e), self.request)


# -- primitives -----------------------------------------------------------------

def rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_cover(p: QPainter, pm: QPixmap, rect: QRectF, radius: float) -> None:
    """Draw `pm` covering `rect` (centre crop) clipped to rounded corners."""
    p.save()
    p.setClipPath(rounded(rect, radius))
    src = QRectF(pm.rect())
    target_ratio = rect.width() / rect.height()
    if src.width() / src.height() > target_ratio:
        w = src.height() * target_ratio
        src = QRectF(src.x() + (src.width() - w) / 2, src.y(), w, src.height())
    else:
        h = src.width() / target_ratio
        src = QRectF(src.x(), src.y() + (src.height() - h) / 2, src.width(), h)
    p.drawPixmap(rect, pm, src)
    p.restore()


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, checked: bool = False) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        track = rounded(r, r.height() / 2)
        p.fillPath(track, QColor(theme.SURFACE_3))
        if self._pos > 0:
            p.save()
            p.setOpacity(self._pos)
            p.fillPath(track, theme.accent_gradient(r))
            p.restore()
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        off, on = QColor("#9A9AA2"), QColor(theme.ON_ACCENT)
        t = self._pos
        knob = QColor(round(off.red() + (on.red() - off.red()) * t), round(off.green() + (on.green() - off.green()) * t),
                      round(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(44, 24)


class IconButton(QAbstractButton):
    """Round icon-only button using the Fluent icon font."""

    def __init__(self, glyph: str, tooltip: str = "", parent=None, size: int = 34,
                 danger_hover: bool = False) -> None:
        super().__init__(parent)
        self.glyph = glyph
        self.danger = danger_hover
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self._hover or self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3A1622" if self.danger and self._hover else theme.SURFACE_3))
            p.drawRoundedRect(r, 9, 9)
        color = theme.TEXT if self._hover or self.isChecked() else theme.MUTED
        if self.danger and self._hover:
            color = theme.DANGER
        p.setPen(QColor(color))
        p.setFont(theme.icon_font(10.5))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.glyph)
        p.end()


class TitleButton(QAbstractButton):
    """Caption buttons (minimise / maximise / close)."""

    def __init__(self, glyph: str, close: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.glyph, self.close_style = glyph, close
        self.setFixedSize(46, 36)
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        if self._hover:
            p.fillRect(self.rect(), QColor("#E5304A" if self.close_style else theme.SURFACE_2))
        p.setPen(QColor("white" if self._hover else theme.MUTED))
        p.setFont(theme.icon_font(7.5))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.glyph)
        p.end()


class NavButton(QAbstractButton):
    def __init__(self, glyph: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.glyph, self.label = glyph, text
        self.badge = 0
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = 0.0
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def set_badge(self, n: int) -> None:
        self.badge = n
        self.update()

    def _fade(self, target: float) -> None:
        self._anim.stop()
        self._anim.setDuration(theme.ms(160))
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e) -> None:
        self._fade(1.0)

    def leaveEvent(self, e) -> None:
        self._fade(0.0)

    def paintEvent(self, event) -> None:
        # the selected background is a separate NavIndicator that slides between buttons
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        if self._hover > 0 and not self.isChecked():
            bg = QColor(theme.SURFACE)
            bg.setAlphaF(self._hover)
            p.fillPath(rounded(r, 10), bg)
        active = self.isChecked() or self._hover > 0.5
        p.setPen(QColor(theme.TEXT if active else theme.MUTED))
        p.setFont(theme.icon_font(11.5))
        p.drawText(QRectF(r.left() + 14, r.top(), 24, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
        p.setFont(theme.ui_font(10.2, theme.QFont.Weight.DemiBold if self.isChecked() else theme.QFont.Weight.Medium))
        p.drawText(QRectF(r.left() + 50, r.top(), r.width() - 60, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)
        if self.badge:
            text = str(self.badge)
            p.setFont(theme.ui_font(8, theme.QFont.Weight.Bold))
            w = max(20, QFontMetrics(p.font()).horizontalAdvance(text) + 12)
            b = QRectF(r.right() - w - 10, r.center().y() - 10, w, 20)
            p.fillPath(rounded(b, 10), QColor(theme.SURFACE_3))
            p.setPen(QColor(theme.TEXT))
            p.drawText(b, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class NavIndicator(QWidget):
    """The selected-item pill in the sidebar; glides to whichever NavButton is active."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def move_to(self, button: QWidget, animate: bool = True) -> None:
        target = button.geometry()
        self.lower()
        self.show()
        self._anim.stop()
        if not animate or not theme.ANIMATIONS or self.geometry().isEmpty():
            self.setGeometry(target)
            return
        self._anim.setDuration(theme.ms(260))
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        p.fillPath(rounded(r, 10), QColor(theme.SURFACE_2))
        bar = QRectF(r.left(), r.center().y() - 9, 3, 18)
        p.fillPath(rounded(bar, 1.5), theme.accent_gradient(bar))
        p.end()


class FadeStack(QStackedWidget):
    """QStackedWidget whose pages fade in and drift up slightly when shown."""

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return
        super().setCurrentIndex(index)
        if not theme.ANIMATIONS:
            return
        page = self.currentWidget()
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", page)
        fade.setDuration(theme.ms(220))
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        end = page.pos()
        slide = QPropertyAnimation(page, b"pos", page)
        slide.setDuration(theme.ms(280))
        slide.setStartValue(end + QPoint(0, 14))
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        # drop the effect afterwards: it would slow down scrolling
        fade.finished.connect(lambda: page.setGraphicsEffect(None))
        fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        slide.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def fade_in_window(window: QWidget, rise: int = 10, duration: int = 180) -> None:
    """Fade a top-level window in and let it rise a few pixels (used for popups)."""
    if not theme.ANIMATIONS:
        return
    window.setWindowOpacity(0.0)
    fade = QPropertyAnimation(window, b"windowOpacity", window)
    fade.setDuration(theme.ms(duration))
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    if rise:
        end = window.pos()
        slide = QPropertyAnimation(window, b"pos", window)
        slide.setDuration(theme.ms(duration + 60))
        slide.setStartValue(end + QPoint(0, rise))
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        slide.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


# -- cards ------------------------------------------------------------------------

class MediaCard(QWidget):
    """A square thumbnail card with title, meta line, hover action and progress."""

    clicked = Signal(object)
    context = Signal(object, QPoint)
    favorite_clicked = Signal(object)

    W, IMG = 200, 200

    def __init__(self, payload, title: str, meta: str, loader: ImageLoader, image_key: str,
                 parent=None) -> None:
        super().__init__(parent)
        self.payload = payload
        self.title, self.meta = title, meta
        self.loader, self.image_key = loader, image_key
        self.action = ""          # text shown on hover, e.g. "Herunterladen"
        self.action_glyph = ""
        self.badge = ""           # small pill top-left, e.g. "In Bibliothek"
        self.progress = -1.0      # 0..1 while downloading
        self.status = ""
        self.favorite: bool | None = None   # None = card has no favourite star
        self._hover = 0.0
        self._reveal = 1.0                  # 0..1 while the card animates in
        self._img = 1.0 if loader.get(image_key) else 0.0   # thumbnail fade-in
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(theme.ms(160))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reveal_anim = QPropertyAnimation(self, b"reveal", self)
        self._reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._img_anim = QPropertyAnimation(self, b"img", self)
        loader.loaded.connect(self._on_loaded)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def _get_reveal(self) -> float:
        return self._reveal

    def _set_reveal(self, v: float) -> None:
        self._reveal = v
        self.update()

    reveal = Property(float, _get_reveal, _set_reveal)

    def _get_img(self) -> float:
        return self._img

    def _set_img(self, v: float) -> None:
        self._img = v
        self.update()

    img = Property(float, _get_img, _set_img)

    def animate_in(self, delay: int = 0) -> None:
        """Fade + rise into place, optionally after `delay` ms (for staggered grids)."""
        if not theme.ANIMATIONS:
            return
        self._reveal = 0.0
        self._reveal_anim.stop()
        self._reveal_anim.setDuration(theme.ms(340))
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        QTimer.singleShot(delay, self._reveal_anim.start)

    def _on_loaded(self, key: str, pm: QPixmap) -> None:
        if key != self.image_key:
            return
        if theme.ANIMATIONS and self._img < 1.0:
            self._img_anim.stop()
            self._img_anim.setDuration(theme.ms(260))
            self._img_anim.setStartValue(0.0)
            self._img_anim.setEndValue(1.0)
            self._img_anim.start()
        else:
            self._img = 1.0
            self.update()

    def set_state(self, action: str = "", glyph: str = "", badge: str = "", progress: float = -1.0,
                  status: str = "") -> None:
        self.action, self.action_glyph, self.badge = action, glyph, badge
        self.progress, self.status = progress, status
        self.update()

    def heightForWidth(self, w: int) -> int:
        return w + 62

    def enterEvent(self, e) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0)
        self._anim.start()

    def leaveEvent(self, e) -> None:
        self._anim.stop()
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _star_rect(self) -> QRectF:
        return QRectF(self.width() - 42, 10, 32, 32)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or not self.rect().contains(e.position().toPoint()):
            return
        if self.favorite is not None and self._star_rect().contains(e.position()):
            self.favorite_clicked.emit(self.payload)
        else:
            self.clicked.emit(self.payload)

    def contextMenuEvent(self, e) -> None:
        self.context.emit(self.payload, e.globalPos())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._reveal < 1.0:  # entrance animation
            p.setOpacity(self._reveal)
            p.translate(0, (1.0 - self._reveal) * 18)
        w = self.width()
        lift = 3 * self._hover
        img_rect = QRectF(0, 4 - lift, w, w)

        p.fillPath(rounded(img_rect, 14), QColor(theme.SURFACE))
        pm = self.loader.get(self.image_key)
        if pm and self._img < 1.0:
            p.setPen(QColor(theme.DIM))
            p.setFont(theme.icon_font(22))
            p.drawText(img_rect, Qt.AlignmentFlag.AlignCenter, theme.Icon.PHOTO)
        if pm:
            base = p.opacity()
            p.setOpacity(base * self._img)
            draw_cover(p, pm, img_rect, 14)
            p.setOpacity(base)
        else:
            p.setPen(QColor(theme.DIM))
            p.setFont(theme.icon_font(22))
            p.drawText(img_rect, Qt.AlignmentFlag.AlignCenter, theme.Icon.PHOTO)

        # bottom fade so badges/actions stay readable
        if self._hover > 0 or self.progress >= 0:
            grad = QLinearGradient(img_rect.topLeft(), img_rect.bottomLeft())
            grad.setColorAt(0.35, QColor(0, 0, 0, 0))
            alpha = 200 if self.progress >= 0 else int(190 * self._hover)
            grad.setColorAt(1, QColor(8, 8, 10, alpha))
            p.fillPath(rounded(img_rect, 14), grad)

        # thin outline, a touch brighter on hover
        p.setPen(QPen(QColor(255, 255, 255, int(14 + 36 * self._hover)), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(img_rect.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        if self.badge:
            p.setFont(theme.ui_font(8, theme.QFont.Weight.DemiBold))
            fm = p.fontMetrics()
            bw = fm.horizontalAdvance(self.badge) + 30
            b = QRectF(10, img_rect.top() + 10, bw, 22)
            p.fillPath(rounded(b, 11), QColor(10, 10, 18, 215))
            p.setPen(QColor(theme.SUCCESS))
            p.setFont(theme.icon_font(7.5))
            p.drawText(QRectF(b.left() + 8, b.top(), 12, b.height()), Qt.AlignmentFlag.AlignCenter, theme.Icon.CHECK)
            p.setFont(theme.ui_font(8, theme.QFont.Weight.DemiBold))
            p.setPen(QColor(theme.TEXT))
            p.drawText(b.adjusted(22, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, self.badge)

        if self.favorite or (self.favorite is not None and self._hover > 0):
            star = self._star_rect().translated(0, -lift)
            p.save()
            p.setOpacity(1.0 if self.favorite else self._hover)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(10, 10, 12, 200))
            p.drawEllipse(star)
            p.setPen(QColor("#F2C94C" if self.favorite else theme.TEXT))
            p.setFont(theme.icon_font(10))
            p.drawText(star, Qt.AlignmentFlag.AlignCenter, theme.Icon.STAR_FILL if self.favorite else theme.Icon.STAR)
            p.restore()

        if self.progress >= 0:
            bar = QRectF(14, img_rect.bottom() - 22, w - 28, 6)
            p.fillPath(rounded(bar, 3), QColor(255, 255, 255, 40))
            fill = QRectF(bar.left(), bar.top(), max(6.0, bar.width() * self.progress), bar.height())
            p.fillPath(rounded(fill, 3), QColor(theme.ACCENT))
            p.setPen(QColor("white"))
            p.setFont(theme.ui_font(8.5, theme.QFont.Weight.DemiBold))
            label = self.status or tr("Wird heruntergeladen")
            label = f"{int(self.progress * 100)} %  ·  {label}" if self.progress > 0 else label
            fm = p.fontMetrics()
            p.drawText(QRectF(14, bar.top() - 24, w - 28, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(label, Qt.TextElideMode.ElideRight, w - 28))
        elif self.action and self._hover > 0:
            p.save()
            p.setOpacity(self._hover)
            p.setFont(theme.ui_font(9, theme.QFont.Weight.Bold))
            fm = p.fontMetrics()
            pw = fm.horizontalAdvance(self.action) + 46
            pill = QRectF((w - pw) / 2, img_rect.bottom() - 48 + 6 * (1 - self._hover), pw, 34)
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.setBrush(QColor(18, 18, 20, 225))
            p.drawRoundedRect(pill, 17, 17)
            p.setPen(QColor(theme.TEXT))
            p.setFont(theme.icon_font(9.5))
            p.drawText(QRectF(pill.left() + 14, pill.top(), 16, pill.height()), Qt.AlignmentFlag.AlignCenter,
                       self.action_glyph)
            p.setFont(theme.ui_font(9, theme.QFont.Weight.Bold))
            p.drawText(pill.adjusted(34, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, self.action)
            p.restore()

        # title + meta
        p.setPen(QColor(theme.TEXT))
        p.setFont(theme.ui_font(10, theme.QFont.Weight.DemiBold))
        fm = p.fontMetrics()
        p.drawText(QRectF(2, w + 14, w - 4, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.title, Qt.TextElideMode.ElideRight, w - 4))
        p.setPen(QColor(theme.MUTED))
        p.setFont(theme.ui_font(8.6))
        fm = p.fontMetrics()
        p.drawText(QRectF(2, w + 35, w - 4, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.meta, Qt.TextElideMode.ElideRight, w - 4))
        p.end()


class CardGrid(QWidget):
    """Responsive grid: cards stretch to fill the row, then wrap."""

    MIN_W, GAP = 178, 22

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.cards: list[QWidget] = []

    def clear(self) -> None:
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        self.relayout()

    def add(self, card: QWidget) -> None:
        card.setParent(self)
        card.show()
        self.cards.append(card)

    def relayout(self) -> None:
        width = max(1, self.width())
        cols = max(1, (width + self.GAP) // (self.MIN_W + self.GAP))
        cw = (width - self.GAP * (cols - 1)) / cols
        ch = cw + 62
        shown = [c for c in self.cards if not c.isHidden()]
        for i, card in enumerate(shown):
            row, col = divmod(i, cols)
            card.setGeometry(round(col * (cw + self.GAP)), round(row * (ch + self.GAP)), round(cw), round(ch))
        rows = (len(shown) + cols - 1) // cols
        self.setMinimumHeight(int(rows * (ch + self.GAP)))

    def resizeEvent(self, e) -> None:
        self.relayout()


# -- confirm dialog ---------------------------------------------------------------

class ConfirmDialog(QDialog):
    """Dark, frameless yes/no popup. Used before anything gets deleted."""

    def __init__(self, parent: QWidget, title: str, text: str, confirm: str = tr("Löschen"),
                 cancel: str = tr("Abbrechen"), danger: bool = True, field: str | None = None) -> None:
        super().__init__(parent)
        # stays on top so it can't hide behind always-on-top overlays
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
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(12)
        icon = QLabel(theme.Icon.WARNING if danger else theme.Icon.SPARKLE)
        icon.setFont(theme.icon_font(15))
        icon.setStyleSheet(f"color:{theme.DANGER if danger else theme.MUTED}; background:transparent;")
        head.addWidget(icon)
        t = QLabel(title)
        t.setWordWrap(True)
        t.setStyleSheet("font-size:12pt; font-weight:600; background:transparent;")
        head.addWidget(t, 1)
        lay.addLayout(head)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{theme.MUTED}; background:transparent; line-height:140%;")
        body.setVisible(bool(text))
        lay.addWidget(body)
        self.edit: QLineEdit | None = None
        if field is not None:
            self.edit = QLineEdit(field)
            self.edit.setStyleSheet("padding-left: 12px;")
            self.edit.selectAll()
            lay.addSpacing(4)
            lay.addWidget(self.edit)
        lay.addSpacing(10)

        buttons = QHBoxLayout()
        buttons.addStretch()
        no = QPushButton(cancel)
        no.clicked.connect(self.reject)
        yes = QPushButton(confirm)
        yes.setObjectName("DangerSolid" if danger else "Primary")
        yes.setStyleSheet("QPushButton#DangerSolid { background:#8E3B43; border:1px solid #A5464F; color:white; }"
                          "QPushButton#DangerSolid:hover { background:#A5464F; }")
        yes.clicked.connect(self.accept)
        for b in (no, yes):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumWidth(110)
            buttons.addWidget(b)
        lay.addLayout(buttons)
        if self.edit is not None:
            yes.setDefault(True)
            self.edit.returnPressed.connect(self.accept)
            self.edit.setFocus()
        else:
            no.setDefault(True)   # Enter never deletes by accident
            no.setFocus()
        self.setFixedWidth(460)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        parent = self.parentWidget()
        if parent and parent.isVisible():
            self.move(parent.geometry().center() - self.rect().center())
        fade_in_window(self)

    @staticmethod
    def ask(parent: QWidget, title: str, text: str, confirm: str = tr("Löschen"), cancel: str = tr("Abbrechen"),
            danger: bool = True) -> bool:
        return ConfirmDialog(parent, title, text, confirm, cancel, danger).exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def ask_text(parent: QWidget, title: str, value: str = "", confirm: str = tr("Speichern"), text: str = "") -> str | None:
        dlg = ConfirmDialog(parent, title, text, confirm, danger=False, field=value)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.edit.text().strip():
            return dlg.edit.text().strip()
        return None


class ProgressDialog(QDialog):
    """Frameless progress popup (used while an update downloads). Emits `cancelled`."""

    cancelled = Signal()

    def __init__(self, parent: QWidget, title: str) -> None:
        super().__init__(parent)
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
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        t = QLabel(title)
        t.setStyleSheet("font-size:12pt; font-weight:600; background:transparent;")
        lay.addWidget(t)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(f"QProgressBar {{ background:{theme.SURFACE_3}; border:none; border-radius:3px; }}"
                               f"QProgressBar::chunk {{ background:{theme.ACCENT}; border-radius:3px; }}")
        lay.addWidget(self.bar)
        self.status = QLabel(tr("Wird vorbereitet …"))
        self.status.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch()
        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        row.addWidget(self.cancel_btn)
        lay.addLayout(row)
        self.setFixedWidth(440)

    def set_progress(self, done: int, total: int) -> None:
        if total:
            self.bar.setValue(int(done * 1000 / total))
            self.status.setText(tr("{a0} von {a1}", a0=human_size(done), a1=human_size(total)))
        else:
            self.status.setText(human_size(done))

    def showEvent(self, e) -> None:
        super().showEvent(e)
        parent = self.parentWidget()
        if parent and parent.isVisible():
            self.move(parent.geometry().center() - self.rect().center())
        fade_in_window(self)


# -- toasts ---------------------------------------------------------------------

class Toast(QLabel):
    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        color = {"ok": theme.SUCCESS, "error": theme.DANGER}.get(kind, theme.MUTED)
        glyph = {"ok": theme.Icon.CHECK, "error": theme.Icon.CLOSE}.get(kind, theme.Icon.SPARKLE)
        self.setText(f'<span style="font-family:\'{theme.ICON_FONT}\'; color:{color}">{glyph}</span>'
                     f'&nbsp;&nbsp;{text}')
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setWordWrap(True)
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)
        self.setStyleSheet(f"background:{theme.SURFACE_2}; border:1px solid {theme.BORDER};"
                           f"border-left:3px solid {color}; border-radius:12px; padding:12px 16px;"
                           f"font-size:9.5pt;")
        self.adjustSize()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(theme.ms(220))
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        QTimer.singleShot(3800, self._out)
        self.show()
        self.raise_()

    def _out(self) -> None:
        self._fade.setDirection(QPropertyAnimation.Direction.Backward)
        self._fade.finished.connect(self.deleteLater)
        self._fade.start()


class ToastHost(QObject):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.window = window
        self.toasts: list[Toast] = []

    def show(self, text: str, kind: str = "info") -> None:
        t = Toast(self.window, text, kind)
        t.destroyed.connect(lambda *_: self._forget(t))
        self.toasts.append(t)
        self.reposition()

    def _forget(self, t: Toast) -> None:
        if t in self.toasts:
            self.toasts.remove(t)
        self.reposition()

    def reposition(self) -> None:
        try:
            y = self.window.height() - 24
        except RuntimeError:  # window already gone during shutdown
            return
        for t in reversed(self.toasts):
            try:
                y -= t.height()
                target = QPoint(self.window.width() - t.width() - 24, y)
                y -= 10
                placed = getattr(t, "_placed", False)
                t._placed = True
                if not theme.ANIMATIONS or (placed and t.pos() == target):
                    t.move(target)
                    continue
                # new toasts slide in from the right, existing ones glide to their new slot
                start = target + QPoint(40, 0) if not placed else t.pos()
                anim = QPropertyAnimation(t, b"pos", t)
                anim.setDuration(theme.ms(260))
                anim.setStartValue(start)
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            except RuntimeError:
                pass
