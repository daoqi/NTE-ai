"""
Improved fishing controller with WGC capture, HSV green detection,
template-matched yellow detection, and range-staying control logic.

Drop-in replacement for controlfishing.py — same start_follow() signature.
"""

import os
import sys
import time
import threading
import queue
import ctypes
from ctypes import wintypes

import cv2
import numpy as np
import win32gui
import pydirectinput

from windows_capture import WindowsCapture, Frame, InternalCaptureControl


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ---------- Configuration ----------

IMG_DIR = "fishingimages"
TEMPLATE_HS = resource_path(os.path.join(IMG_DIR, "hs.png"))

# ROI within client area — where the fishing bar lives at 1920x1080
ROI = (597, 61, 1328, 85)

# HSV bounds for green scoring zone
GREEN_HSV_LOWER = np.array([60, 100, 150])
GREEN_HSV_UPPER = np.array([90, 255, 255])

# Template matching threshold for yellow marker
YELLOW_MATCH_THRESH = 0.6

# Range-staying controller parameters
GREEN_BUFFER_PCT = 0.25  # buffer = 15% of green zone width on each side
PULSE_SCALE = 0.002         # seconds per pixel of overshoot
PULSE_MIN = 0.005           # 5ms minimum tap
PULSE_MAX = 0.040           # 40ms maximum press
INTER_PULSE_SLEEP = 0.010   # gap between pulses to let game register

# First-frame wait timeout (don't block forever if WGC fails)
FIRST_FRAME_TIMEOUT = 1.0

# Producer/consumer queue — single slot, drop-old-keep-newest
detection_queue = queue.Queue(maxsize=1)


# ---------- DWM crop math ----------

def get_client_crop(hwnd):
    """Compute crop bounds to extract pure client area from WGC frame."""
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )
    dwm_left, dwm_top = rect.left, rect.top
    
    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
    client_left, client_top = client_origin
    
    client_rect = win32gui.GetClientRect(hwnd)
    client_w, client_h = client_rect[2], client_rect[3]
    
    return {
        'left': client_left - dwm_left,
        'top': client_top - dwm_top,
        'width': client_w,
        'height': client_h,
    }


# ---------- Detection ----------

def detect_green_zone(frame_rgb):
    """Returns (left_x, right_x) in full-frame coords, or None."""
    roi_l, roi_t, roi_r, roi_b = ROI
    h, w = frame_rgb.shape[:2]
    
    if roi_r > w or roi_b > h or roi_l < 0 or roi_t < 0:
        return None
    
    roi_img = frame_rgb[roi_t:roi_b, roi_l:roi_r]
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, GREEN_HSV_LOWER, GREEN_HSV_UPPER)
    
    cols = np.any(mask > 0, axis=0)
    indices = np.where(cols)[0]
    
    if len(indices) == 0:
        return None
    
    return (int(indices[0]) + roi_l, int(indices[-1]) + roi_l)


def detect_yellow_marker(frame_rgb, template):
    """Returns yellow center x in full-frame coords, or None."""
    if template is None:
        return None
    
    roi_l, roi_t, roi_r, roi_b = ROI
    h, w = frame_rgb.shape[:2]
    
    if roi_r > w or roi_b > h or roi_l < 0 or roi_t < 0:
        return None
    
    roi_img = frame_rgb[roi_t:roi_b, roi_l:roi_r]
    gray = cv2.cvtColor(roi_img, cv2.COLOR_RGB2GRAY)
    
    th, tw = template.shape[:2]
    if gray.shape[0] < th or gray.shape[1] < tw:
        return None
    
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    
    if max_val < YELLOW_MATCH_THRESH:
        return None
    
    return max_loc[0] + tw // 2 + roi_l


# ---------- Capture worker ----------

class CaptureWorker:
    """
    Owns the WGC session, runs detection in the WGC callback,
    pushes results to detection_queue.
    """
    def __init__(self, hwnd, hs_template, stop_event, first_frame_event):
        self.hwnd = hwnd
        self.hs_template = hs_template
        self.stop_event = stop_event
        self.first_frame_event = first_frame_event
        self.crop = get_client_crop(hwnd)
        self.capture_handle = None
    
    def start(self):
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=None,
            window_name=None,
            window_hwnd=self.hwnd,
        )
        
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            if self.stop_event.is_set():
                capture_control.stop()
                return
            
            try:
                # Crop to client area
                arr = frame.frame_buffer
                fh, fw = arr.shape[:2]
                cl = max(0, min(self.crop['left'], fw))
                ct = max(0, min(self.crop['top'], fh))
                cr = min(cl + self.crop['width'], fw)
                cb = min(ct + self.crop['height'], fh)
                arr = arr[ct:cb, cl:cr]
                
                rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
                
                # Run detections
                green = detect_green_zone(rgb)
                yellow_x = detect_yellow_marker(rgb, self.hs_template)
                
                if green is not None and yellow_x is not None:
                    detection = (yellow_x, green[0], green[1])
                    # Drop-old-keep-newest
                    try:
                        detection_queue.put_nowait(detection)
                    except queue.Full:
                        try:
                            detection_queue.get_nowait()
                            detection_queue.put_nowait(detection)
                        except queue.Empty:
                            pass
                
                self.first_frame_event.set()
            
            except Exception as e:
                print(f"[capture] frame error: {e}", flush=True)
        
        @capture.event
        def on_closed():
            pass
        
        self.capture_handle = capture.start_free_threaded()
    
    def stop(self):
        if self.capture_handle is not None:
            try:
                self.capture_handle.stop()
            except Exception:
                pass
            self.capture_handle = None


# ---------- Control worker ----------

def control_worker(stop_event):
    """
    Range-staying controller: presses A/D only when yellow exits the
    green zone (with safety buffer). No fight-to-center, no overshoot loops.
    """
    key_a_down = False
    key_d_down = False
    
    def release_all():
        nonlocal key_a_down, key_d_down
        if key_a_down:
            pydirectinput.keyUp('a')
            key_a_down = False
        if key_d_down:
            pydirectinput.keyUp('d')
            key_d_down = False
    
    def scale_pulse(overshoot_px):
        return max(PULSE_MIN, min(PULSE_MAX, overshoot_px * PULSE_SCALE))
    
    while not stop_event.is_set():
        try:
            yellow_x, green_left, green_right = detection_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # Compute safe target zone
        green_width = green_right - green_left
        buffer_px = int(green_width * GREEN_BUFFER_PCT)
        target_left = green_left + buffer_px
        target_right = green_right - buffer_px
        
        if target_left >= target_right:
            # Green zone too narrow for buffer — fall back to bare bounds
            target_left = green_left
            target_right = green_right
        
        if target_left <= yellow_x <= target_right:
            # Yellow is comfortably inside — release any held keys, do nothing
            release_all()
        elif yellow_x < target_left:
            # Yellow too far left — press D to move it right
            release_all()
            overshoot = target_left - yellow_x
            pulse = scale_pulse(overshoot)
            pydirectinput.keyDown('d')
            time.sleep(pulse)
            pydirectinput.keyUp('d')
            time.sleep(INTER_PULSE_SLEEP)
        else:  # yellow_x > target_right
            # Yellow too far right — press A to move it left
            release_all()
            overshoot = yellow_x - target_right
            pulse = scale_pulse(overshoot)
            pydirectinput.keyDown('a')
            time.sleep(pulse)
            pydirectinput.keyUp('a')
            time.sleep(INTER_PULSE_SLEEP)
    
    release_all()


# ---------- Public API (matches controlfishing.py) ----------

def start_follow(stop_event, target_hwnd=None):
    """
    Start fishing automation. Returns True on successful start, False otherwise.
    
    Args:
        stop_event: threading.Event() — set this to stop both worker threads.
        target_hwnd: window handle of the game window. Required.
    """
    if target_hwnd is None:
        print("错误：未传入目标窗口句柄，请通过UI选择钓鱼窗口", flush=True)
        return False
    
    if not win32gui.IsWindow(target_hwnd):
        print(f"错误：窗口句柄 {target_hwnd} 无效", flush=True)
        return False
    
    print(f"使用窗口句柄: {target_hwnd}", flush=True)
    
    # Load yellow marker template
    hs_template = cv2.imread(TEMPLATE_HS, cv2.IMREAD_GRAYSCALE)
    if hs_template is None:
        print(f"错误：无法读取 hs.png，路径={TEMPLATE_HS}", flush=True)
        return False
    
    # Drain any stale detections from previous run
    while not detection_queue.empty():
        try:
            detection_queue.get_nowait()
        except queue.Empty:
            break
    
    # Start capture
    first_frame_event = threading.Event()
    capture = CaptureWorker(target_hwnd, hs_template, stop_event, first_frame_event)
    
    try:
        capture.start()
    except Exception as e:
        print(f"错误：WGC 启动失败 {e}", flush=True)
        return False
    
    # Wait for first frame to confirm capture is working
    if not first_frame_event.wait(timeout=FIRST_FRAME_TIMEOUT):
        print(f"警告：{FIRST_FRAME_TIMEOUT}秒内未收到首帧，可能捕获失败", flush=True)
        # Continue anyway — capture might still come up, controller will idle until then
    else:
        print("捕获已启动", flush=True)
    
    # Start control thread
    control_thread = threading.Thread(
        target=control_worker,
        args=(stop_event,),
        daemon=True,
        name="fishing-control",
    )
    control_thread.start()
    
    # Stash capture object somewhere stop_event consumers can find it
    # Since the original API doesn't return anything but bool, we attach
    # to the stop_event so it gets cleaned up
    stop_event._capture_worker = capture
    
    print("开始跟随...", flush=True)
    return True