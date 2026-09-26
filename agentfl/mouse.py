"""Click and drag inside FL without touching the real cursor.

Posted clicks work on FL's ordinary controls but not on its canvases (the
playlist, the piano roll), which ask the system where the cursor is and
whether the button is held. `fldrop.dll` answers those questions from the
agent's pointer while it sends the mouse messages, on FL's UI thread.

The agent pointer (see `ghost`) is shown at every point, so the human can
watch what the agent does while keeping their own mouse.
"""

from __future__ import annotations

import ctypes
import tempfile
import time
from ctypes import wintypes as W
from pathlib import Path

from agentfl import drop, ghost, window

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.SetWindowsHookExW.restype = W.HHOOK
_u.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, W.HINSTANCE, W.DWORD]
_u.UnhookWindowsHookEx.argtypes = [W.HHOOK]
_u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
_u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]


def run(ops: list[tuple], label: str = "agent", show: bool = True, timeout: float = 10.0) -> str:
    """Run mouse ops, each ("move"|"ldown"|"lup"|"rdown"|"rup", sx, sy) or ("wait", ms)."""
    main = window.main_window()
    if main is None:
        raise RuntimeError("FL is not running")
    if show:
        first = next((o for o in ops if o[0] != "wait"), None)
        if first:
            ghost.point_to(first[1], first[2], label)

    tmp = Path(tempfile.gettempdir())
    result = tmp / "agentfl_mouse.result"
    result.unlink(missing_ok=True)
    lines = [str(main.hwnd)] + [" ".join(str(int(v)) if not isinstance(v, str) else v for v in o) for o in ops]
    (tmp / "agentfl_mouse.request").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lib = ctypes.WinDLL(str(drop.DLL))
    proc = ctypes.cast(lib.GetMsgProc, ctypes.c_void_p)
    tid = _u.GetWindowThreadProcessId(main.hwnd, None)
    hook = _u.SetWindowsHookExW(3, proc, lib._handle, tid)
    if not hook:
        raise OSError(ctypes.get_last_error(), "SetWindowsHookEx failed")
    try:
        _u.PostMessageW(main.hwnd, _u.RegisterWindowMessageW("AgentFL.Mouse"), 0, 0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if result.exists():
                text = result.read_text()
                if "done" in text or "error" in text:
                    return text.strip()
            time.sleep(0.05)
        return "timeout"
    finally:
        _u.UnhookWindowsHookEx(hook)


def click(sx: int, sy: int, label: str = "click", right: bool = False) -> str:
    d, u = ("rdown", "rup") if right else ("ldown", "lup")
    return run([("move", sx, sy), (d, sx, sy), ("wait", 30), (u, sx, sy)], label)


def drag(x1: int, y1: int, x2: int, y2: int, label: str = "drag", steps: int = 8) -> str:
    ops = [("move", x1, y1), ("ldown", x1, y1)]
    for i in range(1, steps + 1):
        ops += [("wait", 15), ("move", x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)]
    ops += [("lup", x2, y2)]
    return run(ops, label)
