# auto_updater.py
import sys
import os
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
from urllib.request import urlopen, urlretrieve
from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt
from config import REPO_OWNER, REPO_NAME, VERSION

class AutoUpdater:
    def __init__(self):
        self.repo_owner = REPO_OWNER
        self.repo_name = REPO_NAME
        self.current_version = VERSION
        self.raw_base = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/main/"

    def get_remote_version(self):
        if not self.repo_owner or not self.repo_name:
            return None
        try:
            version_url = self.raw_base + "version.txt"
            with urlopen(version_url, timeout=5) as resp:
                remote_version = resp.read().decode('utf-8').strip()
                return remote_version
        except Exception:
            return None

    def download_and_apply_update(self, progress_callback=None):
        try:
            zip_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/refs/heads/main.zip"
            temp_zip = tempfile.mktemp(suffix=".zip")
            urlretrieve(zip_url, temp_zip, reporthook=progress_callback)
            extract_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            src_folder = Path(extract_dir) / f"{self.repo_name}-main"
            current_dir = Path.cwd()
            for item in src_folder.iterdir():
                dest = current_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            shutil.rmtree(extract_dir)
            os.remove(temp_zip)
            return True
        except Exception:
            return False

    def check_and_update(self, parent_window):
        if not self.repo_owner or not self.repo_name:
            return False
        remote_ver = self.get_remote_version()
        if remote_ver is None or remote_ver <= self.current_version:
            return False
        reply = QMessageBox.question(parent_window, "发现新版本",
                                     f"当前版本 {self.current_version}，最新版本 {remote_ver}\n是否立即更新？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            progress = QProgressDialog("正在下载更新...", "取消", 0, 100, parent_window)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            def report(blocknum, blocksize, totalsize):
                if progress.wasCanceled():
                    raise Exception("用户取消更新")
                if totalsize > 0:
                    percent = int(blocknum * blocksize * 100 / totalsize)
                    progress.setValue(percent)
            try:
                if self.download_and_apply_update(report):
                    progress.setValue(100)
                    QMessageBox.information(parent_window, "更新完成", "已下载最新版本，程序将重启。")
                    self.restart_program()
            except Exception:
                QMessageBox.warning(parent_window, "更新取消", "更新已取消或失败")
        return False

    @staticmethod
    def restart_program():
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)