# controlfishing.py
import cv2
import numpy as np
import pydirectinput
import win32gui
import time
import threading
import queue
from PIL import ImageGrab
import sys
import os
import traceback

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

IMG_DIR = "fishingimages"
TEMPLATE_HS = resource_path(os.path.join(IMG_DIR, "hs.png"))
TEMPLATE_DDS = resource_path(os.path.join(IMG_DIR, "dds.png"))

WINDOW_TITLE = "异环"          # 窗口标题关键字
ROI = (597, 55, 1328, 88)      # 鱼漂区域 (左, 上, 右, 下) 相对于窗口客户区
MATCH_THRESH = 0.6
CAPTURE_DELAY = 0.0005         # 0.5毫秒截图间隔

pos_queue = queue.Queue(maxsize=1)

def get_hwnd():
    """获取包含 WINDOW_TITLE 的窗口句柄"""
    def cb(hwnd, lst):
        if win32gui.IsWindowVisible(hwnd) and WINDOW_TITLE in win32gui.GetWindowText(hwnd):
            lst.append(hwnd)
    lst = []
    win32gui.EnumWindows(cb, lst)
    return lst[0] if lst else None

def find_center(gray, tpl, th):
    try:
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, maxloc = cv2.minMaxLoc(res)
        if maxv >= th:
            h, w = tpl.shape
            return (maxloc[0] + w//2, maxloc[1] + h//2)
    except Exception as e:
        print(f"[controlfishing] 匹配异常: {e}")
    return None

def capture_worker(hwnd, hs_tpl, dds_tpl, stop_event):
    l, t, r, b = ROI
    while not stop_event.is_set():
        try:
            left_top = win32gui.ClientToScreen(hwnd, (l, t))
            right_bottom = win32gui.ClientToScreen(hwnd, (r, b))
            bbox = (left_top[0], left_top[1], right_bottom[0], right_bottom[1])
            img = ImageGrab.grab(bbox=bbox)
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            hs = find_center(gray, hs_tpl, MATCH_THRESH)
            dds = find_center(gray, dds_tpl, MATCH_THRESH)
            if hs and dds:
                hs_x = hs[0] + l
                dds_x = dds[0] + l
                try:
                    pos_queue.put_nowait((hs_x, dds_x))
                except queue.Full:
                    try:
                        pos_queue.get_nowait()
                        pos_queue.put_nowait((hs_x, dds_x))
                    except:
                        pass
        except Exception as e:
            print(f"[controlfishing] 截图处理异常: {e}")
        time.sleep(CAPTURE_DELAY)

def control_worker(stop_event):
    DEAD_ZONE = 2
    PULSE_LONG = 0.012
    PULSE_MID = 0.008
    PULSE_SHORT = 0.003
    BRAKE_PULSE = 0.010

    last_dds_x = None
    stationary_counter = 0
    last_hs_x = None

    while not stop_event.is_set():
        try:
            hs_x, dds_x = pos_queue.get_nowait()
        except queue.Empty:
            continue

        if last_dds_x is not None and abs(dds_x - last_dds_x) <= 1:
            stationary_counter += 1
        else:
            stationary_counter = 0
        last_dds_x = dds_x

        if stationary_counter >= 3:
            pydirectinput.keyUp('a')
            pydirectinput.keyUp('d')
            continue

        diff = hs_x - dds_x
        abs_diff = abs(diff)

        if last_hs_x is not None:
            last_diff = last_hs_x - dds_x
            if last_diff * diff < 0 and abs_diff > DEAD_ZONE:
                if diff > 0:
                    pydirectinput.keyUp('a')
                    pydirectinput.keyUp('d')
                    pydirectinput.keyDown('a')
                    time.sleep(BRAKE_PULSE)
                    pydirectinput.keyUp('a')
                else:
                    pydirectinput.keyUp('a')
                    pydirectinput.keyUp('d')
                    pydirectinput.keyDown('d')
                    time.sleep(BRAKE_PULSE)
                    pydirectinput.keyUp('d')
                last_hs_x = hs_x
                continue

        if abs_diff <= DEAD_ZONE:
            pass
        else:
            if abs_diff > 15:
                pulse = PULSE_LONG
            elif abs_diff > 7:
                pulse = PULSE_MID
            else:
                pulse = PULSE_SHORT

            if diff > 0:
                if hs_x > dds_x:
                    pydirectinput.keyUp('d')
                    pydirectinput.keyDown('a')
                    time.sleep(pulse)
                    pydirectinput.keyUp('a')
            else:
                if hs_x < dds_x:
                    pydirectinput.keyUp('a')
                    pydirectinput.keyDown('d')
                    time.sleep(pulse)
                    pydirectinput.keyUp('d')

        last_hs_x = hs_x

    pydirectinput.keyUp('a')
    pydirectinput.keyUp('d')

def start_follow(stop_event):
    try:
        hwnd = get_hwnd()
        if not hwnd:
            print("错误：未找到包含 '%s' 的窗口" % WINDOW_TITLE)
            return False
        print(f"找到窗口句柄: {hwnd}")
        hs = cv2.imread(TEMPLATE_HS, cv2.IMREAD_GRAYSCALE)
        dds = cv2.imread(TEMPLATE_DDS, cv2.IMREAD_GRAYSCALE)
        if hs is None:
            print(f"错误：无法读取模板图片 {TEMPLATE_HS}")
            return False
        if dds is None:
            print(f"错误：无法读取模板图片 {TEMPLATE_DDS}")
            return False
        t1 = threading.Thread(target=capture_worker, args=(hwnd, hs, dds, stop_event), daemon=True)
        t2 = threading.Thread(target=control_worker, args=(stop_event,), daemon=True)
        t1.start()
        t2.start()
        return True
    except Exception as e:
        print(f"启动跟随异常: {e}")
        traceback.print_exc()
        return False