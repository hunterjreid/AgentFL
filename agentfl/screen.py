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
