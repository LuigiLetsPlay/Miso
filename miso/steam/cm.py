"""Tiny Steam CM (connection manager) client over WebSocket.

Just enough of the protocol to log in anonymously — exactly what
`steamcmd +login anonymous` does — and ask for the two secrets needed to
download a workshop item: the depot decryption key and a manifest request
code.
"""
from __future__ import annotations

import gzip
import json
import random
import struct
import time
import urllib.request

from websockets.sync.client import connect

from .protobuf import Message, Writer
from ..i18n import tr

PROTO_MASK = 0x80000000

# EMsg values
MULTI = 1
SERVICE_METHOD_RESPONSE = 147
SERVICE_METHOD_CALL = 151
CLIENT_HEARTBEAT = 703
CLIENT_LOGON_RESPONSE = 751
CLIENT_LOGGED_OFF = 757
CLIENT_GET_DEPOT_KEY = 5438
CLIENT_GET_DEPOT_KEY_RESPONSE = 5439
CLIENT_LOGON = 5514
CLIENT_HELLO = 9805

PROTOCOL_VERSION = 65580
ANON_STEAMID = (1 << 56) | (10 << 52)  # universe Public, type AnonUser
API = "https://api.steampowered.com"
USER_AGENT = "Miso/1.0"


class SteamError(RuntimeError):
    pass


def http_json(url: str, timeout: float = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def cm_servers() -> list[str]:
    data = http_json(f"{API}/ISteamDirectory/GetCMListForConnect/v1/?cellid=0&cmtype=websockets")
    servers = [s["endpoint"] for s in data["response"]["serverlist"] if s.get("type") == "websockets"]
    if not servers:
        raise SteamError(tr("Keine Steam-Server gefunden"))
    return servers


class CMClient:
    def __init__(self, log=print) -> None:
        self.log = log
        self.ws = None
        self.steamid = ANON_STEAMID
        self.session_id = 0
        self.heartbeat = 9.0
        self._last_send = 0.0
        self._job = random.randint(1, 1 << 30)
        self._pending: list[tuple[int, Message, bytes]] = []

    # -- connection -------------------------------------------------------
    def connect(self) -> None:
        last_error = None
        for endpoint in cm_servers()[:5]:
            try:
                self.log(tr("Verbinde mit Steam ({a0}) …", a0=endpoint.split(':')[0]))
                self.ws = connect(f"wss://{endpoint}/cmsocket/", open_timeout=10,
                                  max_size=None, user_agent_header=USER_AGENT)
                return
            except Exception as e:  # try the next server
                last_error = e
        raise SteamError(tr("Verbindung zu Steam fehlgeschlagen: {a0}", a0=last_error))

    def close(self) -> None:
        if self.ws is not None:
            try:
                self.ws.close()
            finally:
                self.ws = None

    def __enter__(self) -> "CMClient":
        self.connect()
        self.login_anonymous()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- framing ----------------------------------------------------------
    def _send(self, emsg: int, body: bytes, job_id: int | None = None, job_name: str | None = None) -> None:
        header = Writer().fixed64(1, self.steamid).varint(2, self.session_id)
        if job_id is not None:
            header.fixed64(10, job_id)
        if job_name:
            header.string(12, job_name)
        header = header.build()
        packet = struct.pack("<II", emsg | PROTO_MASK, len(header)) + header + body
        self.ws.send(packet)
        self._last_send = time.monotonic()

    def _keepalive(self) -> None:
        if self.session_id and time.monotonic() - self._last_send > self.heartbeat / 2:
            self._send(CLIENT_HEARTBEAT, b"")

    def _unpack(self, packet: bytes) -> None:
        raw_emsg, = struct.unpack_from("<I", packet, 0)
        emsg = raw_emsg & ~PROTO_MASK
        if not raw_emsg & PROTO_MASK:
            return  # legacy struct messages — nothing we need
        hlen, = struct.unpack_from("<I", packet, 4)
        header = Message(packet[8:8 + hlen])
        body = packet[8 + hlen:]
        if emsg == MULTI:
            multi = Message(body)
            payload = multi.get(2, b"")
            if multi.int(1):
                payload = gzip.decompress(payload)
            pos = 0
            while pos < len(payload):
                size, = struct.unpack_from("<I", payload, pos)
                self._unpack(payload[pos + 4:pos + 4 + size])
                pos += 4 + size
            return
        self._pending.append((emsg, header, body))

    def _wait(self, match, timeout: float = 20) -> tuple[Message, bytes]:
        deadline = time.monotonic() + timeout
        while True:
            for i, (emsg, header, body) in enumerate(self._pending):
                if emsg == CLIENT_LOGGED_OFF:
                    raise SteamError(tr("Von Steam abgemeldet (EResult {a0})", a0=Message(body).int(1)))
                if match(emsg, header):
                    del self._pending[i]
                    return header, body
            self._pending.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SteamError(tr("Steam antwortet nicht (Timeout)"))
            self._keepalive()
            try:
                packet = self.ws.recv(timeout=min(remaining, 2.0))
            except TimeoutError:
                continue
            self._unpack(packet)

    # -- API --------------------------------------------------------------
    def login_anonymous(self) -> None:
        self._send(CLIENT_HELLO, Writer().varint(1, PROTOCOL_VERSION).build())
        body = (Writer()
                .varint(1, PROTOCOL_VERSION)
                .varint(3, 0)            # cell_id
                .varint(5, 1771)         # client_package_version
                .string(6, "english")
                .varint(7, 16)           # client_os_type: Windows 10
                .varint(8, False)        # should_remember_password
                .build())
        self._send(CLIENT_LOGON, body)
        header, body = self._wait(lambda e, h: e == CLIENT_LOGON_RESPONSE)
        resp = Message(body)
        result = resp.signed(1, 2)
        if result != 1:
            raise SteamError(tr("Anonymer Login fehlgeschlagen (EResult {a0})", a0=result))
        self.steamid = header.int(1, self.steamid)
        self.session_id = header.int(2)
        self.heartbeat = float(resp.signed(3, 9) or 9)
        self.log(tr("Anonym bei Steam angemeldet"))

    def call(self, method: str, body: bytes) -> Message:
        self._job += 1
        job = self._job
        self._send(SERVICE_METHOD_CALL, body, job_id=job, job_name=method)
        header, resp = self._wait(lambda e, h: e == SERVICE_METHOD_RESPONSE and h.int(11) == job)
        result = header.signed(13, 2)
        if result != 1:
            raise SteamError(tr("{a0} fehlgeschlagen (EResult {a1})", a0=method, a1=result))
        return Message(resp)

    def depot_key(self, app_id: int, depot_id: int) -> bytes:
        self._job += 1
        self._send(CLIENT_GET_DEPOT_KEY, Writer().varint(1, depot_id).varint(2, app_id).build(), job_id=self._job)
        _, body = self._wait(lambda e, h: e == CLIENT_GET_DEPOT_KEY_RESPONSE)
        resp = Message(body)
        result = resp.signed(1, 2)
        if result != 1:
            raise SteamError(tr("Kein Zugriff auf Depot {a0} (EResult {a1})", a0=depot_id, a1=result))
        return resp.get(3)

    def manifest_request_code(self, app_id: int, depot_id: int, manifest_id: int, branch: str = "public") -> int:
        body = (Writer().varint(1, app_id).varint(2, depot_id)
                .varint(3, manifest_id).string(4, branch).build())
        return self.call("ContentServerDirectory.GetManifestRequestCode#1", body).int(1)
