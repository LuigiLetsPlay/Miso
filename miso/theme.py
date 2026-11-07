"""Colors, fonts, icons and the global stylesheet."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap

# muted, almost monochrome palette — the content should be the colourful part
BG = "#0E0E10"
SIDEBAR = "#111113"
SURFACE = "#161618"
SURFACE_2 = "#1C1C1F"
SURFACE_3 = "#27272B"
BORDER = "#242428"
BORDER_HOVER = "#34343A"
TEXT = "#E6E6E9"
MUTED = "#8B8B93"
DIM = "#5A5A62"
ACCENT = "#D6D6DB"        # soft light grey, used sparingly
ACCENT_A = ACCENT
ACCENT_B = "#BDBDC4"
ON_ACCENT = "#121214"     # text/icons drawn on top of the accent
SUCCESS = "#5FB98B"
DANGER = "#D9666F"

ICON_FONT = "Segoe Fluent Icons"

# -- motion --------------------------------------------------------------------------
ANIMATIONS = True   # set from the user setting + Windows' "show animations" at startup


def ms(duration: int) -> int:
    """Animation length, or 0 when animations are switched off."""
    return duration if ANIMATIONS else 0


def system_animations_enabled() -> bool:
    if sys.platform != "win32":
        return True
    import ctypes
    enabled = ctypes.c_int(1)
    ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)  # SPI_GETCLIENTAREAANIMATION
    return bool(enabled.value)


class Icon:
    SEARCH = ""
    COMPASS = ""
    LIBRARY = ""
    LAYERS = ""
    SETTINGS = ""
    DOWNLOAD = ""
    UPLOAD = ""
    ADD = ""
    DELETE = ""
    CLOSE = ""
    MIN = ""
    MAX = ""
    RESTORE = ""
    EYE = ""
    EYE_OFF = ""
    EDIT = ""
    LOCK = ""
    FOLDER = ""
    PIN = ""
    PEOPLE = ""
    HEART = ""
    REFRESH = ""
    FLIP = ""
    CENTER = ""
    BRIGHTNESS = ""
    CHECK = ""
    GLOBE = ""
    PHOTO = ""
    SPARKLE = ""
    KEYBOARD = ""
    SHIELD = ""
    STAR = ""
    STAR_FILL = ""
    STORAGE = ""
    BROOM = ""
    CLOCK = ""
    WARNING = ""
    GRIP = ""
    CHEVRON_LEFT = ""
    CHEVRON_RIGHT = ""
    MORE = ""


def asset(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def setup_fonts() -> None:
    global ICON_FONT
    families = set(QFontDatabase.families())
    if "Segoe Fluent Icons" not in families and "Segoe MDL2 Assets" in families:
        ICON_FONT = "Segoe MDL2 Assets"


def ui_font(size: float = 10, weight: QFont.Weight = QFont.Weight.Normal, display: bool = False) -> QFont:
    family = "Segoe UI Variable Display" if display else "Segoe UI Variable Text"
    f = QFont([family, "Segoe UI", "Inter", "Arial"])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def icon_font(size: float = 11) -> QFont:
    f = QFont(ICON_FONT)
    f.setPointSizeF(size)
    return f


def accent_gradient(rect: QRectF) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor(ACCENT_A))
    g.setColorAt(1, QColor(ACCENT_B))
    return g


_icon_cache: dict[int, QPixmap] = {}


def app_icon_pixmap(size: int = 256) -> QPixmap:
    if size not in _icon_cache:
        pm = QPixmap(str(asset("icon.png")))
        if pm.isNull():
            pm = QPixmap(size, size)
            pm.fill(QColor(SURFACE_3))
        _icon_cache[size] = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
    return _icon_cache[size]


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(s))
    return icon


def glyph_icon(glyph: str, color: str = TEXT, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(color))
    f = QFont(ICON_FONT)
    f.setPixelSize(int(size * .62))
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


STYLESHEET = f"""
* {{
    color: {TEXT};
    outline: none;
}}
QWidget#Root {{ background: {BG}; }}
QWidget#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QWidget#Page, QWidget#ScrollContent {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QLabel#Muted {{ color: {MUTED}; }}
QLabel#Dim {{ color: {DIM}; font-size: 9pt; }}
QLabel#PageTitle {{
    font-family: "Segoe UI Variable Display", "Segoe UI";
    font-size: 20pt; font-weight: 600;
}}
QLabel#SectionTitle {{ font-size: 10.5pt; font-weight: 600; color: {MUTED}; }}

QLineEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px 8px 6px;
    selection-background-color: {SURFACE_3};
    font-size: 10.5pt;
}}
QLineEdit:hover {{ border-color: {BORDER_HOVER}; }}
QLineEdit:focus {{ border-color: #4A4A52; background: {SURFACE_2}; }}

QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {SURFACE_3}; border-color: {BORDER_HOVER}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {DIM}; }}
QPushButton#Primary {{ border: none; background: {ACCENT}; color: {ON_ACCENT}; }}
QPushButton#Primary:hover {{ background: #E8E8EC; }}
QPushButton#Primary:pressed {{ background: {ACCENT_B}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {MUTED}; }}
QPushButton#Ghost:hover {{ color: {TEXT}; background: {SURFACE_2}; }}
QPushButton#Danger:hover {{ background: #2A1A1C; border-color: #5A3236; color: {DANGER}; }}

QPushButton#Seg {{
    background: transparent; border: none; border-radius: 7px;
    padding: 6px 14px; color: {MUTED}; font-weight: 600;
}}
QPushButton#Seg:hover {{ color: {TEXT}; }}
QPushButton#Seg:checked {{ background: {SURFACE_3}; color: {TEXT}; }}
QPushButton#Chip {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 15px;
    padding: 6px 14px; color: {MUTED}; font-weight: 600;
}}
QPushButton#Chip:hover {{ color: {TEXT}; border-color: {BORDER_HOVER}; }}
QPushButton#Chip:checked {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}
QWidget#SegBar {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}

QComboBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 12px; font-weight: 600;
}}
QComboBox:hover {{ border-color: {BORDER_HOVER}; background: {SURFACE_3}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
    selection-background-color: {SURFACE_3}; outline: none;
}}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #2A2A2F; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: #3A3A41; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #A1A1A9; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}

QMenu {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMenu::indicator {{ width: 0; }}

QToolTip {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 5px 8px;
}}
"""
