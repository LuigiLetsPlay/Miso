"""Download a workshop item straight from Steam's content CDN.

Same steps SteamCMD's `workshop_download_item` performs:
  1. anonymous CM login -> depot key + manifest request code
  2. fetch + decrypt the depot manifest (file list, chunk list)
  3. fetch each chunk, AES-decrypt, decompress, write into place
"""
from __future__ import annotations

import base64
import io
import lzma
import os
import random
import struct
import threading
import urllib.error
import urllib.request
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .cm import API, USER_AGENT, CMClient, SteamError, http_json
from .protobuf import Message
from ..i18n import tr

try:
    from compression import zstd
except ImportError:  # Python < 3.14
    zstd = None

MAGIC_PAYLOAD = 0x71F617D0
MAGIC_METADATA = 0x1F4812BE
MAGIC_SIGNATURE = 0x1B81B817
MAGIC_END = 0x32C415AB
FLAG_DIRECTORY = 64


class Cancelled(Exception):
    pass


@dataclass
class Chunk:
    sha: bytes
    checksum: int
    offset: int
    size: int
    compressed: int


@dataclass
class FileEntry:
    name: str
    size: int
    flags: int
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def is_dir(self) -> bool:
        return bool(self.flags & FLAG_DIRECTORY)


# -- crypto / compression ---------------------------------------------------

def symmetric_decrypt(data: bytes, key: bytes) -> bytes:
    ecb = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    iv = ecb.update(data[:16]) + ecb.finalize()
    cbc = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = cbc.update(data[16:]) + cbc.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return unpad.update(plain) + unpad.finalize()


def decompress_chunk(data: bytes) -> bytes:
    if data[:3] == b"VZa":
        # VZip: 'VZa' + u32 + 5 byte LZMA props + stream + u32 crc + u32 size + 'zv'
        props = data[7:12]
        size, = struct.unpack_from("<I", data, len(data) - 6)
        alone = props + struct.pack("<Q", size) + data[12:-10]
        return lzma.decompress(alone, format=lzma.FORMAT_ALONE)
    if data[:4] == b"VSZa":
        if zstd is None:
            raise SteamError(tr("Zstd-Chunk benötigt Python 3.14+"))
        dec = zstd.ZstdDecompressor()
        return dec.decompress(data[8:])
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return z.read(z.namelist()[0])
    raise SteamError(tr("Unbekanntes Chunk-Format"))


# -- CDN ----------------------------------------------------------------------

def cdn_hosts() -> list[str]:
    data = http_json(f"{API}/IContentServerDirectoryService/GetServersForSteamPipe/v1/?cell_id=0")
    servers = [s for s in data["response"]["servers"] if s.get("type") in ("SteamCache", "CDN")]
    servers.sort(key=lambda s: s.get("weighted_load", 100))
    hosts = [s.get("vhost") or s["host"] for s in servers]
    return hosts or ["steampipe.akamaized.net"]


def http_get(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_manifest(raw: bytes, key: bytes) -> tuple[list[FileEntry], Message]:
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    payload = metadata = None
    pos = 0
    while pos + 8 <= len(raw):
        magic, length = struct.unpack_from("<II", raw, pos)
        pos += 8
        if magic == MAGIC_END:
            break
        section = raw[pos:pos + length]
        pos += length
        if magic == MAGIC_PAYLOAD:
            payload = Message(section)
        elif magic == MAGIC_METADATA:
            metadata = Message(section)
    if payload is None or metadata is None:
        raise SteamError(tr("Manifest ist beschädigt"))

    encrypted_names = bool(metadata.int(4))
    files = []
    for m in payload.msgs(1):
        name = m.str(1)
        if encrypted_names:
            name = symmetric_decrypt(base64.b64decode(name), key).rstrip(b"\0").decode("utf-8", "replace")
        chunks = [Chunk(c.get(1), c.int(2), c.int(3), c.int(4), c.int(5)) for c in m.msgs(6)]
        files.append(FileEntry(name.replace("\\", "/"), m.int(2), m.int(3), chunks))
    return files, metadata


# -- downloader -----------------------------------------------------------------

class WorkshopDownloader:
    """Downloads one workshop item into `target_dir`.

    `progress(done_bytes, total_bytes)` and `log(text)` are called from worker
    threads; `cancel_event` aborts the download.
    """

    def __init__(self, app_id: int, log=print, progress=None, cancel_event: threading.Event | None = None,
                 workers: int = 8) -> None:
        self.app_id = app_id
        self.log = log
        self.progress = progress or (lambda done, total: None)
        self.cancel = cancel_event or threading.Event()
        self.workers = workers

    def _check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def download(self, manifest_id: int, target_dir: Path, accept=None) -> list[Path]:
        """Download into `target_dir`. Only files for which `accept(name)` is true are fetched;
        everything else (scripts, executables, …) never touches the disk."""
        depot = self.app_id  # workshop content lives in the app's own depot
        with CMClient(log=self.log) as cm:
            self._check()
            key = cm.depot_key(self.app_id, depot)
            code = cm.manifest_request_code(self.app_id, depot, manifest_id)
        self._check()

        hosts = cdn_hosts()
        self.log(tr("Lade Manifest …"))
        raw = None
        for host in hosts[:4]:
            try:
                raw = http_get(f"https://{host}/depot/{depot}/manifest/{manifest_id}/5/{code}")
                break
            except urllib.error.URLError:
                continue
        if raw is None:
            raise SteamError(tr("Manifest konnte nicht geladen werden"))
        files, _ = parse_manifest(raw, key)

        root = target_dir.resolve()
        wanted = []
        for f in files:
            if f.is_dir:
                continue
            dest = (target_dir / f.name).resolve()
            if root not in dest.parents:          # "..\..\evil.exe" and absolute paths
                continue
            if accept and not accept(f.name):
                continue
            wanted.append(f)
        skipped = sum(1 for f in files if not f.is_dir) - len(wanted)
        if skipped:
            self.log(tr("{a0} Datei(en) übersprungen (kein Bild)", a0=skipped))
        if not wanted:
            raise SteamError(tr("Item enthält keine Bilder"))
        files = wanted

        total = sum(f.size for f in files if not f.is_dir)
        done = 0
        lock = threading.Lock()
        self.progress(0, total)
        self.log(tr("{a0} Datei(en), {a1:.1f} MB", a0=len(files), a1=total / 1048576))

        target_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        handles: dict[str, object] = {}
        jobs: list[tuple[FileEntry, Chunk]] = []
        for f in files:
            path = target_dir / f.name
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(path, "wb")
            fh.truncate(f.size)
            handles[f.name] = fh
            written.append(path)
            jobs.extend((f, c) for c in f.chunks)

        def fetch(chunk: Chunk) -> bytes:
            last = None
            for attempt in range(5):
                self._check()
                host = random.choice(hosts[:6])
                try:
                    data = http_get(f"https://{host}/depot/{depot}/chunk/{chunk.sha.hex()}")
                    plain = decompress_chunk(symmetric_decrypt(data, key))
                    if len(plain) != chunk.size:
                        raise SteamError(tr("Chunk hat falsche Größe"))
                    if zlib.adler32(plain, 0) != chunk.checksum:
                        raise SteamError(tr("Chunk-Prüfsumme stimmt nicht"))
                    return plain
                except (urllib.error.URLError, SteamError, OSError, ValueError) as e:
                    last = e
            raise SteamError(tr("Chunk-Download fehlgeschlagen: {a0}", a0=last))

        def work(entry: FileEntry, chunk: Chunk) -> None:
            nonlocal done
            data = fetch(chunk)
            with lock:
                fh = handles[entry.name]
                fh.seek(chunk.offset)
                fh.write(data)
                done += len(data)
                self.progress(done, total)

        try:
            with ThreadPoolExecutor(self.workers) as pool:
                futures = [pool.submit(work, f, c) for f, c in jobs]
                try:
                    for fut in as_completed(futures):
                        fut.result()
                except BaseException:
                    self.cancel.set()
                    for fut in futures:
                        fut.cancel()
                    raise
        except BaseException:
            for fh in handles.values():
                fh.close()
            for p in written:
                try:
                    os.remove(p)
                except OSError:
                    pass
            raise
        for fh in handles.values():
            fh.close()
        return written
