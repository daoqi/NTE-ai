import cv2
import ctypes
from ctypes import wintypes
import sys
import time
import threading
import numpy as np
import win32gui
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap

from windows_capture import WindowsCapture, Frame, InternalCaptureControl

HS_TEMPLATE_PATH = "fishingimages/hs.png"
HS_MATCH_THRESHOLD = 0.6

# ROI from controlfishing.py — window-relative coordinates
ROI = (597, 61, 1328, 85)


# HSV thresholds for the green scoring zone
# Bright cyan-green color of the zone
GREEN_HSV_LOWER = np.array([60, 100, 150])
GREEN_HSV_UPPER = np.array([90, 255, 255])

def diagnose_window(hwnd):
    """One-time diagnostic to figure out the geometry."""
    window_rect = win32gui.GetWindowRect(hwnd)
    client_rect = win32gui.GetClientRect(hwnd)
    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
    
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )
    dwm_rect = (rect.left, rect.top, rect.right, rect.bottom)
    
    print(f"Window rect (full):           {window_rect}")
    print(f"Client rect (size):           {client_rect}")
    print(f"Client origin (screen pos):   {client_origin}")
    print(f"DWM extended frame bounds:    {dwm_rect}")
    print(f"Window size:    {window_rect[2]-window_rect[0]} x {window_rect[3]-window_rect[1]}")
    print(f"Client size:    {client_rect[2]} x {client_rect[3]}")
    print(f"DWM size:       {dwm_rect[2]-dwm_rect[0]} x {dwm_rect[3]-dwm_rect[1]}")

class WGCCaptureManager(QThread):
    """
    Manages a windows-capture session. Emits frames as they arrive from the
    WGC callback. Restarts the session when the user picks a different window.
    """
    frame_ready = pyqtSignal(np.ndarray, int, int)
    capture_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.target_hwnd = None
        self.current_capture = None
        self.lock = threading.Lock()
        self.running = True
        self.crop_info = None

    
    def set_target_hwnd(self, hwnd):
        """Called from the GUI thread when the user picks a window."""
        with self.lock:
            if hwnd == self.target_hwnd:
                return
            self.target_hwnd = hwnd
            self._restart_capture()
    
    def _restart_capture(self):
        """Stop any current session and start a new one for self.target_hwnd."""
        # Stop existing capture if any
        if self.current_capture is not None:
            try:
                self.current_capture.stop()
            except Exception:
                pass
            self.current_capture = None
        
        if self.target_hwnd is None:
            return
        
        try:
            self.crop_info = self.get_crop_for_window(self.target_hwnd)
            print(f"[crop] {self.crop_info}")
            # WindowsCapture takes a window title or handle
            # Using window_handle (hwnd) is more reliable
            capture = WindowsCapture(
                cursor_capture=False,       # don't draw the cursor in the frame
                draw_border=False,          # no yellow border around captured window
                monitor_index=None,
                window_name=None,
                window_hwnd=self.target_hwnd,
            )
            
            # Register frame handler
            @capture.event
            def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
                if not self.running:
                    capture_control.stop()
                    return
                
                # Count incoming frames from WGC (independent of polling rate)
                if not hasattr(self, '_wgc_frame_count'):
                    self._wgc_frame_count = 0
                    self._wgc_last_print = time.time()
                self._wgc_frame_count += 1
                now = time.time()
                if now - self._wgc_last_print > 1.0:
                    print(f"[WGC] incoming: {self._wgc_frame_count} frames/sec")
                    self._wgc_frame_count = 0
                    self._wgc_last_print = now
                
                arr = frame.frame_buffer  # BGRA

                if self.crop_info is not None:
                    c = self.crop_info
                    h, w = arr.shape[:2]
                    crop_l = max(0, min(c['left'], w))
                    crop_t = max(0, min(c['top'], h))
                    crop_r = min(crop_l + c['width'], w)
                    crop_b = min(crop_t + c['height'], h)
                    arr = arr[crop_t:crop_b, crop_l:crop_r]

                rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
                self.frame_ready.emit(rgb, frame.width, frame.height)
            
            @capture.event
            def on_closed():
                pass  # window closed, will be detected by hwnd validity check
            
            # start_free_threaded runs the capture loop in WGC's own thread,
            # not blocking us; we just receive callbacks
            self.current_capture = capture.start_free_threaded()
        
        except Exception as e:
            self.capture_error.emit(f"启动捕获失败: {e}")
            self.current_capture = None
    
    def get_crop_for_window(self, hwnd):
        """Compute crop bounds to extract pure client area from WGC frame."""
        # DWM bounds — what WGC actually captures
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        rect = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        dwm_left, dwm_top = rect.left, rect.top
        dwm_w = rect.right - rect.left
        dwm_h = rect.bottom - rect.top
        
        # Client area position on screen
        client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
        client_left, client_top = client_origin
        
        # Client size
        client_rect = win32gui.GetClientRect(hwnd)
        client_w, client_h = client_rect[2], client_rect[3]
        
        # Offset of client area within DWM frame
        crop_left = client_left - dwm_left
        crop_top = client_top - dwm_top
        
        return {
            'left': crop_left,
            'top': crop_top,
            'width': client_w,
            'height': client_h,
        }

    def run(self):
        self.exec_()
    
    def stop(self):
        self.running = False
        with self.lock:
            if self.current_capture is not None:
                try:
                    self.current_capture.stop()
                except Exception:
                    pass
                self.current_capture = None
        self.quit()  # tells exec_() to exit
        self.wait()


class WindowMirror(QMainWindow):
    def __init__(self):
        super().__init__()

        self._last_green_info = "绿区: 未检测到"
        self._last_yellow_info = "黄标: 未检测到"
        self._last_status_info = ""

        self.hs_template = cv2.imread(HS_TEMPLATE_PATH, cv2.IMREAD_GRAYSCALE)
        if self.hs_template is None:
            print(f"[警告] 无法加载 {HS_TEMPLATE_PATH}")

        self.setWindowTitle("游戏窗口镜像 (WGC)")
        self.setGeometry(100, 100, 800, 600)
        # self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Top row: window selector
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("游戏窗口:"))
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(400)
        self.window_combo.currentIndexChanged.connect(self.on_window_selected)
        top_row.addWidget(self.window_combo)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_windows)
        top_row.addWidget(refresh_btn)
        top_row.addStretch()
        layout.addLayout(top_row)
        
        # Diagnostic info
        self.info_label = QLabel("未选择窗口")
        self.info_label.setStyleSheet("font-family: Consolas; padding: 6px; background: #111; color: #0f0;")
        layout.addWidget(self.info_label)
        
        # The mirrored display
        self.image_label = QLabel("等待...")
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_label.setStyleSheet("background-color: #000;")
        layout.addWidget(self.image_label, stretch=1)
        
        # FPS tracking
        self.frame_times = []
        self.last_fps_update = time.time()
        self.current_fps = 0.0
        
        # Capture manager
        self.capture_manager = WGCCaptureManager()
        self.capture_manager.frame_ready.connect(self.on_frame_ready)
        self.capture_manager.capture_error.connect(self.on_capture_error)
        self.capture_manager.start()
        
        # Initial population
        self.refresh_windows()

    def detect_green_zone(self, full_frame_rgb):
        """
        Detect the green scoring zone within the ROI.
        Returns (left_x, right_x) in full-frame coordinates, or None if not found.
        """
        roi_l, roi_t, roi_r, roi_b = ROI
        h, w = full_frame_rgb.shape[:2]
        
        # Defensive: clip ROI to frame bounds
        roi_l = max(0, min(roi_l, w))
        roi_t = max(0, min(roi_t, h))
        roi_r = max(0, min(roi_r, w))
        roi_b = max(0, min(roi_b, h))
        
        if roi_r <= roi_l or roi_b <= roi_t:
            return None
        
        # Extract ROI strip
        roi_img = full_frame_rgb[roi_t:roi_b, roi_l:roi_r]
        
        # HSV thresholding
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, GREEN_HSV_LOWER, GREEN_HSV_UPPER)
        
        # Find horizontal extent — which columns contain any green pixels
        cols_with_green = np.any(mask > 0, axis=0)
        green_indices = np.where(cols_with_green)[0]
        
        if len(green_indices) == 0:
            return None
        
        # Convert ROI-local coordinates back to full-frame coordinates
        green_left = int(green_indices[0]) + roi_l
        green_right = int(green_indices[-1]) + roi_l
        
        return (green_left, green_right)
        
    def detect_yellow_marker(self, full_frame_rgb):
        """
        Detect yellow marker via template matching (mirrors the original code's approach).
        More robust for narrow markers than HSV thresholding.
        """
        if self.hs_template is None:
            return None
        
        roi_l, roi_t, roi_r, roi_b = ROI
        h, w = full_frame_rgb.shape[:2]
        
        roi_l = max(0, min(roi_l, w))
        roi_t = max(0, min(roi_t, h))
        roi_r = max(0, min(roi_r, w))
        roi_b = max(0, min(roi_b, h))
        
        if roi_r <= roi_l or roi_b <= roi_t:
            return None
        
        roi_img = full_frame_rgb[roi_t:roi_b, roi_l:roi_r]
        gray = cv2.cvtColor(roi_img, cv2.COLOR_RGB2GRAY)
        
        # Defensive: template must fit within ROI
        th, tw = self.hs_template.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            return None
        
        result = cv2.matchTemplate(gray, self.hs_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val < HS_MATCH_THRESHOLD:
            return None
        
        # Convert ROI-local match position to full-frame coordinates
        yellow_left = max_loc[0] + roi_l
        yellow_right = yellow_left + tw
        yellow_center = yellow_left + tw // 2
        
        return (yellow_left, yellow_right, yellow_center)

    def refresh_windows(self):
        # Block signals so we don't trigger on_window_selected during repopulation
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "异环" in title and "异环薄荷AI" not in title and "镜像" not in title:
                    self.window_combo.addItem(title, hwnd)
        win32gui.EnumWindows(enum_cb, None)
        
        self.window_combo.blockSignals(False)
        
        # Trigger selection of the first item if any
        if self.window_combo.count() > 0:
            self.on_window_selected(0)
    

    
    def on_window_selected(self, index):
        if index < 0:
            return
        hwnd = self.window_combo.itemData(index)
        if hwnd and win32gui.IsWindow(hwnd):
            diagnose_window(hwnd)  # ← add this

            self.capture_manager.set_target_hwnd(hwnd)
    
    def draw_overlays(self, arr):
        """Draw all debug overlays on the captured frame."""
        roi_l, roi_t, roi_r, roi_b = ROI
        h, w = arr.shape[:2]
        
        # Defensive clamp
        roi_l = max(0, min(roi_l, w - 1))
        roi_t = max(0, min(roi_t, h - 1))
        roi_r = max(0, min(roi_r, w - 1))
        roi_b = max(0, min(roi_b, h - 1))
        
        # ROI box (red)
        cv2.rectangle(arr, (roi_l, roi_t), (roi_r, roi_b), (255, 0, 0), 2)
        
        # ROI label
        cv2.putText(arr, f"ROI {roi_r-roi_l}x{roi_b-roi_t}",
                    (roi_l, max(roi_t - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        
        # ROI corner crosshairs (yellow)
        for (cx, cy) in [(roi_l, roi_t), (roi_r, roi_t), (roi_l, roi_b), (roi_r, roi_b)]:
            cv2.line(arr, (cx - 10, cy), (cx + 10, cy), (255, 255, 0), 1)
            cv2.line(arr, (cx, cy - 10), (cx, cy + 10), (255, 255, 0), 1)
        
        # Yellow marker detection
        yellow_bounds = self.detect_yellow_marker(arr)
        if yellow_bounds is not None:
            yl, yr, yc = yellow_bounds
            # Draw a narrow blue box around the marker (blue stands out against yellow)
            cv2.rectangle(arr, (yl, roi_t - 5), (yr, roi_b + 5), (0, 100, 255), 2)
            
            # Vertical line through the center
            cv2.line(arr, (yc, roi_t - 8), (yc, roi_b + 8), (0, 100, 255), 1)
            
            # Label below
            cv2.putText(arr, f"YELLOW c={yc}",
                        (yl - 30, roi_b + 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 255), 2)
            
            self._last_yellow_info = f"黄标: 中心={yc}"
        else:
            self._last_yellow_info = "黄标: 未检测到"

        # Green zone detection — overlay on top of ROI
        green_bounds = self.detect_green_zone(arr)
        if green_bounds is not None:
            gl, gr = green_bounds
            # Draw a thicker green box just inside the ROI vertical extent
            cv2.rectangle(arr, (gl, roi_t - 3), (gr, roi_b + 3), (0, 255, 0), 2)
            
            # Label with width
            green_width = gr - gl
            green_center = (gl + gr) // 2
            cv2.putText(arr, f"GREEN w={green_width} c={green_center}",
                        (gl, roi_b + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Store for status display
            self._last_green_info = f"绿区: 左={gl} 右={gr} 宽={green_width} 中心={green_center}"
        else:
            self._last_green_info = "绿区: 未检测到"

        # Combined status: is yellow inside green?
        if green_bounds is not None and yellow_bounds is not None:
            gl, gr = green_bounds
            yc = yellow_bounds[2]
            if gl <= yc <= gr:
                status = "✓ IN ZONE"
                cv2.putText(arr, status, (roi_r - 150, roi_t - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            else:
                offset = (yc - gl) if yc < gl else (yc - gr)
                direction = "←" if yc < gl else "→"
                status = f"✗ OUT {offset:+d} {direction}"
                cv2.putText(arr, status, (roi_r - 200, roi_t - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            self._last_status_info = status
        else:
            self._last_status_info = ""


        
        
        return arr
    
    def on_frame_ready(self, arr, client_w, client_h):
        if not hasattr(self, '_emit_count'):
            self._emit_count = 0
            self._emit_last_print = time.time()
        self._emit_count += 1
        now = time.time()
        if now - self._emit_last_print > 1.0:
            print(f"[GUI] received: {self._emit_count} frames/sec")
            self._emit_count = 0
            self._emit_last_print = now
        # Track FPS
        now = time.time()
        self.frame_times.append(now)
        self.frame_times = [t for t in self.frame_times if now - t < 1.0]
        if now - self.last_fps_update > 0.5:
            self.current_fps = len(self.frame_times)
            self.last_fps_update = now
        
        # WGC arrays may not be writable — make sure cv2.rectangle can modify
        if not arr.flags.writeable:
            arr = arr.copy()
        
        arr = self.draw_overlays(arr)
        
        h, w = arr.shape[:2]
        # Important: keep arr alive while QImage references it
        self._current_arr = arr  # prevent GC
        qimg = QImage(arr.data, w, h, w * 3, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(qimg))
        
        self.info_label.setText(
            f"客户区: {client_w}x{client_h} | FPS: {self.current_fps:.0f} | "
            f"{self._last_green_info} | {self._last_yellow_info} {self._last_status_info}"
        )
    
    def on_capture_error(self, msg):
        self.info_label.setText(f"捕获错误: {msg}")
    
    def closeEvent(self, event):
        self.capture_manager.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WindowMirror()
    window.show()
    sys.exit(app.exec_())