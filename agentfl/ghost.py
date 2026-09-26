"""A second, visible pointer that shows where the agent is acting.

The agent never moves the real cursor, which leaves the human unable to see
what it is doing. This draws its own pointer instead: an always on top,
click-through overlay that glides to each point the agent acts on and fades
when idle. Clicks pass straight through it, so it cannot get in the way.

It runs as its own small process, started on first use, and listens on a
localhost UDP port for "x y label" lines in screen coordinates.

    from agentfl import ghost
    ghost.point_to(sx, sy, "drop kick")
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

PORT = 47831


def ghost_enabled() -> bool:
    """Off unless asked for. The pointer is for watching; nothing needs it."""
    return os.environ.get("AGENTFL_GHOST") == "1"

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _alive() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", PORT))
    except OSError:
        return True
    finally:
        probe.close()
    return False


def ensure_running() -> None:
    if _alive():
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, "-m", "agentfl.ghost"], creationflags=flags,
                     cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    for _ in range(40):
        if _alive():
            return
        time.sleep(0.05)


def point_to(sx: int, sy: int, label: str = "agent", settle: float = 0.35) -> None:
    """Glide the agent pointer to a screen point, then wait for it to land."""
    ensure_running()
    _sock.sendto(f"{int(sx)} {int(sy)} {label}".encode("utf-8"), ("127.0.0.1", PORT))
    time.sleep(settle)


def _run() -> None:
    import ctypes
    import tkinter as tk

    KEY = "#ff00ff"
    W, H = 220, 44
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", KEY)
    root.configure(bg=KEY)
    c = tk.Canvas(root, width=W, height=H, bg=KEY, highlightthickness=0)
    c.pack()
    # Arrow tip sits at the window's top left corner, like a real pointer.
    c.create_polygon(2, 2, 2, 26, 8, 20, 13, 31, 17, 29, 12, 18, 20, 18,
                     fill="#ff8a00", outline="#1a1a1a", width=2)
    label = c.create_text(26, 30, text="agent", anchor="w", fill="#ffffff",
                          font=("Segoe UI Semibold", 10))
    bg = c.create_rectangle(0, 0, 0, 0, fill="#1a1a1a", outline="")
    c.tag_lower(bg, label)

    root.update_idletasks()
    hwnd = ctypes.WinDLL("user32").GetParent(root.winfo_id())
    u = ctypes.WinDLL("user32")
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
    u.SetWindowLongW(hwnd, GWL_EXSTYLE, u.GetWindowLongW(hwnd, GWL_EXSTYLE)
                     | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", PORT))
    sock.setblocking(False)

    state = {"x": None, "y": None, "tx": 0, "ty": 0, "t0": 0.0, "fx": 0, "fy": 0, "last": 0.0}
    root.withdraw()

    def set_label(text: str) -> None:
        c.itemconfigure(label, text=text)
        x1, y1, x2, y2 = c.bbox(label)
        c.coords(bg, x1 - 5, y1 - 2, x2 + 5, y2 + 2)

    def tick() -> None:
        try:
            while True:
                msg = sock.recv(512).decode("utf-8", "replace").split(" ", 2)
                tx, ty = int(msg[0]), int(msg[1])
                set_label(msg[2] if len(msg) > 2 else "agent")
                if state["x"] is None:
                    state["x"], state["y"] = tx, ty
                state.update(fx=state["x"], fy=state["y"], tx=tx, ty=ty, t0=time.time(), last=time.time())
                root.deiconify()
                root.attributes("-alpha", 1.0)
        except BlockingIOError:
            pass
        now = time.time()
        if state["x"] is not None:
            p = min(1.0, (now - state["t0"]) / 0.3)
            e = 1 - (1 - p) ** 3
            state["x"] = round(state["fx"] + (state["tx"] - state["fx"]) * e)
            state["y"] = round(state["fy"] + (state["ty"] - state["fy"]) * e)
            root.geometry(f"{W}x{H}+{state['x']}+{state['y']}")
            idle = now - state["last"]
            if idle > 4.0:
                a = max(0.0, 1 - (idle - 4.0) / 0.6)
                root.attributes("-alpha", a)
                if a == 0.0:
                    root.withdraw()
        root.after(16, tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    _run()
