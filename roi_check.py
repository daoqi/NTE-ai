from PIL import ImageGrab, ImageDraw
import win32gui
import sys
import os

OUTPUT_DIR = 'debug_screenshots'  # folder name relative to current directory


# The ROI from controlfishing.py
ROI = (597, 61, 1328, 85)

def find_game_window():
    """Find the 异环 game window, excluding the NTE-ai UI itself."""
    matches = []
    
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "异环" in title and "异环薄荷AI" not in title:
                matches.append((hwnd, title))
    
    win32gui.EnumWindows(enum_cb, None)
    return matches

def main():
    windows = find_game_window()
    
    if not windows:
        print("[错误] 未找到异环游戏窗口。请先启动游戏。")
        sys.exit(1)
    
    if len(windows) > 1:
        print(f"[警告] 找到多个匹配窗口:")
        for i, (hwnd, title) in enumerate(windows):
            print(f"  {i}: hwnd={hwnd}, title={title}")
        print("使用第一个。")
    
    hwnd, title = windows[0]
    print(f"[信息] 使用窗口: {title} (hwnd={hwnd})")
    
    # Get window position info for diagnostics
    client_rect = win32gui.GetClientRect(hwnd)
    print(f"[信息] 客户区大小: {client_rect[2]}x{client_rect[3]}")
    
    # Convert ROI window-relative coords to screen coords
    l, t, r, b = ROI
    left_top = win32gui.ClientToScreen(hwnd, (l, t))
    right_bottom = win32gui.ClientToScreen(hwnd, (r, b))
    
    print(f"[信息] ROI 窗口坐标: ({l}, {t}) -> ({r}, {b})")
    print(f"[信息] ROI 屏幕坐标: {left_top} -> {right_bottom}")
    
    # Full screen capture
    img = ImageGrab.grab()
    draw = ImageDraw.Draw(img)
    
    # Draw red rectangle around ROI
    draw.rectangle([left_top, right_bottom], outline='red', width=3)
    
    # Make sure output folder exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    output_path = os.path.join(OUTPUT_DIR, 'roi_check.png')

    # Save and open
    img.save(output_path)
    print(f"[完成] 已保存到 {output_path}，请打开查看红框是否对准钓鱼条。")

if __name__ == "__main__":
    main()