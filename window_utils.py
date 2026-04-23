# window_utils.py
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def enum_windows_callback(hwnd, lparam):
    if user32.IsWindowVisible(hwnd):
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        title = buffer.value
        if title:
            windows.append((hwnd, title))
    return True

def get_all_windows():
    global windows
    windows = []
    callback = EnumWindowsProc(enum_windows_callback)
    user32.EnumWindows(callback, 0)
    return windows

def get_window_rect(hwnd):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    left_top = wintypes.POINT(rect.left, rect.top)
    right_bottom = wintypes.POINT(rect.right, rect.bottom)
    user32.ClientToScreen(hwnd, ctypes.byref(left_top))
    user32.ClientToScreen(hwnd, ctypes.byref(right_bottom))
    return (left_top.x, left_top.y, right_bottom.x, right_bottom.y)