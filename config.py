# config.py
from pathlib import Path

APP_NAME = "异环薄荷AI"

def get_version():
    version_file = Path(__file__).resolve().parent / "version.txt"
    if version_file.exists():
        return version_file.read_text(encoding='utf-8').strip()
    return "1.0.0"

VERSION = get_version()

# GitHub 仓库
REPO_OWNER = "daoqi"
REPO_NAME = "NTE-ai"

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "images"

MATCH_THRESHOLD = 0.9
LOOP_INTERVAL = 0.05
ACTION_DELAY = 0.01

TEMPLATES_CONFIG = [
    ("跳过箭头.png", "click", None),
    ("确认.png", "click", None),
    ("下页.png", "click", None),
    ("点击空白区域关闭.png", "click", None),
    ("点击空白区域关闭1.png", "click", None),
   ("点击空白区域关闭2.png", "click", None),
    ("领取.png", "click", None),
    ("跳过.png", "key", "esc"),
    ("不可跳过.png", "center_click", None),
    ("调查F.png", "key", "f"),
    ("查看放大镜F.png", "key", "f"),
    ("3个点点点.png", "key", "f"),
    ("手F.png", "key", "f"),
]