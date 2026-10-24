"""Small Win32 helpers (no-ops on other platforms)."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WIN = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

WM_HOTKEY = 0x0312
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000

HTCLIENT, HTCAPTION = 1, 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

if IS_WIN:
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]


def set_click_through(hwnd: int, enabled: bool) -> None:
    if not IS_WIN:
        return
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED
    style = style | WS_EX_TRANSPARENT if enabled else style & ~WS_EX_TRANSPARENT
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


def style_window(hwnd: int) -> None:
    """Dark frame, rounded Win11 corners, Mica-free solid backdrop."""
    if not IS_WIN:
        return
    on = ctypes.c_int(1)
    dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)          # immersive dark mode
    round_ = ctypes.c_int(2)
    dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(round_), 4)      # rounded corners
    border = ctypes.c_uint(0x00382A2A)                                   # COLORREF (BGR)
    dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), 4)


def register_hotkey(hwnd: int, hotkey_id: int, mods: int, vk: int) -> bool:
    if not IS_WIN:
        return False
    return bool(user32.RegisterHotKey(hwnd, hotkey_id, mods | MOD_NOREPEAT, vk))


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    if IS_WIN:
        user32.UnregisterHotKey(hwnd, hotkey_id)


def msg_from(message) -> wintypes.MSG:
    return wintypes.MSG.from_address(int(message))


def is_maximized(hwnd: int) -> bool:
    return bool(IS_WIN and user32.IsZoomed(hwnd))


def frame_thickness() -> int:
    """Resize frame Windows adds around a maximized captioned window."""
    if not IS_WIN:
        return 0
    return user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)  # SM_CXSIZEFRAME + SM_CXPADDEDBORDER


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(name: str, command: str | None) -> None:
    if not IS_WIN:
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if command:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
