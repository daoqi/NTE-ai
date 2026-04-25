import sys
import os
import time
import threading
import random
import pydirectinput
import win32gui
from PIL import ImageGrab
import cv2
import numpy as np
import controlfishing_v2 as controlfishing
import traceback

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

IMG_DIR = "fishingimages"
PATH_DIAOYU = resource_path(os.path.join(IMG_DIR, "diaoyu.png"))
PATH_KAISHIDIAOYU = resource_path(os.path.join(IMG_DIR, "kaishidiaoyu.png"))
PATH_DIANJIKONGBAI = resource_path(os.path.join(IMG_DIR, "dianjikongbai.png"))
PATH_PANDUANDIAOYU = resource_path(os.path.join(IMG_DIR, "panduandiaoyu.png"))
PATH_YU1 = resource_path(os.path.join(IMG_DIR, "yu1.png"))
PATH_YU = resource_path(os.path.join(IMG_DIR, "yu.png"))

MATCH_THRESH = 0.7
global_stop = threading.Event()
fish_count = 0

def smart_sleep(seconds, interval=0.05):
    if seconds <= 0:
        return
    elapsed = 0
    while elapsed < seconds and not global_stop.is_set():
        time.sleep(min(interval, seconds - elapsed))
        elapsed += interval

def find_image(template_path, region=None):
    try:
        img = ImageGrab.grab(bbox=region) if region else ImageGrab.grab()
        gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return None
        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= MATCH_THRESH:
            h, w = template.shape
            return (max_loc[0] + w//2, max_loc[1] + h//2)
    except Exception as e:
        print(f"[fishing] find_image error: {e}")
    return None

def random_click(pos, offset=10):
    x = pos[0] + random.randint(-offset, offset)
    y = pos[1] + random.randint(-offset, offset)
    pydirectinput.moveTo(x, y)
    time.sleep(0.02)
    pydirectinput.click()
    time.sleep(0.02)

def fish_logic():
    global fish_count
    try:
        # 第一阶段
        print("开始监测：diaoyu, kaishidiaoyu, dianjikongbai, panduandiaoyu ...")
        last_prompt = time.time()
        while not global_stop.is_set():
            pos = find_image(PATH_DIAOYU)
            if pos:
                print("发现 diaoyu.png，按F")
                pydirectinput.press('f')
                time.sleep(0.02)
                continue
            pos = find_image(PATH_KAISHIDIAOYU)
            if pos:
                print("发现 kaishidiaoyu.png，随机点击")
                random_click(pos)
                continue
            pos = find_image(PATH_DIANJIKONGBAI)
            if pos:
                print("发现 dianjikongbai.png，随机点击")
                random_click(pos)
                continue
            pos = find_image(PATH_PANDUANDIAOYU)
            if pos:
                print("发现 panduandiaoyu.png，按F退出监测")
                pydirectinput.press('f')
                break
            if time.time() - last_prompt > 3:
                print("监测中... (等待任意图片)")
                last_prompt = time.time()
            time.sleep(0.02)

        # 第二阶段
        print("等待 yu1.png 和 yu.png ...")
        found1 = False
        found2 = False
        while (not found1 or not found2) and not global_stop.is_set():
            if not found1:
                pos1 = find_image(PATH_YU1)
                if pos1:
                    print("找到 yu1.png，按F")
                    pydirectinput.press('f')
                    found1 = True
            if not found2:
                pos2 = find_image(PATH_YU)
                if pos2:
                    print("找到 yu.png，按F")
                    pydirectinput.press('f')
                    found2 = True
            time.sleep(0.05)
        if not (found1 and found2):
            print("未同时找到两个鱼图")
            return False

        # 第三阶段：启动跟随，必须从环境变量获取窗口句柄
        print("开始跟随...")
        stop_event = threading.Event()
        target_hwnd_str = os.environ.get("FISHING_TARGET_HWND")
        if target_hwnd_str is None:
            print("错误：未接收到目标窗口句柄，请通过UI选择钓鱼窗口")
            return False
        target_hwnd = int(target_hwnd_str)
        print(f"接收到窗口句柄: {target_hwnd}")
        if not controlfishing.start_follow(stop_event, target_hwnd=target_hwnd):
            print("跟随启动失败")
            return False

        # 第四阶段
        print("等待 dianjikongbai.png（成功）或 panduandiaoyu.png（逃走）...")
        last_print = time.time()
        result = None
        target_pos = None
        start_wait = time.time()
        timeout = 15
        while not global_stop.is_set():
            pos_success = find_image(PATH_DIANJIKONGBAI)
            if pos_success:
                result = 'success'
                target_pos = pos_success
                break
            pos_escape = find_image(PATH_PANDUANDIAOYU)
            if pos_escape:
                result = 'escape'
                break
            if time.time() - start_wait > timeout:
                print("超时未出现信号，按逃走处理")
                result = 'escape'
                break
            if time.time() - last_print > 3:
                print("等待中... (成功: dianjikongbai, 逃走: panduandiaoyu)")
                last_print = time.time()
            time.sleep(0.05)

        stop_event.set()
        if result == 'success':
            print("出现 dianjikongbai.png，随机点击中心")
            random_click(target_pos)
            fish_count += 1
            print(f"跟随结束，鱼+1，总鱼数: {fish_count}")
            return True
        else:
            print("鱼逃走了！")
            return False
    except Exception as e:
        print(f"fish_logic 异常: {e}")
        traceback.print_exc()
        return False

def main():
    print("开始钓鱼，按 Ctrl+C 可中断")
    try:
        while not global_stop.is_set():
            success = fish_logic()
            if not success:
                print("本次钓鱼失败，3秒后重试...")
                smart_sleep(3)
            else:
                print("钓鱼成功，继续下一杆...")
                smart_sleep(1)
    except KeyboardInterrupt:
        global_stop.set()
        print("用户中断")
    except Exception as e:
        print(f"主循环异常: {e}")
        traceback.print_exc()
    finally:
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('d')
        print(f"总共钓鱼 {fish_count} 条")

if __name__ == "__main__":
    main()