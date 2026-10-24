"""Global hotkeys: storage format, German display text and Win32 key codes.

A combo is stored as text like "Ctrl+Alt+E" or "Ctrl+Shift+Left".
"""
from __future__ import annotations

from PySide6.QtCore import Qt

from . import winapi

# action -> (id for RegisterHotKey, label, default combo)
ACTIONS = {
    "edit": (1, "Bearbeiten-Modus", "Ctrl+Alt+E"),
    "hide": (2, "Alle aus-/einblenden", "Ctrl+Alt+H"),
    "prev": (3, "Vorheriges Profil", "Ctrl+Alt+Left"),
    "next": (4, "Nächstes Profil", "Ctrl+Alt+Right"),
}

MODS = {"Ctrl": winapi.MOD_CONTROL, "Alt": winapi.MOD_ALT, "Shift": winapi.MOD_SHIFT, "Win": 0x0008}
MOD_TEXT = {"Ctrl": "Strg", "Alt": "Alt", "Shift": "Umschalt", "Win": "Win"}

# named keys: storage name -> (virtual key, display text, Qt key)
SPECIAL = {
    "Left": (0x25, "←", Qt.Key.Key_Left),
    "Up": (0x26, "↑", Qt.Key.Key_Up),
    "Right": (0x27, "→", Qt.Key.Key_Right),
    "Down": (0x28, "↓", Qt.Key.Key_Down),
    "Space": (0x20, "Leertaste", Qt.Key.Key_Space),
    "Home": (0x24, "Pos1", Qt.Key.Key_Home),
    "End": (0x23, "Ende", Qt.Key.Key_End),
    "PageUp": (0x21, "Bild ↑", Qt.Key.Key_PageUp),
    "PageDown": (0x22, "Bild ↓", Qt.Key.Key_PageDown),
    "Insert": (0x2D, "Einfg", Qt.Key.Key_Insert),
    "Delete": (0x2E, "Entf", Qt.Key.Key_Delete),
}
for _n in range(1, 25):
    SPECIAL[f"F{_n}"] = (0x6F + _n, f"F{_n}", getattr(Qt.Key, f"Key_F{_n}"))
_BY_QT = {qt.value: name for name, (_, _, qt) in SPECIAL.items()}


def default(action: str) -> str:
    return ACTIONS[action][2]


def parse(combo: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+E' -> (MOD flags, virtual key) for RegisterHotKey."""
    parts = combo.split("+")
    *mods, key = parts
    flags = 0
    for m in mods:
        if m not in MODS:
            return None
        flags |= MODS[m]
    if key in SPECIAL:
        vk = SPECIAL[key][0]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    else:
        return None
    return (flags, vk) if flags else None


def display(combo: str) -> str:
    *mods, key = combo.split("+")
    names = [MOD_TEXT.get(m, m) for m in mods]
    names.append(SPECIAL[key][1] if key in SPECIAL else key.upper())
    return " + ".join(names)


def modifiers_text(mods: Qt.KeyboardModifier) -> list[str]:
    out = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        out.append("Ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        out.append("Alt")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        out.append("Shift")
    if mods & Qt.KeyboardModifier.MetaModifier:
        out.append("Win")
    return out


def from_key(key: int, mods: Qt.KeyboardModifier) -> str | None:
    """Turn a key press into a combo; None while only modifiers are held or no modifier is used."""
    names = modifiers_text(mods)
    key = int(key)
    if not names:
        return None
    if key in _BY_QT:
        name = _BY_QT[key]
    elif Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
        name = chr(key)
    else:
        return None
    return "+".join(names + [name])
