"""Macchiato native caption, keeping Windows resizing and accessibility intact."""
import sys

COLORS = {34: '#24273a', 35: '#181926', 36: '#cad3f5'}


def colorref(value):
    value = value.lstrip('#')
    red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    return red | green << 8 | blue << 16


def apply_window_theme(window):
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    try:
        handle = int(window.native.Handle.ToInt64())
        set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        set_attribute.restype = ctypes.c_long
        dark = ctypes.c_int(1)
        set_attribute(handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        # Caption colors require Windows 11; Windows 10 keeps native dark mode.
        for attribute, hex_color in COLORS.items():
            color = ctypes.c_uint32(colorref(hex_color))
            set_attribute(handle, attribute, ctypes.byref(color), ctypes.sizeof(color))
    except (AttributeError, OSError, TypeError, ValueError):
        return
