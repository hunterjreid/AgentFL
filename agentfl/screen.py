"""Seeing FL Studio.

The agent equivalent of looking at the screen. Kept separate from pointer.py
because reading is always safe and always allowed, while acting is not.

Multi monitor note: a window on a monitor left of the primary has negative
screen coordinates, which is normal and not a bug. Pillow needs all_screens
for those to be captured at all, and without it you silently get a black or
clipped image rather than an error.
"""

from __future__ import annotations

from pathlib import Path

from PIL import ImageGrab

from . import window


def grab_region(left: int, top: int, right: int, bottom: int, path: str | Path,
                scale: int = 1) -> Path:
    img = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale),
                         resample=0)  # nearest, so pixel edges stay readable
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def capture_window(hwnd: int):
    """Render a window into an image without reading the screen.

    PrintWindow with PW_RENDERFULLCONTENT asks DWM for the window's own
    surface, so FL can sit behind other windows, or on a monitor the user is
    not looking at, and the capture is still of FL rather than of whatever
    covers it. A screen grab would show the cover.
    """
    import ctypes
    from ctypes import wintypes as W

    from PIL import Image

    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    # FL skips painting whatever is off the visible desktop, so a window parked
    # off screen comes back with black holes. Repaint all of it first.
    u.RedrawWindow(hwnd, None, None, 0x1 | 0x80 | 0x100 | 0x400)  # INVALIDATE ALLCHILDREN UPDATENOW FRAME
    r = W.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    wdc = u.GetWindowDC(hwnd)
    mdc = g.CreateCompatibleDC(wdc)
    bmp = g.CreateCompatibleBitmap(wdc, w, h)
    old = g.SelectObject(mdc, bmp)
    try:
        u.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT
        info = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mdc, bmp, 0, h, buf, info, 0)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        g.SelectObject(mdc, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(hwnd, wdc)


def grab_fl(path: str | Path, *, region: tuple[int, int, int, int] | None = None,
            scale: int = 1) -> Path:
    """Capture FL's main window, or a sub-region of it.

    `region` is given in window-relative pixels (x, y, w, h), which keeps
    callers from having to know where FL sits on the desktop.
    """
    win = window.main_window()
    if win is None:
        raise RuntimeError("FL Studio is not running (no main form found)")
    if win.minimized:
        raise RuntimeError(
            "FL Studio is minimized, so there is nothing on screen to capture. "
            "Restore it first, or work through injection instead of vision."
        )
    left, top, right, bottom = win.rect
    if region is not None:
        x, y, w, h = region
        left, top = left + x, top + y
        right, bottom = left + w, top + h
    return grab_region(left, top, right, bottom, path, scale=scale)
