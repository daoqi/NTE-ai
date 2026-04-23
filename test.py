import cv2
import numpy as np
import pydirectinput
import win32gui
import time
import threading
import queue
from PIL import ImageGrab

# ========== 配置（全部是窗口客户区相对坐标）==========
WINDOW_KEYWORD = "异环"  # 窗口标题关键字
ROI = (597, 55, 1328, 88)  # 识别区域 (left, top, right, bottom) 窗口相对坐标
TEMPLATE_HS = r"D:\Github\NTE\fishingimages\hs.png"
TEMPLATE_DDS = r"D:\Github\NTE\fishingimages\dds.png"
THRESHOLD = 5  # 重合允许误差（像素）
MATCH_THRESHOLD = 0.8  # 模板匹配相似度
CAPTURE_INTERVAL = 0.02  # 截图间隔（秒）
# =================================================

running = True
pos_queue = queue.Queue(maxsize=1)
current_key = None


def find_hwnd():
    """返回窗口句柄"""

    def callback(hwnd, hwnd_list):
        if win32gui.IsWindowVisible(hwnd) and WINDOW_KEYWORD in win32gui.GetWindowText(hwnd):
            hwnd_list.append(hwnd)

    hwnd_list = []
    win32gui.EnumWindows(callback, hwnd_list)
    return hwnd_list[0] if hwnd_list else None


def find_template(img_gray, template, threshold):
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        h, w = template.shape
        return (max_loc[0] + w // 2, max_loc[1] + h // 2)
    return None


def capture_worker(hwnd, hs_tpl, dds_tpl):
    global running
    l, t, r, b = ROI  # 窗口相对坐标
    # 将窗口相对坐标转为屏幕坐标（仅用于 ImageGrab）
    left_top = win32gui.ClientToScreen(hwnd, (l, t))
    right_bottom = win32gui.ClientToScreen(hwnd, (r, b))
    screen_rect = (left_top[0], left_top[1], right_bottom[0], right_bottom[1])

    while running:
        # 截图（屏幕矩形）
        img_pil = ImageGrab.grab(bbox=screen_rect)
        img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

        hs_rel = find_template(gray, hs_tpl, MATCH_THRESHOLD)
        dds_rel = find_template(gray, dds_tpl, MATCH_THRESHOLD)

        if hs_rel and dds_rel:
            # 转换为窗口相对坐标（识别出的坐标 + ROI左上角）
            hs_x = hs_rel[0] + l
            dds_x = dds_rel[0] + l
            # 清空队列，只保留最新
            while not pos_queue.empty():
                try:
                    pos_queue.get_nowait()
                except:
                    break
            pos_queue.put((hs_x, dds_x))

        time.sleep(CAPTURE_INTERVAL)


def control_worker():
    global running, current_key
    while running:
        try:
            hs_x, dds_x = pos_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        diff = hs_x - dds_x
        target = None
        if diff > THRESHOLD:
            target = 'A'  # 黄色在右侧 -> 按A向左
        elif diff < -THRESHOLD:
            target = 'D'  # 黄色在左侧 -> 按D向右

        if target != current_key:
            if current_key == 'A':
                pydirectinput.keyUp('a')
            elif current_key == 'D':
                pydirectinput.keyUp('d')
            if target == 'A':
                pydirectinput.keyDown('a')
            elif target == 'D':
                pydirectinput.keyDown('d')
            current_key = target

        time.sleep(0.005)


def main():
    hwnd = find_hwnd()
    if not hwnd:
        print("未找到窗口")
        return
    print(f"找到窗口: {win32gui.GetWindowText(hwnd)}")

    hs = cv2.imread(TEMPLATE_HS, cv2.IMREAD_GRAYSCALE)
    dds = cv2.imread(TEMPLATE_DDS, cv2.IMREAD_GRAYSCALE)
    if hs is None or dds is None:
        print("模板图片加载失败")
        return
    print("模板加载成功")

    t1 = threading.Thread(target=capture_worker, args=(hwnd, hs, dds), daemon=True)
    t2 = threading.Thread(target=control_worker, daemon=True)
    t1.start()
    t2.start()

    print("脚本运行中，按 Ctrl+C 退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        global running, current_key
        running = False
        if current_key:
            pydirectinput.keyUp(current_key.lower())
        print("退出")


if __name__ == "__main__":
    main()