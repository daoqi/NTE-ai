# floating_log.py
from PyQt5.QtWidgets import QWidget, QTextEdit, QVBoxLayout, QPushButton, QHBoxLayout, QLabel, QApplication
from PyQt5.QtCore import Qt, QPoint

class FloatingLogWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 0, 0, 200);
                border: 2px solid #00ffcc;
                border-radius: 8px;
            }
            QTextEdit {
                background-color: rgba(0, 0, 0, 0);
                color: #00ffcc;
                border: none;
                font: 10pt "Consolas";
            }
            QPushButton {
                background-color: #1e2a3a;
                color: #00ffcc;
                border: 1px solid #00ffcc;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #00ccbb;
                color: #0a0f1e;
            }
        """)
        self.setFixedSize(400, 250)
        self.drag_pos = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        title_layout = QHBoxLayout()
        self.title_label = QLabel("📜 异环游戏日志 (可拖动)")
        self.title_label.setStyleSheet("color: #00ffcc; background: transparent;")
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.clicked.connect(self.hide)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.close_btn)
        layout.addLayout(title_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # 限制最大行数（QTextEdit使用文档块限制）
        self.log_text.document().setMaximumBlockCount(50)
        layout.addWidget(self.log_text)

        self.setWindowTitle("异环日志")
        self.hide()

    def append_log(self, msg):
        self.log_text.append(msg)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def showEvent(self, event):
        screen_geometry = QApplication.desktop().availableGeometry()
        self.move(screen_geometry.width() - self.width() - 20,
                  screen_geometry.height() - self.height() - 50)
        super().showEvent(event)