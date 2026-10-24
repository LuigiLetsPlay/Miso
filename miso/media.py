"""Decode GIF / APNG / WebP / still images into Qt frames.

Frames are cached at the size they are displayed at (not their native size),
so a 221-frame 800px APNG doesn't eat half a gigabyte of RAM. When an overlay
grows past the cached resolution it simply asks for a new decode.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, Signal
from PySide6.QtGui import QImage

SUPPORTED = (".gif", ".png", ".apng", ".webp", ".jpg", ".jpeg", ".bmp")
FRAME_BUDGET = 320 * 1024 * 1024  # max bytes of decoded frames per overlay
MIN_DURATION = 10  # ms; browsers clamp tiny GIF delays the same way


def is_supported(path: str) -> bool:
    return path.lower().endswith(SUPPORTED)


REAL_FORMATS = {"GIF", "PNG", "WEBP", "JPEG", "BMP"}   # APNG reports as PNG
MAX_SIDE = 16384


def is_real_image(path) -> bool:
    """Check the file *content* (not just the extension) is a sane image. Never executes anything."""
    if not is_supported(str(path)):
        return False
    try:
        with Image.open(path) as im:
            return im.format in REAL_FORMATS and 0 < im.width <= MAX_SIDE and 0 < im.height <= MAX_SIDE
    except Exception:
        return False


@dataclass
class MediaInfo:
    width: int
    height: int
    frames: int


def probe(path: str) -> MediaInfo:
    with Image.open(path) as im:
        return MediaInfo(im.width, im.height, getattr(im, "n_frames", 1))


@dataclass
class Frames:
    images: list[QImage]
    durations: list[int]
    native: QSize

    @property
    def size(self) -> QSize:
        return self.images[0].size() if self.images else QSize()


def decode(path: str, max_side: int, cancelled=lambda: False) -> Frames:
    with Image.open(path) as im:
        native = QSize(im.width, im.height)
        n = getattr(im, "n_frames", 1)
        # fit into the requested size, never upscale, and respect the RAM budget
        scale = min(1.0, max_side / max(im.width, im.height))
        per_frame = im.width * im.height * 4 * scale * scale
        if per_frame * n > FRAME_BUDGET:
            scale *= (FRAME_BUDGET / (per_frame * n)) ** 0.5
        w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))

        images, durations = [], []
        for i in range(n):
            if cancelled():
                break
            im.seek(i)
            frame = im.convert("RGBA")
            if n == 1:  # photos may be stored rotated
                frame = ImageOps.exif_transpose(frame)
                if frame.size == (im.height, im.width) and im.width != im.height:
                    w, h = h, w
                    native = QSize(im.height, im.width)
            if frame.size != (w, h):
                frame = frame.resize((w, h), Image.Resampling.LANCZOS if n < 60 else Image.Resampling.BILINEAR)
            qimg = QImage(frame.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
            images.append(qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
            duration = im.info.get("duration") or 100
            durations.append(max(MIN_DURATION, int(round(duration))))
        return Frames(images, durations, native)


class _Signals(QObject):
    done = Signal(object, int)   # Frames, request id
    failed = Signal(str, int)


class DecodeJob(QRunnable):
    def __init__(self, path: str, max_side: int, request: int) -> None:
        super().__init__()
        self.path, self.max_side, self.request = path, max_side, request
        self.signals = _Signals()
        self.cancelled = False

    def run(self) -> None:
        try:
            frames = decode(self.path, self.max_side, lambda: self.cancelled)
            if not self.cancelled:
                self.signals.done.emit(frames, self.request)
        except Exception as e:  # corrupt or unsupported file
            self.signals.failed.emit(str(e), self.request)


_pool = QThreadPool()
_pool.setMaxThreadCount(2)


def submit(job: DecodeJob) -> None:
    _pool.start(job)
