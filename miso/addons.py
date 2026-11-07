"""Optional add-ons.

Some builds ship an extra package `miso.ext`. If it is there, it gets the main window
once at startup and can add pages, settings or library extras through the window's
public methods (add_page, library_page.add_extension, settings_page.add_section).
"""
from __future__ import annotations


def load(window) -> None:
    try:
        from . import ext
    except ModuleNotFoundError as e:
        if e.name != f"{__package__}.ext":
            raise
        return
    ext.setup(window)
