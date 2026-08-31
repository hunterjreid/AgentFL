"""Finding FL Studio's windows.

FL is a Delphi/VCL application, so its top level windows carry stable,
readable class names (TFruityLoopsMainForm, TPythonForm, TFLHintBarForm and so
on). That is what makes addressing it from outside practical at all: we can
locate the main form reliably without guessing at window titles, which change
with the open project.

Note that FL keeps many of these forms alive but hidden. A form existing tells
you nothing about whether it is on screen; check `visible`.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)

MAIN_FORM_CLASS = "TFruityLoopsMainForm"
HINT_BAR_CLASS = "TFLHintBarForm"
SCRIPT_OUTPUT_CLASS = "TPythonForm"

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@dataclass
class Win:
    hwnd: int
    cls: str
    title: str
    visible: bool
    minimized: bool
    rect: tuple[int, int, int, int]  # left, top, right, bottom in screen pixels

    @property
    def size(self) -> tuple[int, int]:
        return self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]


def _text(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _cls(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def windows_for_pid(pid: int) -> list[Win]:
    """Every top level window owned by a process."""
    found: list[Win] = []

    def cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            found.append(Win(
                hwnd=hwnd,
                cls=_cls(hwnd),
                title=_text(hwnd),
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                rect=_rect(hwnd),
            ))
        return True

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return found


def fl_pid() -> int | None:
    """PID of the running FL Studio, found by main form class.

    Deliberately not done by process name: FL ships as FL64.exe, FL.exe and
    other variants across versions, and the window class is the stable fact.
    """
    hwnd = user32.FindWindowW(MAIN_FORM_CLASS, None)
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value or None


def main_window() -> Win | None:
    """FL's main form, or None when FL is not running."""
    hwnd = user32.FindWindowW(MAIN_FORM_CLASS, None)
    if not hwnd:
        return None
    return Win(
        hwnd=hwnd,
        cls=MAIN_FORM_CLASS,
        title=_text(hwnd),
        visible=bool(user32.IsWindowVisible(hwnd)),
        minimized=bool(user32.IsIconic(hwnd)),
        rect=_rect(hwnd),
    )


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert screen pixels to a window's client coordinates.

    Required before posting mouse messages, whose lParam is client relative.
    Getting this wrong is silent: the click lands somewhere else in FL.
    """
    pt = wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    pt = wintypes.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y
