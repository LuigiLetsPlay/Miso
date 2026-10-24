"""Persistent state: settings, library and placed overlays (JSON in %APPDATA%)."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from . import hotkeys
from .nsfw import is_nsfw

APP_NAME = "Miso"
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "cache"
WORKSHOP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "workshop"
UPLOAD_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "uploads"
CONFIG_FILE = DATA_DIR / "config.json"


def _load(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class LibraryItem:
    path: str
    title: str
    kind: str = "local"            # "local" | "upload" | "workshop"
    workshop_id: str = ""
    preview_url: str = ""
    added: float = field(default_factory=time.time)
    last_used: float = 0.0         # last time it was on screen (0 = never)
    favorite: bool = False

    @property
    def key(self) -> str:
        return f"ws:{self.workshop_id}" if self.workshop_id else f"file:{self.path}"

    @property
    def used(self) -> float:
        return max(self.last_used, self.added)

    @property
    def deletable(self) -> bool:
        """Only files Miso owns get deleted from disk; plain links are just forgotten."""
        return self.kind in ("workshop", "upload")

    def size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0


@dataclass
class OverlayState:
    path: str
    title: str
    x: int = 0
    y: int = 0
    w: int = 300
    h: int = 300
    opacity: float = 1.0
    speed: float = 1.0
    flip: bool = False
    visible: bool = True
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class Profile:
    """A named arrangement of overlays. The library is shared by all profiles."""
    name: str
    overlays: list[OverlayState] = field(default_factory=list)
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:10])


@dataclass
class Settings:
    close_mode: str = "auto"       # auto (tray only while overlays are shown) | tray | quit
    autostart: bool = False
    start_hidden: bool = False
    show_tips: bool = True
    hide_nsfw: bool = True         # on by default; turning it off is saved like any setting
    auto_delete_days: int = 0      # 0 = never
    library_sort: str = "recent"   # recent | added | name | size
    hotkeys: dict = field(default_factory=dict)   # action -> combo; missing = default
    animations: bool = True
    update_check: bool = True      # look for new GitHub releases
    update_auto_install: bool = False
    update_dismissed: str = ""     # version the user said "later" to (no popup again)


class Store(QObject):
    library_changed = Signal()
    overlays_changed = Signal()
    filter_changed = Signal()
    profiles_changed = Signal()   # added / renamed / removed / switched
    hotkeys_changed = Signal()

    def hotkey(self, action: str) -> str:
        return self.settings.hotkeys.get(action) or hotkeys.default(action)

    def hotkey_text(self, action: str) -> str:
        return hotkeys.display(self.hotkey(action))

    def set_hotkey(self, action: str, combo: str | None) -> None:
        """Set a combo (None = back to default)."""
        if combo and combo != hotkeys.default(action):
            self.settings.hotkeys[action] = combo
        else:
            self.settings.hotkeys.pop(action, None)
        self.save()
        self.hotkeys_changed.emit()

    def hidden(self, title: str) -> bool:
        """True if the NSFW filter hides something with this title."""
        return self.settings.hide_nsfw and is_nsfw(title)

    def set_hide_nsfw(self, on: bool) -> None:
        self.settings.hide_nsfw = on
        self.save()
        self.filter_changed.emit()

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings()
        self.library: list[LibraryItem] = []
        self.profiles: list[Profile] = [Profile("Standard")]
        self.active_uid = self.profiles[0].uid
        self._timer = QTimer(self, singleShot=True, interval=400, timeout=self.save_now)
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            return
        self.settings = _load(Settings, data.get("settings", {}))
        self.library = [_load(LibraryItem, d) for d in data.get("library", [])]
        if data.get("profiles"):
            self.profiles = [Profile(d.get("name") or "Profil",
                                     [_load(OverlayState, o) for o in d.get("overlays", [])],
                                     d.get("uid") or uuid.uuid4().hex[:10])
                             for d in data["profiles"]]
        else:  # configs from before profiles existed
            self.profiles = [Profile("Standard", [_load(OverlayState, o) for o in data.get("overlays", [])])]
        uids = [pr.uid for pr in self.profiles]
        self.active_uid = data.get("active_profile") if data.get("active_profile") in uids else uids[0]
        # drop entries whose files were removed behind our back
        self.library = [i for i in self.library if Path(i.path).exists()]
        for pr in self.profiles:
            pr.overlays = [o for o in pr.overlays if Path(o.path).exists()]
        active, now = {o.path for o in self.overlays}, time.time()
        for i in self.library:
            if i.path in active:  # on screen right now = in use
                i.last_used = now

    def save(self) -> None:
        self._timer.start()

    def save_now(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "settings": asdict(self.settings),
            "library": [asdict(i) for i in self.library],
            "profiles": [asdict(pr) for pr in self.profiles],
            "active_profile": self.active_uid,
        }
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(CONFIG_FILE)

    # -- library ------------------------------------------------------------
    def workshop_item(self, workshop_id: str) -> LibraryItem | None:
        return next((i for i in self.library if i.workshop_id == workshop_id), None)

    def add_library(self, item: LibraryItem) -> LibraryItem:
        existing = next((i for i in self.library if i.key == item.key), None)
        if existing:
            self.library.remove(existing)
        self.library.insert(0, item)
        self.save()
        self.library_changed.emit()
        return item

    def remove_library(self, item: LibraryItem) -> None:
        if item in self.library:
            self.library.remove(item)
            self.save()
            self.library_changed.emit()

    def touch(self, path: str) -> None:
        """Mark library entries for `path` as used right now."""
        now = time.time()
        for i in self.library:
            if i.path == path:
                i.last_used = now
        self.save()

    def rename_item(self, item: LibraryItem, title: str) -> None:
        """Rename an uploaded image (workshop items keep their Steam title)."""
        title = title.strip()
        if not title or item.kind == "workshop" or title == item.title:
            return
        item.title = title
        for pr in self.profiles:
            for o in pr.overlays:
                if o.path == item.path:
                    o.title = title
        self.save()
        self.library_changed.emit()
        self.overlays_changed.emit()

    def set_favorite(self, item: LibraryItem, on: bool) -> None:
        item.favorite = on
        self.save()
        self.library_changed.emit()

    def unused(self, days: int | None = None) -> list[LibraryItem]:
        """Items not used by any profile and not favourites (optionally: unused for `days`)."""
        active = {o.path for pr in self.profiles for o in pr.overlays}
        cutoff = time.time() - days * 86400 if days else None
        return [i for i in self.library
                if not i.favorite and i.path not in active and (cutoff is None or i.used < cutoff)]

    # -- profiles -----------------------------------------------------------
    @property
    def profile(self) -> Profile:
        return next((pr for pr in self.profiles if pr.uid == self.active_uid), self.profiles[0])

    @property
    def overlays(self) -> list[OverlayState]:
        """Overlays of the active profile."""
        return self.profile.overlays

    def set_active(self, uid: str) -> None:
        if uid != self.active_uid and any(pr.uid == uid for pr in self.profiles):
            self.active_uid = uid
            for o in self.overlays:
                self.touch(o.path)
            self.save()
            self.profiles_changed.emit()
            self.overlays_changed.emit()

    def unique_name(self, base: str) -> str:
        names = {pr.name for pr in self.profiles}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def add_profile(self, name: str, copy_from: Profile | None = None) -> Profile:
        overlays = []
        if copy_from:
            overlays = [OverlayState(**{**asdict(o), "uid": uuid.uuid4().hex[:10]}) for o in copy_from.overlays]
        pr = Profile(self.unique_name(name.strip() or "Profil"), overlays)
        self.profiles.append(pr)
        self.save()
        self.profiles_changed.emit()
        return pr

    def rename_profile(self, pr: Profile, name: str) -> None:
        name = name.strip()
        if name and name != pr.name:
            pr.name = self.unique_name(name)
            self.save()
            self.profiles_changed.emit()

    def remove_profile(self, pr: Profile) -> None:
        """Remove a profile (never the last one). Switch away first if it is active."""
        if len(self.profiles) > 1 and pr in self.profiles:
            self.profiles.remove(pr)
            self.save()
            self.profiles_changed.emit()

    def drop_path(self, path: str) -> None:
        """Remove overlays showing `path` from every inactive profile."""
        for pr in self.profiles:
            if pr.uid != self.active_uid:
                pr.overlays = [o for o in pr.overlays if o.path != path]
        self.save()

    # -- overlays -----------------------------------------------------------
    def add_overlay(self, state: OverlayState) -> None:
        self.touch(state.path)
        self.overlays.append(state)
        self.save()
        self.overlays_changed.emit()

    def remove_overlay(self, state: OverlayState) -> None:
        if state in self.overlays:
            self.touch(state.path)  # it was in use until now
            self.overlays.remove(state)
            self.save()
            self.overlays_changed.emit()
