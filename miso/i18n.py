"""Tiny translation layer: German is the source language, English comes from i18n_en.

The language is read from the config right at import time, so module-level labels
(menus, sort names, …) are already translated. Changing it takes effect after a restart.
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

from .i18n_en import EN

LANGUAGES = {"de": "Deutsch", "en": "English"}
_CONFIG = Path(os.environ.get("APPDATA", Path.home())) / "Miso" / "config.json"


def system_language() -> str:
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "de" if (lang_id & 0x3FF) == 0x07 else "en"   # LANG_GERMAN
    except Exception:
        code = (locale.getlocale()[0] or "").lower()
        return "de" if code.startswith(("de", "german")) else "en"


def _configured() -> str:
    try:
        lang = json.loads(_CONFIG.read_text("utf-8")).get("settings", {}).get("language", "")
    except (OSError, ValueError):
        lang = ""
    return lang if lang in LANGUAGES else system_language()


LANG = _configured()


def tr(text: str, **values) -> str:
    """Translate a German UI string (with optional {placeholders})."""
    if LANG == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text
