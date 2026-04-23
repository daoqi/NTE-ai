# automation_thread.py
import time
import cv2
import numpy as np
import pyautogui
from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
from config import TEMPLATES_CONFIG, MATCH_THRESHOLD, LOOP_INTERVAL, ACTION_DELAY
from utils import screenshot_window_by_title, get_window_rect_by_title

# 图像缩放因子（0.5 可大幅提升速度）
SCALE_FACTOR = 0.5
USE_GRAYSCALE = True

class AutomationThread(QThread):
    log_signal = pyqtSignal(str)        # 主窗口日志
    game_log_signal = pyqtSignal(str)   # 游戏内浮动日志
    finished_signal = pyqtSignal()

    def __init__(self, template_dir: str, window_title: str = "", parent=None):
        super().__init__(parent)
        self.template_dir = Path(template_dir).resolve()
        self.window_title = window_title
        self.running = False
        self.templates = []   # (缩放后模板, 动作, 参数, 原始高, 原始宽)
        self.load_templates()

    def load_templates(self):
        if not self.template_dir.exists():
            self.log_signal.emit(f"[错误] 模板目录不存在: {self.template_dir}")
            return
        for filename, action, param in TEMPLATES_CONFIG:
            img_path = self.template_dir / filename
            if not img_path.exists():
                self.log_signal.emit(f"[警告] 模板文件不存在: {filename}")
                continue
            try:
                with open(img_path, 'rb') as f:
                    data = np.frombuffer(f.read(), dtype=np.uint8)
                    template_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if template_bgr is None:
                    self.log_signal.emit(f"[警告] 无法解码模板图片: {filename}")
                    continue
                # 转灰度（提速）
                if USE_GRAYSCALE:
                    template = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
                else:
                    template = template_bgr
                h, w = template.shape[:2]
                # 缩放模板
                if SCALE_FACTOR != 1.0:
                    new_w = int(w * SCALE_FACTOR)
                    new_h = int(h * SCALE_FACTOR)
                    template_scaled = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)
                else:
                    template_scaled = template
                self.templates.append((template_scaled, action, param, h, w))
                self.log_signal.emit(f"[初始化] 加载成功: {filename}")
            except Exception as e:
                self.log_signal.emit(f"[错误] 加载失败 {filename}: {e}")

    def find_and_act(self, template_scaled, action, param, orig_h, orig_w):
        try:
            screen_bgr = screenshot_window_by_title(self.window_title)
            if screen_bgr is None:
                return False
            if USE_GRAYSCALE:
                screen = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            else:
                screen = screen_bgr
            # 缩放屏幕截图
            if SCALE_FACTOR != 1.0:
                new_w = int(screen.shape[1] * SCALE_FACTOR)
                new_h = int(screen.shape[0] * SCALE_FACTOR)
                screen_scaled = cv2.resize(screen, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                screen_scaled = screen

            result = cv2.matchTemplate(screen_scaled, template_scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= MATCH_THRESHOLD:
                # 还原坐标到原始截图尺寸
                scale_inv = 1.0 / SCALE_FACTOR
                h_scaled, w_scaled = template_scaled.shape[:2]
                center_x_scaled = max_loc[0] + w_scaled // 2
                center_y_scaled = max_loc[1] + h_scaled // 2
                center_x_original = int(center_x_scaled * scale_inv)
                center_y_original = int(center_y_scaled * scale_inv)

                # 转换为屏幕绝对坐标
                rect = get_window_rect_by_title(self.window_title)
                if rect:
                    left, top, _, _ = rect
                    click_x = left + center_x_original
                    click_y = top + center_y_original
                else:
                    click_x, click_y = center_x_original, center_y_original

                if action == "click":
                    pyautogui.click(click_x, click_y)
                    msg = f"[异环] 点击图片中心: ({click_x}, {click_y})"
                    self.log_signal.emit(msg)
                    self.game_log_signal.emit(msg)
                elif action == "key":
                    pyautogui.press(param.lower())
                    msg = f"[异环] 按键: {param.lower()}"
                    self.log_signal.emit(msg)
                    self.game_log_signal.emit(msg)
                elif action == "center_click":
                    if rect:
                        left, top, right, bottom = rect
                        click_x = left + (right - left) // 2
                        click_y = top + (bottom - top) // 2
                        pyautogui.click(click_x, click_y)
                        msg = f"[异环] 点击窗口中心: ({click_x}, {click_y})"
                    else:
                        w, h = pyautogui.size()
                        click_x, click_y = w // 2, h // 2
                        pyautogui.click(click_x, click_y)
                        msg = f"[异环] 点击屏幕中心: ({click_x}, {click_y})"
                    self.log_signal.emit(msg)
                    self.game_log_signal.emit(msg)
                else:
                    self.log_signal.emit(f"[警告] 未知动作类型: {action}")
                return True
            return False
        except Exception as e:
            self.log_signal.emit(f"[错误] 找图/执行动作异常: {e}")
            return False

    def run(self):
        if not self.templates:
            self.log_signal.emit("[错误] 未加载任何有效模板，线程退出")
            self.finished_signal.emit()
            return
        if not self.window_title:
            self.log_signal.emit("[错误] 未设置目标窗口标题！请在界面中输入窗口标题关键字（如“异环”）。")
            self.finished_signal.emit()
            return
        self.log_signal.emit(f"[自动化] 目标窗口关键字: {self.window_title}")
        self.running = True
        self.log_signal.emit("[自动化] 任务自动跳过已启动，开始监测...")
        while self.running:
            acted = False
            for template_scaled, action, param, orig_h, orig_w in self.templates:
                if self.find_and_act(template_scaled, action, param, orig_h, orig_w):
                    acted = True
                    break
            if acted:
                time.sleep(ACTION_DELAY)
            else:
                time.sleep(LOOP_INTERVAL)
        self.log_signal.emit("[自动化] 任务自动跳过已停止")
        self.finished_signal.emit()

    def stop(self):
        self.running = False
        self.wait()