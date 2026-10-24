"""Getting images into the library: files, browser drag & drop, Ctrl+V.

Browsers put the image URL (and an HTML <img>) on drags and copies. We prefer
the URL and download the original, so animated GIFs stay animated; a raw
bitmap from the clipboard is only the fallback.
"""
from __future__ import annotations

import base64
import html
import re
import shutil
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QMimeData, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from . import media
from .store import UPLOAD_DIR

MAX_BYTES = 200 * 1024 * 1024
FORMAT_EXT = {"GIF": ".gif", "PNG": ".png", "WEBP": ".webp", "JPEG": ".jpg", "BMP": ".bmp"}
_IMG_SRC = re.compile(r"""<img[^>]+src\s*=\s*["']([^"']+)["']""", re.I)


def sources_from_mime(mime: QMimeData) -> list[tuple[str, object]]:
    """Return [("file", path) | ("url", url) | ("image", QImage)] in order of preference."""
    out: list[tuple[str, object]] = []
    for u in mime.urls() if mime.hasUrls() else []:
        if u.isLocalFile():
            out.append(("file", u.toLocalFile()))
        elif u.scheme() in ("http", "https", "data"):
            out.append(("url", u.toString()))
    if not out and mime.hasHtml():
        for src in _IMG_SRC.findall(mime.html()):
            out.append(("url", html.unescape(src)))
    if not out and mime.hasText():
        text = mime.text().strip()
        if re.match(r"^(https?://|data:image/)\S+$", text):
            out.append(("url", text))
    if not out and mime.hasImage():
        img = mime.imageData()
        if isinstance(img, QImage) and not img.isNull():
            out.append(("image", img))
    return out


def _unique(name: str) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "bild"
    return UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe[-80:]}"


def _finish(tmp: Path, title: str) -> tuple[str, str]:
    """Validate a downloaded/pasted file and give it the right extension."""
    try:
        with Image.open(tmp) as im:
            fmt = im.format
    except Exception:
        tmp.unlink(missing_ok=True)
        raise ValueError("Das ist kein unterstütztes Bild")
    ext = FORMAT_EXT.get(fmt or "")
    if not ext:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"Format {fmt} wird nicht unterstützt")
    final = tmp.with_name(Path(tmp.name).stem + ext) if tmp.suffix.lower() != ext else tmp
    if final != tmp:
        tmp.replace(final)
    return str(final), title


def copy_file(path: str) -> tuple[str, str]:
    src = Path(path)
    if not media.is_supported(path) or not src.is_file():
        raise ValueError(f"„{src.name}“ wird nicht unterstützt")
    dest = _unique(src.name)
    shutil.copy2(src, dest)
    return str(dest), src.stem


def save_image(img: QImage) -> tuple[str, str]:
    dest = _unique("eingefuegt.png")
    if not img.save(str(dest), "PNG"):
        raise ValueError("Bild aus der Zwischenablage konnte nicht gespeichert werden")
    return str(dest), "Eingefügtes Bild"


def download(url: str) -> tuple[str, str]:
    if url.startswith("data:"):
        header, _, payload = url.partition(",")
        data = base64.b64decode(payload) if ";base64" in header else urllib.parse.unquote_to_bytes(payload)
        tmp = _unique("eingefuegt.bin")
        tmp.write_bytes(data)
        return _finish(tmp, "Eingefügtes Bild")

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
        "Accept": "image/gif,image/apng,image/webp,image/*,*/*;q=0.8",
    })
    name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name or "bild"
    tmp = _unique(Path(name).stem + ".part")
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
            total = 0
            while chunk := r.read(1 << 16):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise ValueError("Datei ist größer als 200 MB")
                f.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    title = Path(name).stem if name != "bild" else "Bild aus dem Web"
    return _finish(tmp, title[:60])


class _Signals(QObject):
    done = Signal(str, str)      # path, title
    failed = Signal(str)


class ImportJob(QRunnable):
    def __init__(self, kind: str, value) -> None:
        super().__init__()
        self.kind, self.value = kind, value
        self.signals = _Signals()

    def run(self) -> None:
        try:
            if self.kind == "file":
                path, title = copy_file(self.value)
            elif self.kind == "url":
                path, title = download(self.value)
            else:
                path, title = save_image(self.value)
            self.signals.done.emit(path, title)
        except Exception as e:
            try:
                self.signals.failed.emit(str(e))
            except RuntimeError:
                pass


class Importer(QObject):
    """Runs imports in the background; emits `imported(path, title)` per finished file."""

    imported = Signal(str, str)
    failed = Signal(str)
    busy = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self._jobs: set[_Signals] = set()

    def run(self, sources: list[tuple[str, object]]) -> int:
        for kind, value in sources:
            job = ImportJob(kind, value)
            sig = job.signals
            self._jobs.add(sig)
            sig.done.connect(lambda p, t, s=sig: self._done(s, p, t))
            sig.failed.connect(lambda m, s=sig: self._failed(s, m))
            self.pool.start(job)
        self.busy.emit(len(self._jobs))
        return len(sources)

    def _done(self, sig, path: str, title: str) -> None:
        self._jobs.discard(sig)
        self.imported.emit(path, title)
        self.busy.emit(len(self._jobs))

    def _failed(self, sig, message: str) -> None:
        self._jobs.discard(sig)
        self.failed.emit(message)
        self.busy.emit(len(self._jobs))
