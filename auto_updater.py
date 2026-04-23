# auto_updater.py
import sys
import os
import json
import zipfile
import tempfile
import subprocess
import shutil
from pathlib import Path
from urllib.request import urlopen, urlretrieve
from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import Qt
from config import REPO_OWNER, REPO_NAME, VERSION

class AutoUpdater:
    def __init__(self):
        self.owner = REPO_OWNER
        self.repo = REPO_NAME
        self.current_version = VERSION

    def get_latest_release(self):
        """从 GitHub API 获取最新 Release 信息"""
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        try:
            with urlopen(api_url, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data
        except Exception as e:
            print(f"[更新] 获取最新 Release 失败: {e}")
            return None

    def check_and_update(self, parent_window):
        release = self.get_latest_release()
        if not release:
            return
        remote_tag = release.get('tag_name', '').lstrip('v')   # 去掉 'v' 前缀
        if remote_tag > self.current_version:
            # 提示用户更新
            reply = QMessageBox.question(parent_window, "发现新版本",
                                         f"当前版本 v{self.current_version}\n最新版本 v{remote_tag}\n是否立即更新？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                # 下载附件
                assets = release.get('assets', [])
                if not assets:
                    QMessageBox.warning(parent_window, "更新失败", "Release 中没有可下载的附件")
                    return
                # 取第一个 zip 附件（约定打包为 Source code.zip 或自定义名称）
                zip_url = assets[0]['browser_download_url']
                self.download_and_apply_update(zip_url, parent_window)

    def download_and_apply_update(self, url, parent_window):
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
            temp_zip = tempfile.mktemp(suffix=".zip")
            urlretrieve(url, temp_zip, reporthook=report)

            extract_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(temp_zip, 'r') as zf:
                zf.extractall(extract_dir)

            # 获取解压后唯一子文件夹（GitHub Action 打包的文件夹名可能为 仓库名-版本号）
            extracted_items = list(Path(extract_dir).iterdir())
            if len(extracted_items) != 1 or not extracted_items[0].is_dir():
                # 如果不是单文件夹，则把所有文件直接替换到当前目录
                src_dir = Path(extract_dir)
            else:
                src_dir = extracted_items[0]

            # 覆盖当前程序所在目录（保留虚拟环境和用户数据）
            current_dir = Path.cwd()
            for item in src_dir.iterdir():
                dest = current_dir / item.name
                if dest.is_dir() and dest.name in ['venv', 'venv_clean', '__pycache__', '.git', '.idea', 'fishingimages', 'images']:
                    continue  # 跳过虚拟环境、图片目录等用户数据目录
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # 清理临时文件
            shutil.rmtree(extract_dir)
            os.remove(temp_zip)

            progress.setValue(100)
            QMessageBox.information(parent_window, "更新完成", "已更新到最新版本，程序将重启。")
            self.restart_program()
        except Exception as e:
            QMessageBox.warning(parent_window, "更新失败", f"下载或替换文件失败: {e}")

    @staticmethod
    def restart_program():
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)