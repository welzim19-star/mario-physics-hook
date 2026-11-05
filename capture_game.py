import ctypes
from ctypes import wintypes
import sys
import os
from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

def switch_to_input_desktop():
    input_desk = user32.OpenInputDesktop(0, False, 0x01FF)
    if input_desk:
        user32.SetThreadDesktop(input_desk)

def find_elden_ring_window():
    switch_to_input_desktop()
    found_hwnd = None
    def enum_cb(hwnd, lparam):
        nonlocal found_hwnd
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if "ELDEN RING" in buff.value.upper():
                    found_hwnd = hwnd
                    return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found_hwnd

def capture_window(hwnd, output_path):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False, f"Invalid dimensions: {w}x{h}"

    hwnd_dc = user32.GetDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mem_dc, bitmap)

    # PrintWindow with PW_RENDERFULLCONTENT (2)
    PW_RENDERFULLCONTENT = 2
    res = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
    if not res:
        # Fallback to BitBlt
        gdi32.BitBlt(mem_dc, 0, 0, w, h, hwnd_dc, 0, 0, 0x00CC0020) # SRCCOPY

    bmp_info = bytearray(40)
    # BITMAPINFOHEADER
    ctypes.c_uint32.from_buffer(bmp_info, 0).value = 40 # biSize
    ctypes.c_int32.from_buffer(bmp_info, 4).value = w    # biWidth
    ctypes.c_int32.from_buffer(bmp_info, 8).value = -h   # biHeight (top-down)
    ctypes.c_uint16.from_buffer(bmp_info, 12).value = 1  # biPlanes
    ctypes.c_uint16.from_buffer(bmp_info, 14).value = 32 # biBitCount
    ctypes.c_uint32.from_buffer(bmp_info, 16).value = 0  # biCompression (BI_RGB)

    buf = bytearray(w * h * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, h, (ctypes.c_char * len(buf)).from_buffer(buf), (ctypes.c_char * 40).from_buffer(bmp_info), 0)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    # Convert to PIL Image
    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
    img = img.convert('RGB')
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=85)
    return True, f"Saved {w}x{h} to {output_path}"

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "game_screen.jpg"
    hwnd = find_elden_ring_window()
    if not hwnd:
        print("[ERRO] Janela do Elden Ring nao encontrada. O jogo esta aberto?")
        sys.exit(1)
    
    success, msg = capture_window(hwnd, out)
    print(f"[{'SUCESSO' if success else 'ERRO'}] {msg}")
