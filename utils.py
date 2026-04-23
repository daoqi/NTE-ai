# utils.py
import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
from datetime import datetime
from PIL import ImageGrab

def get_window_rect_by_title(title_keyword):
    """根据窗口标题关键字获取第一个匹配窗口的客户区矩形（屏幕坐标）"""
    windows = gw.getWindowsWithTitle(title_keyword)
    if not windows:
        return None
    win = windows[0]
    return (win.left, win.top, win.left + win.width, win.top + win.height)

def screenshot_window_by_title(title_keyword=None):
    """截取指定窗口区域，若找不到则截取全屏"""
    if title_keyword:
        rect = get_window_rect_by_title(title_keyword)
        if rect:
            screenshot = ImageGrab.grab(bbox=rect)
            frame = np.array(screenshot)
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    # 回退全屏
    screenshot = pyautogui.screenshot()
    frame = np.array(screenshot)
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_message(msg: str) -> str:
    return f"[{get_timestamp()}] {msg}"