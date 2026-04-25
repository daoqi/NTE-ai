# 改进捕获方法！增加鱼竿摆动速度！无需修改帧数
# 用 WGC 捕获、HSV 绿色区域检测、模板匹配黄色标记，以及范围保持控制逻辑。
import os                     # 导入操作系统接口模块，用于文件和路径操作
import sys                    # 导入系统相关模块，用于获取打包路径等
import time                   # 导入时间模块，用于延时和计时
import threading              # 导入多线程模块，用于异步处理捕获和控制
import queue                  # 导入队列模块，用于线程间安全传递检测结果
import ctypes                 # 导入 ctypes 模块，用于调用 Windows API
from ctypes import wintypes   # 导入 ctypes 的 Windows 类型定义
import cv2                    # 导入 OpenCV 库，用于图像处理和模板匹配
import numpy as np            # 导入 NumPy 库，用于数组操作和 HSV 转换
import win32gui               # 导入 win32gui 库，用于获取窗口信息、坐标转换等
import pydirectinput          # 导入 pydirectinput 库，用于模拟键盘按键（A/D）
from windows_capture import WindowsCapture, Frame, InternalCaptureControl  # 导入 WGC 捕获相关类
def resource_path(relative_path):
    """
    获取资源的绝对路径，兼容开发环境和 PyInstaller 打包后的 exe。
    :param relative_path: 相对路径字符串
    :return: 绝对路径字符串
    """
    try:
        base_path = sys._MEIPASS          # 如果程序被打包成 exe，则根目录在 sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))  # 开发环境则取当前文件所在目录
    return os.path.join(base_path, relative_path)  # 拼接完整路径并返回


# ---------- 配置参数----------

IMG_DIR = "fishingimages"                                     # 存放模板图片的文件夹名称
TEMPLATE_HS = resource_path(os.path.join(IMG_DIR, "hs.png"))  # 黄色标记模板图片的完整路径

# 钓鱼区域内 ROI（客户区相对坐标），根据 1920x1080 窗口设定
ROI = (605, 61, 1322,88)          # (left, top, right, bottom) 钓鱼活动条所在矩形区域

# 绿色评分区域的 HSV 颜色范围下限
GREEN_HSV_LOWER = np.array([60, 100, 150])
# 绿色评分区域的 HSV 颜色范围上限
GREEN_HSV_UPPER = np.array([90, 255, 255])

# 黄色标记模板匹配置信度阈值，高于此值认为匹配成功
YELLOW_MATCH_THRESH = 0.6

# 范围保持控制器参数（加速版）
GREEN_BUFFER_PCT = 0.15          # 绿色区域缓冲区比例（左右各缩进 15%），更早介入调整
PULSE_SCALE = 0.004              # 脉冲系数：每秒每像素的脉冲时长（秒/像素），移动快则脉冲长
PULSE_MIN = 0.008                # 最小脉冲时长（8ms），确保轻推有效
PULSE_MAX = 0.060                # 最大脉冲时长（60ms），限制单次移动距离避免过冲
INTER_PULSE_SLEEP = 0.005        # 两次脉冲之间的间隔（5ms），提高响应频率

# 首帧等待超时，防止 WGC 启动失败时无限等待
FIRST_FRAME_TIMEOUT = 1.0        # 1 秒

# 生产者-消费者队列，单槽位，丢弃旧数据保留最新
detection_queue = queue.Queue(maxsize=1)


# ---------- DWM 裁剪计算 ----------

def get_client_crop(hwnd):
    """
    计算从 WGC 捕获的整个窗口画面中裁剪出纯客户区所需的偏移量。
    参数 hwnd：目标窗口句柄
    返回字典：{'left': 偏移左, 'top': 偏移上, 'width': 客户区宽度, 'height': 客户区高度}
    """
    DWMWA_EXTENDED_FRAME_BOUNDS = 9                                        # DwmGetWindowAttribute 的参数，表示获取窗口扩展边界
    rect = wintypes.RECT()                                                 # 创建 RECT 结构体
    ctypes.windll.dwmapi.DwmGetWindowAttribute(                            # 调用 DwmGetWindowAttribute 获取窗口的扩展边界
        wintypes.HWND(hwnd),                                              # 窗口句柄
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),                        # 属性类型
        ctypes.byref(rect),                                               # 输出矩形指针
        ctypes.sizeof(rect)                                               # 结构体大小
    )
    dwm_left, dwm_top = rect.left, rect.top                               # DWM 报告的窗口左上角坐标（屏幕坐标）

    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))                 # 客户区左上角在屏幕上的坐标
    client_left, client_top = client_origin                               # 客户区左上角屏幕坐标

    client_rect = win32gui.GetClientRect(hwnd)                            # 获取客户区大小（宽高）
    client_w, client_h = client_rect[2], client_rect[3]                   # 客户区宽度和高度

    # 返回在 WGC 帧中裁剪客户区所需的偏移和尺寸
    return {
        'left': client_left - dwm_left,    # 左偏移 = 客户区左边缘 - DWM 窗口左边缘
        'top': client_top - dwm_top,       # 上偏移 = 客户区上边缘 - DWM 窗口上边缘
        'width': client_w,                 # 客户区宽度
        'height': client_h,                # 客户区高度
    }


# ---------- 检测函数 ----------

def detect_green_zone(frame_rgb):
    """
    在指定的 ROI 区域内检测绿色评分带，返回其左右边界 X 坐标（完整帧中的坐标）。
    参数 frame_rgb：RGB 格式的完整帧图像
    返回 (left_x, right_x) 或 None
    """
    roi_l, roi_t, roi_r, roi_b = ROI                                      # 解包 ROI 矩形
    h, w = frame_rgb.shape[:2]                                           # 获取整帧图像高度和宽度
    # 检查 ROI 是否在图像范围内
    if roi_r > w or roi_b > h or roi_l < 0 or roi_t < 0:
        return None                                                      # 超出范围，返回 None

    roi_img = frame_rgb[roi_t:roi_b, roi_l:roi_r]                         # 截取 ROI 区域
    hsv = cv2.cvtColor(roi_img, cv2.COLOR_RGB2HSV)                        # 转换为 HSV 颜色空间
    mask = cv2.inRange(hsv, GREEN_HSV_LOWER, GREEN_HSV_UPPER)             # 创建绿色区域的二值掩膜
    cols = np.any(mask > 0, axis=0)                                       # 按列检查是否存在绿色像素
    indices = np.where(cols)[0]                                           # 获取存在绿色像素的列索引

    if len(indices) == 0:                                                 # 未检测到任何绿色像素
        return None

    # 返回绿色区域的左右边界（相对于完整帧的 X 坐标）
    return (int(indices[0]) + roi_l, int(indices[-1]) + roi_l)


def detect_yellow_marker(frame_rgb, template):
    """
    在 ROI 区域内检测黄色标记（使用模板匹配），返回其中心 X 坐标（完整帧中的坐标）。
    参数 frame_rgb：RGB 格式的完整帧图像
    参数 template：黄色标记的灰度模板图像
    返回中心 X 坐标或 None
    """
    if template is None:                                                 # 模板为空则无法匹配
        return None

    roi_l, roi_t, roi_r, roi_b = ROI                                      # 解包 ROI
    h, w = frame_rgb.shape[:2]                                           # 获取图像尺寸
    if roi_r > w or roi_b > h or roi_l < 0 or roi_t < 0:
        return None                                                      # ROI 越界返回 None

    roi_img = frame_rgb[roi_t:roi_b, roi_l:roi_r]                         # 截取 ROI
    gray = cv2.cvtColor(roi_img, cv2.COLOR_RGB2GRAY)                      # 转为灰度图

    th, tw = template.shape[:2]                                           # 模板高度和宽度
    if gray.shape[0] < th or gray.shape[1] < tw:                          # 图像太小无法匹配模板
        return None

    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)      # 归一化相关系数模板匹配
    _, max_val, _, max_loc = cv2.minMaxLoc(result)                        # 获取最佳匹配位置和相似度
    if max_val < YELLOW_MATCH_THRESH:                                     # 相似度不足则忽略
        return None

    # 计算中心点 X 坐标并转换为完整帧坐标
    return max_loc[0] + tw // 2 + roi_l


# ---------- 捕获工作线程 ----------

class CaptureWorker:
    """
    拥有 WGC 会话，在 WGC 回调中执行检测并将结果推入 detection_queue。
    """
    def __init__(self, hwnd, hs_template, stop_event, first_frame_event):
        """
        初始化捕获工作器。
        :param hwnd: 目标窗口句柄
        :param hs_template: 黄色模板灰度图像
        :param stop_event: 停止事件，设置后停止捕获
        :param first_frame_event: 首帧到达事件，用于通知外部
        """
        self.hwnd = hwnd                             # 保存窗口句柄
        self.hs_template = hs_template               # 保存模板
        self.stop_event = stop_event                 # 保存停止事件
        self.first_frame_event = first_frame_event   # 保存首帧事件
        self.crop = get_client_crop(hwnd)            # 预先计算裁剪偏移（注意：窗口移动后需重新计算，但当前简单处理）
        self.capture_handle = None                   # WGC 会话句柄，用于停止

    def start(self):
        """
        启动 WGC 捕获，并注册事件回调。
        """
        # 创建 WindowsCapture 对象，指定窗口句柄，不捕获鼠标，不绘制边框
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=None,
            window_name=None,
            window_hwnd=self.hwnd,
        )

        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            """
            当新帧到达时调用的回调函数。
            """
            if self.stop_event.is_set():            # 如果收到停止信号
                capture_control.stop()              # 停止捕获
                return

            try:
                # 裁剪出客户区部分
                arr = frame.frame_buffer            # 获取帧数据（BGRA 格式）
                fh, fw = arr.shape[:2]              # 帧高度和宽度
                # 限制裁剪区域在帧范围内
                cl = max(0, min(self.crop['left'], fw))
                ct = max(0, min(self.crop['top'], fh))
                cr = min(cl + self.crop['width'], fw)
                cb = min(ct + self.crop['height'], fh)
                arr = arr[ct:cb, cl:cr]             # 裁切出客户区图像

                rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)   # 转为 RGB 格式供检测函数使用

                # 执行检测
                green = detect_green_zone(rgb)                  # 绿色区域边界
                yellow_x = detect_yellow_marker(rgb, self.hs_template)  # 黄色标记中心 X

                if green is not None and yellow_x is not None:
                    detection = (yellow_x, green[0], green[1])  # 构建检测结果元组
                    # 尝试放入队列，若队列已满则丢弃旧数据再放入最新
                    try:
                        detection_queue.put_nowait(detection)
                    except queue.Full:
                        try:
                            detection_queue.get_nowait()
                            detection_queue.put_nowait(detection)
                        except queue.Empty:
                            pass

                self.first_frame_event.set()        # 标记首帧已收到

            except Exception as e:
                print(f"[capture] frame error: {e}", flush=True)

        @capture.event
        def on_closed():
            """
            捕获会话关闭时的回调（空实现）。
            """
            pass

        self.capture_handle = capture.start_free_threaded()   # 启动捕获（在独立线程中运行）

    def stop(self):
        """
        停止捕获会话。
        """
        if self.capture_handle is not None:          # 如果捕获句柄存在
            try:
                self.capture_handle.stop()           # 尝试停止
            except Exception:
                pass                                 # 忽略停止时的异常
            self.capture_handle = None               # 清空句柄


# ---------- 控制工作线程 ----------

def control_worker(stop_event):
    """
    控制线程的主体函数，实现速度自适应控制。
    当绿色区域移动快时加大脉冲强度，确保黄色标记跟上。
    """
    key_a_down = False           # A 键当前是否按住
    key_d_down = False           # D 键当前是否按住

    # 历史数据用于计算绿色区域移动速度
    prev_green_center = None     # 上一帧绿色区域中心 X 坐标
    prev_timestamp = None        # 上一帧的时间戳

    # 速度自适应参数
    SPEED_SLOW = 50              # 低速阈值（像素/秒），低于此值认为是低速
    SPEED_FAST = 150             # 高速阈值（像素/秒），高于此值认为是高速
    PULSE_SCALE_SLOW = 0.004     # 低速时的脉冲系数（秒/像素）
    PULSE_SCALE_FAST = 0.010     # 高速时的脉冲系数（秒/像素）
    BASE_PULSE_MIN = 0.008       # 最小脉冲时长（秒）
    BASE_PULSE_MAX = 0.080       # 最大脉冲时长（秒）

    def scale_pulse(overshoot_px, speed):
        """
        根据速度动态计算脉冲时长。
        :param overshoot_px: 超出安全区的像素距离
        :param speed: 绿色区域当前移动速度（像素/秒）
        :return: 脉冲时长（秒）
        """
        # 根据速度等级确定脉冲系数
        if speed >= SPEED_FAST:
            pulse_scale = PULSE_SCALE_FAST          # 高速时使用大系数
        elif speed <= SPEED_SLOW:
            pulse_scale = PULSE_SCALE_SLOW          # 低速时使用小系数
        else:
            # 线性插值
            ratio = (speed - SPEED_SLOW) / (SPEED_FAST - SPEED_SLOW)
            pulse_scale = PULSE_SCALE_SLOW + ratio * (PULSE_SCALE_FAST - PULSE_SCALE_SLOW)
        pulse = overshoot_px * pulse_scale           # 脉冲时长 = 超出距离 × 系数
        # 限制在最小最大值之间
        return max(BASE_PULSE_MIN, min(BASE_PULSE_MAX, pulse))

    def release_all():
        """
        释放所有已按下的方向键。
        """
        nonlocal key_a_down, key_d_down
        if key_a_down:                               # 如果按着 A
            pydirectinput.keyUp('a')                 # 松开 A
            key_a_down = False                       # 标记已松开
        if key_d_down:                               # 如果按着 D
            pydirectinput.keyUp('d')                 # 松开 D
            key_d_down = False                       # 标记已松开

    # 主循环，直到停止事件被设置
    while not stop_event.is_set():
        try:
            # 从队列获取检测结果，超时 0.05 秒（防止死循环）
            yellow_x, green_left, green_right = detection_queue.get(timeout=0.05)
        except queue.Empty:                          # 队列为空则继续循环
            continue

        # 计算绿色区域中心 X 坐标
        green_center = (green_left + green_right) // 2

        # 计算绿色区域移动速度（像素/秒）
        current_time = time.time()                   # 当前时间戳
        speed = 0                                    # 初始速度为 0
        if prev_green_center is not None and prev_timestamp is not None:
            dt = current_time - prev_timestamp       # 时间差
            if dt > 0:
                speed = abs(green_center - prev_green_center) / dt  # 速度 = 位移 / 时间
        # 更新上一次的状态
        prev_green_center = green_center
        prev_timestamp = current_time

        # 计算安全区边界（绿色区域左右各缩进缓冲区）
        green_width = green_right - green_left        # 绿色区域宽度
        buffer_px = int(green_width * GREEN_BUFFER_PCT)  # 缓冲区像素数
        target_left = green_left + buffer_px          # 安全区左边界
        target_right = green_right - buffer_px        # 安全区右边界
        if target_left >= target_right:               # 缓冲区过大导致无安全区时，退回到原始绿色边界
            target_left = green_left
            target_right = green_right

        # 判断黄色标记位置并执行相应控制
        if yellow_x < target_left:                    # 黄色标记偏左，需要向右移动（按 D）
            overshoot = target_left - yellow_x        # 超出左安全区的距离
            # 如果超出距离很小且速度很慢，用单次脉冲微调，避免过冲
            if overshoot < int(green_width * 0.1) and speed < SPEED_SLOW:
                release_all()                         # 先释放所有按键
                pulse = scale_pulse(overshoot, speed) # 计算脉冲时长
                pydirectinput.keyDown('d')            # 按下 D
                time.sleep(pulse)                     # 保持脉冲时长
                pydirectinput.keyUp('d')              # 松开 D
                time.sleep(INTER_PULSE_SLEEP)         # 短暂间隔
            else:
                # 否则连续按住 D 键（加速追赶）
                if key_a_down:                        # 如果当前按着 A，先释放 A
                    release_all()
                if not key_d_down:                    # 如果 D 没有按住
                    pydirectinput.keyDown('d')        # 按下 D
                    key_d_down = True                 # 标记 D 已按住
        elif yellow_x > target_right:                 # 黄色标记偏右，需要向左移动（按 A）
            overshoot = yellow_x - target_right       # 超出右安全区的距离
            if overshoot < int(green_width * 0.1) and speed < SPEED_SLOW:
                release_all()
                pulse = scale_pulse(overshoot, speed)
                pydirectinput.keyDown('a')            # 按下 A
                time.sleep(pulse)
                pydirectinput.keyUp('a')
                time.sleep(INTER_PULSE_SLEEP)
            else:
                if key_d_down:                        # 如果当前按着 D，先释放
                    release_all()
                if not key_a_down:                    # 如果 A 没有按住
                    pydirectinput.keyDown('a')        # 按下 A
                    key_a_down = True                 # 标记 A 已按住
        else:                                          # 黄色标记在安全区内
            release_all()                             # 释放所有按键

        # 如果没有按键处于按下状态，短暂休眠减少 CPU 占用
        if not (key_a_down or key_d_down):
            time.sleep(0.005)

    # 循环结束时释放所有按键，确保干净退出
    release_all()


# ---------- 公开 API（与原始 controlfishing.py 相同）----------

def start_follow(stop_event, target_hwnd=None):
    """
    启动钓鱼跟随自动化。
    参数:
        stop_event: threading.Event 对象，设置后停止所有工作线程。
        target_hwnd: 游戏窗口句柄（必填）。
    返回: 成功返回 True，失败返回 False。
    """
    if target_hwnd is None:                                                # 未提供窗口句柄
        print("错误：未传入目标窗口句柄，请通过UI选择钓鱼窗口", flush=True)
        return False

    if not win32gui.IsWindow(target_hwnd):                                 # 窗口句柄无效
        print(f"错误：窗口句柄 {target_hwnd} 无效", flush=True)
        return False

    print(f"使用窗口句柄: {target_hwnd}", flush=True)                       # 输出使用的窗口句柄

    # 加载黄色标记模板
    hs_template = cv2.imread(TEMPLATE_HS, cv2.IMREAD_GRAYSCALE)
    if hs_template is None:                                                # 模板加载失败
        print(f"错误：无法读取 hs.png，路径={TEMPLATE_HS}", flush=True)
        return False

    # 清空之前残留的检测队列数据（防止旧数据干扰）
    while not detection_queue.empty():
        try:
            detection_queue.get_nowait()
        except queue.Empty:
            break

    # 启动捕获工作器
    first_frame_event = threading.Event()                                 # 首帧事件
    capture = CaptureWorker(target_hwnd, hs_template, stop_event, first_frame_event)

    try:
        capture.start()                                                    # 开始 WGC 捕获
    except Exception as e:
        print(f"错误：WGC 启动失败 {e}", flush=True)
        return False

    # 等待首帧到达（确认捕获已工作）
    if not first_frame_event.wait(timeout=FIRST_FRAME_TIMEOUT):
        print(f"警告：{FIRST_FRAME_TIMEOUT}秒内未收到首帧，可能捕获失败", flush=True)
        # 即使未收到首帧也继续，有可能稍后恢复
    else:
        print("捕获已启动", flush=True)

    # 启动控制线程
    control_thread = threading.Thread(
        target=control_worker,
        args=(stop_event,),
        daemon=True,                           # 设为守护线程，主程序退出时自动结束
        name="fishing-control",
    )
    control_thread.start()

    # 将捕获对象挂载到 stop_event 上，以便外部可能清理（原 API 无返回，但后续可通过 stop_event 访问）
    stop_event._capture_worker = capture

    print("开始跟随...", flush=True)            # 输出开始信息
    return True                               # 返回成功