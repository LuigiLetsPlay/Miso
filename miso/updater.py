"""Updates from GitHub releases.

Checks /releases/latest, downloads Miso-Setup.exe, verifies its size and the
SHA-256 digest GitHub publishes, then runs it silently. The installer closes
Miso (AppMutex), updates the files and starts the new version again.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from . import __version__

REPO = "LuigiLetsPlay/Miso"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SETUP_ASSET = "Miso-Setup.exe"
USER_AGENT = f"Miso/{__version__}"


@dataclass
class Release:
    version: str
    notes: str
    page_url: str
    setup_url: str
    size: int
    sha256: str


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text)
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def is_installed() -> bool:
    """Only an installed copy (with Inno's uninstaller next to it) can update itself."""
    return getattr(sys, "frozen", False) and Path(sys.executable).with_name("unins000.exe").exists()


def fetch_latest() -> Release | None:
    req = urllib.request.Request(API, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    asset = next((a for a in data.get("assets", []) if a.get("name") == SETUP_ASSET), None)
    if not asset:
        return None
    digest = asset.get("digest") or ""
    return Release(
        version=(data.get("tag_name") or "").lstrip("vV"),
        notes=data.get("body") or "",
        page_url=data.get("html_url") or f"https://github.com/{REPO}/releases",
        setup_url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
    )


def download(release: Release, progress, cancel: threading.Event) -> Path:
    folder = Path(tempfile.gettempdir()) / "Miso-Update"
    folder.mkdir(exist_ok=True)
    target = folder / f"Miso-Setup-{release.version}.exe"
    req = urllib.request.Request(release.setup_url, headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as r, open(target, "wb") as f:
            total = int(r.headers.get("Content-Length") or release.size or 0)
            while chunk := r.read(1 << 16):
                if cancel.is_set():
                    raise InterruptedError("Abgebrochen")
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                progress(done, total)
        if release.size and done != release.size:
            raise ValueError("Download unvollständig")
        if release.sha256 and sha.hexdigest() != release.sha256:
            raise ValueError("Prüfsumme stimmt nicht, Update wurde verworfen")
        with open(target, "rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("Download ist keine Windows-Datei")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def launch_installer(path: Path) -> None:
    """Start the setup (visible progress, no questions). It waits until Miso has quit, installs and restarts it."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     close_fds=True, cwd=os.path.dirname(path))


# -- Qt plumbing --------------------------------------------------------------------

class _Signals(QObject):
    checked = Signal(object)          # Release | None
    check_failed = Signal(str)
    progress = Signal(int, int)
    downloaded = Signal(str)
    download_failed = Signal(str)


class _CheckJob(QRunnable):
    def __init__(self, sig: _Signals) -> None:
        super().__init__()
        self.sig = sig

    def run(self) -> None:
        try:
            self.sig.checked.emit(fetch_latest())
        except Exception as e:
            try:
                self.sig.check_failed.emit(str(e))
            except RuntimeError:
                pass


class _DownloadJob(QRunnable):
    def __init__(self, sig: _Signals, release: Release, cancel: threading.Event) -> None:
        super().__init__()
        self.sig, self.release, self.cancel = sig, release, cancel

    def run(self) -> None:
        try:
            path = download(self.release, lambda d, t: self.sig.progress.emit(d, t), self.cancel)
            self.sig.downloaded.emit(str(path))
        except BaseException as e:
            try:
                self.sig.download_failed.emit(str(e))
            except RuntimeError:
                pass


class Updater(QObject):
    """available(Release) when a newer version exists; up_to_date() / failed(msg) after a manual check."""

    available = Signal(object)
    up_to_date = Signal()
    failed = Signal(str)
    progress = Signal(int, int)
    downloaded = Signal(str)
    download_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.sig = _Signals()
        self.sig.checked.connect(self._on_checked)
        self.sig.check_failed.connect(self.failed)
        self.sig.progress.connect(self.progress)
        self.sig.downloaded.connect(self.downloaded)
        self.sig.download_failed.connect(self.download_failed)
        self.latest: Release | None = None
        self.checking = False
        self.cancel = threading.Event()

    def check(self) -> None:
        if not self.checking:
            self.checking = True
            self.pool.start(_CheckJob(self.sig))

    def _on_checked(self, release: Release | None) -> None:
        self.checking = False
        if release and is_newer(release.version):
            self.latest = release
            self.available.emit(release)
        else:
            self.up_to_date.emit()

    def download(self, release: Release) -> None:
        self.cancel = threading.Event()
        self.pool.start(_DownloadJob(self.sig, release, self.cancel))
