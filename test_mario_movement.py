import ctypes
from ctypes import wintypes
import time
import subprocess
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

hwnd = find_elden_ring_window()
print(f"Elden Ring hwnd: 0x{hwnd:x}" if hwnd else "Elden Ring hwnd: None")

if hwnd:
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)

SCAN_W = 0x11
SCAN_SPACE = 0x39
VK_W = 0x57
VK_SPACE = 0x20
KEYEVENTF_KEYUP = 0x0002

def key_down(vk, scan):
    user32.keybd_event(vk, scan, 0, 0)

def key_up(vk, scan):
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)

print("[INPUT] Pressionando W (andar para frente)...")
key_down(VK_W, SCAN_W)
time.sleep(0.8)

print("[INPUT] Pressionando SPACE (Pulo acrobatico do Mario)...")
key_down(VK_SPACE, SCAN_SPACE)
time.sleep(0.15)
key_up(VK_SPACE, SCAN_SPACE)
time.sleep(0.8)

key_up(VK_W, SCAN_W)
print("[INPUT] Movimento concluido!")

# Agora captura screenshot imediatamente
if hwnd:
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w > 0 and h > 0:
        hwnd_dc = user32.GetDC(hwnd)
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
        gdi32.SelectObject(mem_dc, bitmap)
        user32.PrintWindow(hwnd, mem_dc, 2)
        
        bmi = bytearray(40)
        import struct
        struct.pack_into('<IiiHHIIiiII', bmi, 0, 40, w, -h, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
        pixels = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem_dc, bitmap, 0, h, pixels, bytes(bmi), 0)
        
        img = Image.frombuffer('RGBA', (w, h), pixels.raw, 'raw', 'BGRA', 0, 1)
        img = img.convert('RGB')
        img.save(r"D:\Modding\MarioPhysics\game_screen.jpg", "JPEG", quality=85)
        print("[SUCESSO] Screenshot apos movimento salva em game_screen.jpg!")
        
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)
