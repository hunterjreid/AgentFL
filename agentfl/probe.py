"""Measure FL's real API surface instead of reasoning about it.

Everything this prints is a measurement taken inside the running FL, which is
the only trustworthy source. Version to version, Image-Line adds and removes
functions without announcement, so a capability list written from memory goes
stale silently and sends an agent chasing calls that no longer exist.

    python -m agentfl.probe
    python -m agentfl.probe --sandbox     also test what the sandbox allows
"""

from __future__ import annotations

import argparse
import json

from . import bridge

MODULES = [
    "channels", "mixer", "patterns", "playlist", "plugins",
    "transport", "ui", "general", "arrangement", "device", "utils",
]

_LIST_MODULE = """
mod = {name}
if mod is None:
    RESULT = None
else:
    RESULT = sorted(n for n in dir(mod) if not n.startswith('_'))
"""

# Each probe is written so a restricted builtin raises rather than silently
# returning something falsy, which would read as a working capability.
_SANDBOX = """
results = {}

def attempt(label, fn):
    try:
        results[label] = ['ok', repr(fn())[:120]]
    except Exception as exc:
        results[label] = ['blocked', type(exc).__name__ + ': ' + str(exc)[:120]]

attempt('open_read',   lambda: open(__file__ if '__file__' in dir() else 'nonexistent.txt'))
attempt('import_os',   lambda: __import__('os').getcwd())
attempt('import_sys',  lambda: __import__('sys').version)
attempt('import_socket', lambda: __import__('socket').socket)
attempt('import_ast',  lambda: __import__('ast').parse('1'))
attempt('builtins_open_exists', lambda: 'open' in dir(__builtins__))

RESULT = results
"""


def probe_modules(fl: bridge.Bridge) -> dict:
    surface = {}
    for name in MODULES:
        res = fl.inject(_LIST_MODULE.format(name=name))
        if not res.ok:
            surface[name] = {"error": res.error}
        elif res.value is None:
            surface[name] = {"available": False}
        else:
            surface[name] = {"available": True, "functions": res.value}
    return surface


def probe_sandbox(fl: bridge.Bridge) -> dict:
    res = fl.inject(_SANDBOX)
    return res.value if res.ok else {"error": res.error}


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure FL's live API surface.")
    ap.add_argument("--sandbox", action="store_true",
                    help="also test filesystem and import restrictions")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    args = ap.parse_args()

    with bridge.Bridge() as fl:
        info = fl.ping()
        if not info.get("ok"):
            print("kernel did not answer ping. Run: python -m agentfl.doctor")
            return 1

        out = {
            "fl_version": (info.get("data") or {}).get("fl_version"),
            "modules": probe_modules(fl),
        }
        if args.sandbox:
            out["sandbox"] = probe_sandbox(fl)

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"FL {out['fl_version']}\n")
    for name, info in out["modules"].items():
        if info.get("error"):
            print(f"  {name:<12} error: {info['error']}")
        elif not info.get("available"):
            print(f"  {name:<12} not available on this build")
        else:
            fns = info["functions"]
            print(f"  {name:<12} {len(fns)} functions")
    if args.sandbox:
        print("\nsandbox:")
        for label, (status, detail) in sorted(out["sandbox"].items()):
            print(f"  {label:<22} {status:<8} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
