# ui.py
import sys
import os
import subprocess
import threading
import queue
from pathlib import Path
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QLabel, QTabWidget, QGroupBox,
                             QGridLayout, QMessageBox, QApplication, QGraphicsDropShadowEffect,
                             QLineEdit)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QIcon, QColor
import pyautogui
import pygetwindow as gw

from config import APP_NAME, VERSION, IMAGES_DIR
from automation_thread import AutomationThread
from auto_updater import AutoUpdater
from floating_log import FloatingLogWindow
QTimer.singleShot(1500, self.check_for_updates)
class HotKeySignals(QObject):
    toggle_signal = pyqtSignal()

class NeonMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.setGeometry(200, 100, 900, 700)

        # 图标
        if Path("Windowslogo.ico").exists():
            self.setWindowIcon(QIcon("Windowslogo.ico"))
        if Path("titlelogo.ico").exists():
            self.setWindowIcon(QIcon("titlelogo.ico"))

        self.setStyleSheet("""
            QMainWindow { background-color: #0a0f1e; }
            QTabWidget::pane { border: 2px solid #00ffcc; background-color: #111826; border-radius: 10px; }
            QTabBar::tab { background-color: #1a2332; color: #ccfffc; font: bold 14px "Microsoft YaHei"; padding: 10px 20px; margin: 5px; border-radius: 8px; }
            QTabBar::tab:selected { background-color: #00ccbb; color: #0a0f1e; border: 1px solid #00ffcc; }
            QTabBar::tab:hover { background-color: #2a3a55; }
            QPushButton { background-color: #1e2a3a; color: #00ffcc; border: 1px solid #00ffcc; border-radius: 12px; padding: 8px 16px; font: bold 12px "Microsoft YaHei"; }
            QPushButton:hover { background-color: #00ccbb; color: #0a0f1e; }
            QPushButton:pressed { background-color: #009999; }
            QGroupBox { border: 1px solid #00ffcc; border-radius: 8px; margin-top: 12px; font: bold 12px "Microsoft YaHei"; color: #00ffcc; }
            QGroupBox::title { subcontrol-origin: margin; left: 15px; padding: 0 8px; }
            QTextEdit, QLabel, QLineEdit { background-color: #0f1622; color: #ccfffc; border: 1px solid #2a3a55; border-radius: 6px; font: 10pt "Consolas"; }
            QLabel#codeLabel { background-color: #1a2332; border: 1px solid #00ffcc; border-radius: 6px; padding: 6px; font: 10pt "Microsoft YaHei"; }
            QLabel#codeLabel:hover { background-color: #2a3a55; border: 1px solid #00ffff; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 创建五个选项卡
        self.tab_skip = QWidget()
        self.tab_battle = QWidget()
        self.tab_codes = QWidget()
        self.tab_fishing = QWidget()
        self.tab_mahjong = QWidget()
        self.tab_widget.addTab(self.tab_skip, "✨快速剧情")
        self.tab_widget.addTab(self.tab_battle, "⚔️战斗宏")
        self.tab_widget.addTab(self.tab_codes, "🎁兑奖码")
        self.tab_widget.addTab(self.tab_fishing, "🎣AI钓鱼")
        self.tab_widget.addTab(self.tab_mahjong, "🀄AI麻将")

        # 初始化各个选项卡
        self.init_tab_skip()
        self.init_tab_battle()
        self.init_tab_codes()
        self.init_tab_fishing()
        self.init_tab_mahjong()

        # 自动化线程相关
        self.automation_thread = None
        self.target_window_title = ""

        # 浮动日志窗口
        self.floating_log = FloatingLogWindow()

        # 钓鱼子进程相关
        self.fishing_process = None
        self.fishing_stdout_queue = queue.Queue()
        self.fishing_output_thread = None
        self.fishing_error_thread = None
        self.fishing_timer = None

        # 霓虹外发光效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 255, 204, 120))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        # 自动检测异环窗口
        QTimer.singleShot(500, self.auto_detect_window)

        # 全局热键 F12
        self.hotkey_signals = HotKeySignals()
        self.hotkey_signals.toggle_signal.connect(self.toggle_automation)
        self.start_hotkey_listener()

    # ---------- 全局热键 ----------
    def start_hotkey_listener(self):
        from pynput import keyboard
        def on_press(key):
            try:
                if key == keyboard.Key.f12:
                    self.hotkey_signals.toggle_signal.emit()
            except:
                pass
        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()

    def toggle_automation(self):
        if self.automation_thread and self.automation_thread.isRunning():
            self.stop_automation()
        else:
            self.start_automation()

    # ---------- 页面1：任务自动跳过 ----------
    def init_tab_skip(self):
        layout = QVBoxLayout(self.tab_skip)
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ 开始跳过任务")
        self.stop_btn = QPushButton("⏹️ 停止跳过")
        self.stop_btn.setEnabled(False)
        self.show_log_btn = QPushButton("📺 显示游戏内日志")
        self.start_btn.clicked.connect(self.start_automation)
        self.stop_btn.clicked.connect(self.stop_automation)
        self.show_log_btn.clicked.connect(self.toggle_floating_log)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.show_log_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("🎯 目标窗口标题（关键字）："))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例如：异环")
        self.title_edit.setMinimumWidth(300)
        self.detect_btn = QPushButton("🔍 自动检测异环窗口")
        self.detect_btn.clicked.connect(self.auto_detect_window)
        title_layout.addWidget(self.title_edit)
        title_layout.addWidget(self.detect_btn)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        log_label = QLabel("📋 执行日志")
        log_label.setStyleSheet("font: bold 12px; color:#00ffcc;")
        layout.addWidget(log_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(400)
        layout.addWidget(self.log_text)

        tip = QLabel("💡 提示：程序启动时自动检测“异环”窗口。全局热键 F12 启动/停止。\n游戏内日志窗口可拖动到游戏画面上方，实时显示操作。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#88aaff; font-size:10px;")
        layout.addWidget(tip)

    def auto_detect_window(self):
        try:
            windows = gw.getWindowsWithTitle("异环")
            if windows:
                title = windows[0].title
                self.title_edit.setText(title)
                self.log_signal_ui(f"[自动检测] 找到异环窗口: {title}")
            else:
                self.log_signal_ui("[自动检测] 未找到异环窗口，请手动输入窗口标题关键字")
        except Exception as e:
            self.log_signal_ui(f"[自动检测] 出错: {e}")

    def toggle_floating_log(self):
        if self.floating_log.isVisible():
            self.floating_log.hide()
        else:
            self.floating_log.show()

    # ---------- 页面2：自动战斗（占位）----------
    def init_tab_battle(self):
        layout = QVBoxLayout(self.tab_battle)
        group = QGroupBox("自动战斗 (开发中)")
        group_layout = QVBoxLayout(group)
        info_label = QLabel("⚙️ 自动战斗功能正在加紧开发，敬请期待！")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 14px; color: #ffaa88; padding: 20px;")
        group_layout.addWidget(info_label)
        group_layout.addStretch()
        layout.addWidget(group)

    # ---------- 页面3：兑奖码仓库 ----------
    def init_tab_codes(self):
        layout = QVBoxLayout(self.tab_codes)
        layout.setSpacing(20)
        latest_group = QGroupBox("✨ 最新兑奖码（点击复制）")
        latest_layout = QVBoxLayout(latest_group)
        latest_codes = ["YHNOWTOENJOY", "YHNANALLYGO", "YHOB0423"]
        latest_grid = QGridLayout()
        for idx, code in enumerate(latest_codes):
            lbl = self.create_copyable_label(code)
            latest_grid.addWidget(lbl, idx // 2, idx % 2)
        latest_layout.addLayout(latest_grid)
        layout.addWidget(latest_group)

        history_group = QGroupBox("📜 历史兑奖码")
        history_layout = QVBoxLayout(history_group)
        history_codes = ["YHNOWTOENJOY", "YHNANALLYGO", "YHOB0423"]
        history_grid = QGridLayout()
        for idx, code in enumerate(history_codes):
            lbl = self.create_copyable_label(code)
            history_grid.addWidget(lbl, idx // 2, idx % 2)
        history_layout.addLayout(history_grid)
        layout.addWidget(history_group)

        info = QLabel("💡 点击任意兑奖码即可复制到剪贴板。")
        info.setStyleSheet("color:#aaaaff; font-size:10px; margin-top: 10px;")
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        layout.addStretch()

    # ---------- 页面4：AI 钓鱼（调用外部脚本，编码修复）----------
    def init_tab_fishing(self):
        layout = QVBoxLayout(self.tab_fishing)
        btn_layout = QHBoxLayout()
        self.start_fishing_btn = QPushButton("🎣 开始钓鱼")
        self.stop_fishing_btn = QPushButton("⏹️ 停止钓鱼")
        self.stop_fishing_btn.setEnabled(False)
        self.start_fishing_btn.clicked.connect(self.start_fishing)
        self.stop_fishing_btn.clicked.connect(self.stop_fishing)
        btn_layout.addWidget(self.start_fishing_btn)
        btn_layout.addWidget(self.stop_fishing_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.fishing_log = QTextEdit()
        self.fishing_log.setReadOnly(True)
        self.fishing_log.setMaximumHeight(400)
        layout.addWidget(QLabel("📋 钓鱼日志"))
        layout.addWidget(self.fishing_log)

        tip = QLabel("💡 提示：钓鱼逻辑使用独立的 fishing.py 和 controlfishing.py。\n如果启动后立即退出，请先在命令行运行 fishing.py 检查错误。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#88aaff;")
        layout.addWidget(tip)

    def start_fishing(self):
        if self.fishing_process and self.fishing_process.poll() is None:
            self.log_to_fishing("[警告] 钓鱼进程已在运行")
            return
        script_path = os.path.join(os.path.dirname(__file__), "fishing.py")
        if not os.path.exists(script_path):
            self.log_to_fishing(f"[错误] 找不到钓鱼脚本: {script_path}")
            return
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # 关键：使用 utf-8 编码，并忽略解码错误
        self.fishing_process = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0,
            cwd=os.path.dirname(__file__),
            env=env,
            encoding='utf-8',
            errors='replace'
        )
        self.start_fishing_btn.setEnabled(False)
        self.stop_fishing_btn.setEnabled(True)
        self.log_to_fishing(f"[系统] 钓鱼进程已启动 (PID: {self.fishing_process.pid})")
        while not self.fishing_stdout_queue.empty():
            try:
                self.fishing_stdout_queue.get_nowait()
            except:
                break
        self.fishing_output_thread = threading.Thread(target=self._read_fishing_output, daemon=True)
        self.fishing_error_thread = threading.Thread(target=self._read_fishing_error, daemon=True)
        self.fishing_output_thread.start()
        self.fishing_error_thread.start()
        self.fishing_timer = QTimer()
        self.fishing_timer.timeout.connect(self._update_fishing_log)
        self.fishing_timer.start(50)

    def _read_fishing_output(self):
        if not self.fishing_process:
            return
        try:
            for line in iter(self.fishing_process.stdout.readline, ''):
                if line:
                    self.fishing_stdout_queue.put(line.strip())
                if self.fishing_process.poll() is not None:
                    break
        except Exception as e:
            self.fishing_stdout_queue.put(f"[读取输出异常] {e}")

    def _read_fishing_error(self):
        if not self.fishing_process:
            return
        try:
            for line in iter(self.fishing_process.stderr.readline, ''):
                if line:
                    self.fishing_stdout_queue.put(f"[STDERR] {line.strip()}")
                if self.fishing_process.poll() is not None:
                    break
        except Exception as e:
            self.fishing_stdout_queue.put(f"[读取错误流异常] {e}")

    def _update_fishing_log(self):
        while not self.fishing_stdout_queue.empty():
            try:
                line = self.fishing_stdout_queue.get_nowait()
                self.log_to_fishing(line)
            except:
                break
        if self.fishing_process and self.fishing_process.poll() is not None:
            self._on_fishing_finished()

    def stop_fishing(self):
        if self.fishing_process and self.fishing_process.poll() is None:
            self.log_to_fishing("[系统] 正在终止钓鱼进程...")
            self.fishing_process.terminate()
            try:
                self.fishing_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.fishing_process.kill()
                self.log_to_fishing("[系统] 强制终止钓鱼进程")
            self.log_to_fishing("[系统] 钓鱼进程已终止")
        else:
            self.log_to_fishing("[系统] 没有运行中的钓鱼进程")
        self._on_fishing_finished()

    def _on_fishing_finished(self):
        if self.fishing_timer and self.fishing_timer.isActive():
            self.fishing_timer.stop()
        self.start_fishing_btn.setEnabled(True)
        self.stop_fishing_btn.setEnabled(False)
        self.fishing_process = None
        self.log_to_fishing("[系统] 钓鱼进程已退出")

    def log_to_fishing(self, msg):
        from utils import log_message
        self.fishing_log.append(log_message(msg))
        scroll = self.fishing_log.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    # ---------- 页面5：AI 麻将（占位）----------
    def init_tab_mahjong(self):
        layout = QVBoxLayout(self.tab_mahjong)
        group = QGroupBox("🀄 AI 麻将（开发中）")
        group_layout = QVBoxLayout(group)
        info_label = QLabel("🀄 智能麻将 AI 正在开发中\n\n功能规划：\n• 自动识别手牌\n• 智能出牌策略\n• 听牌检测")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 13px; color: #ffcc88; padding: 30px; line-height: 1.8;")
        group_layout.addWidget(info_label)
        group_layout.addStretch()
        layout.addWidget(group)

    # ---------- 辅助方法 ----------
    def create_copyable_label(self, code: str):
        lbl = QLabel(code)
        lbl.setObjectName("codeLabel")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip(f"点击复制: {code}")
        lbl.setMinimumWidth(200)
        def on_click():
            clipboard = QApplication.clipboard()
            clipboard.setText(code)
            self.log_signal_ui(f"[复制] 兑奖码 '{code}' 已复制")
            original_style = lbl.styleSheet()
            lbl.setStyleSheet("QLabel#codeLabel { background-color: #00aa99; border:1px solid yellow; }")
            QTimer.singleShot(200, lambda: lbl.setStyleSheet(original_style))
        lbl.mousePressEvent = lambda event: on_click()
        return lbl

    # ---------- 自动化控制 ----------
    def start_automation(self):
        if self.automation_thread and self.automation_thread.isRunning():
            self.log_signal_ui("[警告] 自动化已在运行")
            return
        if not IMAGES_DIR.exists():
            self.log_signal_ui(f"[错误] 模板目录不存在: {IMAGES_DIR}")
            return
        window_title = self.title_edit.text().strip()
        if not window_title:
            self.auto_detect_window()
            window_title = self.title_edit.text().strip()
            if not window_title:
                self.log_signal_ui("[错误] 请输入目标窗口标题关键字（如“异环”）")
                return
        self.target_window_title = window_title
        self.automation_thread = AutomationThread(str(IMAGES_DIR), window_title=self.target_window_title)
        self.automation_thread.log_signal.connect(self.log_signal_ui)
        self.automation_thread.game_log_signal.connect(self.floating_log.append_log)
        self.automation_thread.finished_signal.connect(self.on_automation_finished)
        self.automation_thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_signal_ui("[系统] 自动化线程已启动")

    def stop_automation(self):
        if self.automation_thread and self.automation_thread.isRunning():
            self.automation_thread.stop()
            self.log_signal_ui("[系统] 正在停止自动化...")
        else:
            self.log_signal_ui("[系统] 没有运行中的线程")

    def on_automation_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_signal_ui("[系统] 自动化线程已停止")

    def log_signal_ui(self, msg: str):
        from utils import log_message
        self.log_text.append(log_message(msg))
        scroll = self.log_text.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def check_for_updates(self):
        updater = AutoUpdater()
        updater.check_and_update(self)

    def closeEvent(self, event):
        if hasattr(self, 'listener') and self.listener.is_alive():
            self.listener.stop()
        if self.floating_log:
            self.floating_log.close()
        if self.automation_thread and self.automation_thread.isRunning():
            self.automation_thread.stop()
            self.automation_thread.wait(1000)
        if self.fishing_process and self.fishing_process.poll() is None:
            self.stop_fishing()
        event.accept()