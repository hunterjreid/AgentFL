"""Drop files onto FL windows the way Explorer does, without the mouse.

FL's windows register OLE drop targets, not WM_DROPFILES, so a posted message
cannot reach them. `fldrop.dll` is hooked onto FL's UI thread, the thread the
drop handlers expect, and plays DragEnter/DragOver/Drop against the window's
own IDropTarget. That is how a person adds a sample channel (.wav), loads a
plugin (.fst preset) or brings in notes (.mid), which are exactly the things
the Python API cannot do.
"""

from __future__ import annotations

import ctypes
import os
import tempfile
import time
from ctypes import wintypes as W
from pathlib import Path

from agentfl import window
from agentfl.ghost import ghost_enabled

# A hooked DLL stays loaded in FL, so each rebuild gets a new name and the
# newest one is used.
_DROP_DIR = Path(__file__).resolve().parents[1] / "reverse-engineering" / "drop"
DLL = max(_DROP_DIR.glob("fldrop*.dll"), key=lambda p: p.stat().st_mtime, default=_DROP_DIR / "fldrop.dll")
WH_GETMESSAGE = 3

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.SetWindowsHookExW.restype = W.HHOOK
_u.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, W.HINSTANCE, W.DWORD]
_u.UnhookWindowsHookEx.argtypes = [W.HHOOK]
_u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
_u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
_u.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
_u.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]

TARGETS = {
    "channels": "TStepSeqForm",
    "playlist": "TEventEditForm",
    "mixer": "TFXForm",
    "browser": "TSampleListForm",
    "main": "TFruityLoopsMainForm",
}


def find_target(name: str) -> int:
    cls = TARGETS[name]
    main = window.main_window()
    if main is None:
        raise RuntimeError("FL is not running")
    if cls == "TFruityLoopsMainForm":
        return main.hwnd
    found: list[int] = []
    buf = ctypes.create_unicode_buffer(256)

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def visit(h, _):
        _u.GetClassNameW(h, buf, 256)
        if buf.value == cls:
            found.append(h)
            return False
        return True

    _u.EnumChildWindows(main.hwnd, visit, 0)
    if not found:
        raise RuntimeError(f"no {cls} window, is the {name} open?")
    return found[0]


def drop(files: list[str], target: str = "channels", at: tuple[int, int] | None = None,
         timeout: float = 5.0, show: bool | None = None, label: str = "") -> str:
    """Drop `files` on a FL window. `at` is a client point, default the centre.

    Returns the helper's report line. "ok ... drop=0x00000000" means FL
    accepted the drop, not that it did what was wanted: read the result back.
    """
    paths = [str(Path(f).resolve()) for f in files]
    for p in paths:
        if not os.path.exists(p):
            raise FileNotFoundError(p)
    if len({str(Path(p).parent) for p in paths}) > 1:
        raise ValueError("one drop carries files from one folder only")

    hwnd = find_target(target)
    r = W.RECT()
    _u.GetWindowRect(hwnd, ctypes.byref(r))
    if at is None:
        sx, sy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
    else:
        sx, sy = window.client_to_screen(hwnd, *at)

    if show is None:
        show = ghost_enabled()
    if show:
        from agentfl import ghost
        ghost.point_to(sx, sy, label or f"drop {Path(paths[0]).stem}")

    tmp = Path(tempfile.gettempdir())
    result = tmp / "agentfl_drop.result"
    result.unlink(missing_ok=True)
    (tmp / "agentfl_drop.request").write_text(
        f"{hwnd}\n{sx} {sy}\n" + "\n".join(paths) + "\n", encoding="utf-8")

    lib = ctypes.WinDLL(str(DLL))
    proc = ctypes.cast(lib.GetMsgProc, ctypes.c_void_p)
    tid = _u.GetWindowThreadProcessId(hwnd, None)
    hook = _u.SetWindowsHookExW(WH_GETMESSAGE, proc, lib._handle, tid)
    if not hook:
        raise OSError(ctypes.get_last_error(), "SetWindowsHookEx failed")
    try:
        _u.PostMessageW(hwnd, _u.RegisterWindowMessageW("AgentFL.Drop"), 0, 0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if result.exists() and result.stat().st_size:
                return result.read_text().strip()
            time.sleep(0.05)
        return "timeout: FL never processed the drop message (modal dialog up?)"
    finally:
        _u.UnhookWindowsHookEx(hook)
