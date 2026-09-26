"""The same six actions from a shell, for agents that run commands instead of MCP.

    agentfl ping
    agentfl inject "mixer.setTrackVolume(1, 0.7)"
    agentfl inject -f build_drums.py
    agentfl read
    agentfl see fl.png
    agentfl drop kick.wav --at 400 900
    agentfl click 612 488
    agentfl drag 300 200 700 200
    agentfl mcp

Output is JSON on stdout, so another program can read it back.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import actions


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agentfl", description="Drive a live FL Studio.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    i = sub.add_parser("inject")
    i.add_argument("code", nargs="?", help="Python to run; omit to read stdin")
    i.add_argument("-f", "--file")
    i.add_argument("--timeout", type=float, default=10.0)
    sub.add_parser("read")
    s = sub.add_parser("see")
    s.add_argument("out", nargs="?", default="fl.png")
    s.add_argument("--max-width", type=int)
    d = sub.add_parser("drop")
    d.add_argument("files", nargs="+")
    d.add_argument("--at", nargs=2, type=int, metavar=("X", "Y"))
    d.add_argument("--target", default="channels",
                   choices=["channels", "playlist", "mixer", "browser", "main"])
    c = sub.add_parser("click")
    c.add_argument("x", type=int)
    c.add_argument("y", type=int)
    c.add_argument("--right", action="store_true")
    g = sub.add_parser("drag")
    for n in ("x1", "y1", "x2", "y2"):
        g.add_argument(n, type=int)
    sub.add_parser("mcp")

    a = p.parse_args(argv)
    actions.dpi_aware()

    if a.cmd == "mcp":
        from . import mcp_server
        mcp_server.main()
        return 0
    if a.cmd == "ping":
        _print(actions.inject("general.getVersion()"))
    elif a.cmd == "inject":
        code = Path(a.file).read_text(encoding="utf-8") if a.file else (a.code or sys.stdin.read())
        res = actions.inject(code, a.timeout)
        _print(res)
        return 0 if res["ok"] else 1
    elif a.cmd == "read":
        _print(actions.read())
    elif a.cmd == "see":
        Path(a.out).write_bytes(actions.see(a.max_width))
        _print({"ok": True, "path": str(Path(a.out).resolve())})
    elif a.cmd == "drop":
        x, y = a.at if a.at else (None, None)
        _print({"result": actions.drop(a.files, x, y, a.target)})
    elif a.cmd == "click":
        _print({"result": actions.click(a.x, a.y, a.right)})
    elif a.cmd == "drag":
        _print({"result": actions.drag(a.x1, a.y1, a.x2, a.y2)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
