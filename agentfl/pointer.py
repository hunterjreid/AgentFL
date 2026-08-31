"""UI interaction with FL that never touches the user's mouse.

HARD RULE: nothing in this module may call SetCursorPos, mouse_event or
SendInput. Those drive the one physical cursor the user is also holding, which
makes the machine unusable while an agent works and steals focus from whatever
the user is doing. Every interaction here is a message posted to an FL window,
which the user's pointer knows nothing about.

The honest caveat, and you should test rather than trust it: posted mouse
messages reach an application's handlers, but an application is free to ignore
them and ask Windows where the cursor really is. Delphi/VCL apps frequently do
exactly that during a drag, via mouse capture plus GetCursorPos. So a posted
CLICK is very likely to work, and a posted DRAG may well not. `probe_drag`
exists to answer that question on a given FL build instead of assuming.

When a drag turns out not to be honoured, the fallback is not to reach for the
real cursor. It is to do the job through injected Python, or to accept that
the operation is one the user performs.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from . import window

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002


def _lparam(x: int, y: int) -> int:
    """Pack client coordinates the way Windows mouse messages expect."""
    return (y & 0xFFFF) << 16 | (x & 0xFFFF)


def _post(hwnd: int, msg: int, wparam: int, x: int, y: int) -> bool:
    return bool(user32.PostMessageW(hwnd, msg, wparam, _lparam(x, y)))


def click(hwnd: int, x: int, y: int, *, right: bool = False,
          settle: float = 0.06) -> None:
    """Click at client coordinates (x, y) of a window. Cursor is untouched."""
    down = WM_RBUTTONDOWN if right else WM_LBUTTONDOWN
    up = WM_RBUTTONUP if right else WM_LBUTTONUP
    held = MK_RBUTTON if right else MK_LBUTTON

    # The move first matters: many controls only compute their hit target on
    # WM_MOUSEMOVE, and a bare buttondown then lands on a stale position.
    _post(hwnd, WM_MOUSEMOVE, 0, x, y)
    time.sleep(settle)
    _post(hwnd, down, held, x, y)
    time.sleep(settle)
    _post(hwnd, up, 0, x, y)


def click_screen(hwnd: int, sx: int, sy: int, **kw) -> None:
    """Click at absolute screen coordinates, converted for the target window."""
    cx, cy = window.screen_to_client(hwnd, sx, sy)
    click(hwnd, cx, cy, **kw)


def drag(hwnd: int, x1: int, y1: int, x2: int, y2: int, *,
         steps: int = 16, settle: float = 0.03) -> None:
    """Drag between two client coordinates using posted messages only.

    Whether this actually moves anything depends on the target honouring
    posted motion instead of polling the real cursor. Verify with probe_drag
    before relying on it.
    """
    _post(hwnd, WM_MOUSEMOVE, 0, x1, y1)
    time.sleep(settle)
    _post(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, x1, y1)
    time.sleep(settle * 2)
    for i in range(1, steps + 1):
        x = round(x1 + (x2 - x1) * i / steps)
        y = round(y1 + (y2 - y1) * i / steps)
        _post(hwnd, WM_MOUSEMOVE, MK_LBUTTON, x, y)
        time.sleep(settle)
    time.sleep(settle * 2)
    _post(hwnd, WM_LBUTTONUP, 0, x2, y2)


def cursor_pos() -> tuple[int, int]:
    """Where the real cursor is. Read only, used to prove we did not move it."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def probe_drag(hwnd: int, x1: int, y1: int, x2: int, y2: int) -> dict:
    """Attempt a posted drag and report whether the cursor stayed put.

    This answers the only question that matters before trusting this module:
    did we move FL without moving the user's mouse? It cannot tell you whether
    FL acted on the drag; compare screenshots for that.
    """
    before = cursor_pos()
    drag(hwnd, x1, y1, x2, y2)
    after = cursor_pos()
    return {
        "cursor_before": before,
        "cursor_after": after,
        "cursor_moved": before != after,
        "posted": True,
    }
