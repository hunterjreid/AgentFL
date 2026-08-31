"""Close FL Studio, or relaunch it, without touching the mouse.

Posting WM_CLOSE is the polite route: FL runs its normal shutdown, which is
what writes its registry config, so the binding edit that follows is not
fighting a half-saved state.

If FL has unsaved work it puts up a modal dialog and the close simply never
completes. That is detected and reported rather than forced, because forcing
it is how you lose someone's project.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ctypes  # noqa: E402

from agentfl import window  # noqa: E402

WM_CLOSE = 0x0010

FL_EXES = [
    r"C:\Program Files\Image-Line\FL Studio 2024\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
]


def close(timeout: float = 25.0) -> bool:
    win = window.main_window()
    if win is None:
        print("FL is not running")
        return True

    print(f"posting WM_CLOSE to hwnd {win.hwnd} ({win.title!r})")
    ctypes.WinDLL("user32").PostMessageW(win.hwnd, WM_CLOSE, 0, 0)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if window.main_window() is None:
            print("FL closed")
            return True
        time.sleep(0.4)

    print("FL is still up after "
          f"{timeout:.0f}s. Almost certainly a 'save changes?' dialog.")
    print("Answer it, then run this again. Not forcing the close.")
    return False


def dismiss_welcome() -> bool:
    """Close the 'Welcome to FL Studio' wizard if it is up.

    It sits in front of everything until a project is chosen, and FL does not
    finish bringing the session up behind it. Left open, a controller script
    never initialises and the bridge looks broken for a reason that has
    nothing to do with the script.
    """
    pid = window.fl_pid()
    if pid is None:
        return False
    closed = False
    for w in window.windows_for_pid(pid):
        if w.visible and w.cls == "TWelcomeWizard":
            print(f"closing welcome wizard (hwnd {w.hwnd})")
            ctypes.WinDLL("user32").PostMessageW(w.hwnd, WM_CLOSE, 0, 0)
            closed = True
    return closed


def launch() -> bool:
    exe = next((p for p in FL_EXES if Path(p).exists()), None)
    if exe is None:
        print(f"no FL executable found in: {FL_EXES}")
        return False
    print(f"launching {exe}")
    subprocess.Popen([exe], close_fds=True)

    # FL shows a splash before the main form exists, so absence early on means
    # nothing. Wait for the form itself.
    for _ in range(120):
        time.sleep(0.5)
        win = window.main_window()
        if win is not None:
            print(f"FL up: hwnd {win.hwnd} {win.title!r}")
            break
    else:
        print("FL did not present a main form within 60s")
        return False

    # The wizard appears after the main form, so look for it for a while.
    for _ in range(20):
        time.sleep(0.5)
        if dismiss_welcome():
            time.sleep(1.5)
            break
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["close", "launch", "status"])
    args = ap.parse_args()

    if args.action == "status":
        win = window.main_window()
        print("not running" if win is None
              else f"hwnd={win.hwnd} title={win.title!r} minimized={win.minimized}")
        raise SystemExit(0)

    ok = close() if args.action == "close" else launch()
    raise SystemExit(0 if ok else 1)
