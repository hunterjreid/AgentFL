"""Layered diagnosis of the bridge.

Written because the failure that actually happens in practice is the one that
is hardest to read: the kernel is loaded and healthy inside FL, printing
heartbeats into the void, while the agent side hears nothing. Both halves look
fine in isolation and the naive summary is a flat "not connected", which sends
you off rewriting a script that was never broken.

The layers, checked in order, because a failure at one makes every check below
it meaningless:

    1. FL Studio process running at all
    2. loopMIDI ports present
    3. ports openable (Windows MIDI inputs are exclusive)
    4. heartbeat arriving          -> kernel loaded AND output routed
    5. request/response round trip -> input routed too
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field

import mido

from . import bridge, window


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def first_failure(self) -> Check | None:
        return next((c for c in self.checks if not c.ok), None)

    def __str__(self) -> str:
        lines = []
        for c in self.checks:
            lines.append(f"[{'ok' if c.ok else 'FAIL'}] {c.name}"
                         + (f"  {c.detail}" if c.detail else ""))
            if not c.ok and c.fix:
                lines.append(f"       fix: {c.fix}")
        return "\n".join(lines)


def _competing_processes() -> list[str]:
    """Other processes that plausibly hold the MIDI ports."""
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []
    hits = []
    for line in out.splitlines():
        low = line.lower()
        if "fl-studio-mcp" in low or "agentfl" in low:
            hits.append(line.split(",")[0].strip('"'))
    return hits


def diagnose(rx: str = bridge.DEFAULT_RX,
             tx: str = bridge.DEFAULT_TX) -> Report:
    report = Report()

    # 1 -- FL running
    win = window.main_window()
    report.checks.append(Check(
        "FL Studio running",
        win is not None,
        detail=(f"hwnd={win.hwnd}"
                + (" (minimized)" if win and win.minimized else "")) if win else "",
        fix="Start FL Studio.",
    ))
    if win is None:
        return report

    # 1b -- the welcome splash, which blocks controller script loading entirely.
    # Cleared rather than reported, because there is no judgement call here and
    # leaving it up makes every check below meaningless.
    if window.welcome_wizard() is not None:
        cleared = window.dismiss_welcome()
        report.checks.append(Check(
            "welcome splash cleared",
            cleared,
            detail="was blocking script load" if cleared else "still up",
            fix="Close the 'Welcome to FL Studio' window by hand.",
        ))
        if not cleared:
            return report
        # FL loads controller scripts once the splash goes; heartbeats follow
        # within about a second.
        time.sleep(2.0)

    # 2 -- ports exist
    outs, ins = mido.get_output_names(), mido.get_input_names()
    out_ok = bridge._match_port(outs, rx) is not None
    in_ok = bridge._match_port(ins, tx) is not None
    report.checks.append(Check(
        "loopMIDI ports present",
        out_ok and in_ok,
        detail=f"out={rx!r}:{out_ok} in={tx!r}:{in_ok}",
        fix=f"Create {rx!r} and {tx!r} in loopMIDI.",
    ))
    if not (out_ok and in_ok):
        return report

    # 3 -- ports openable
    b = bridge.Bridge(rx, tx)
    try:
        b.connect()
    except bridge.BridgeError as exc:
        others = _competing_processes()
        report.checks.append(Check(
            "MIDI ports openable", False, detail=str(exc),
            fix=("Close the process already holding the port"
                 + (f" (found: {', '.join(sorted(set(others)))})" if others else "")),
        ))
        return report
    report.checks.append(Check("MIDI ports openable", True))

    try:
        # 4 -- heartbeat. The decisive check.
        alive = b.wait_alive(timeout=3.0)
        report.checks.append(Check(
            "kernel heartbeat received",
            alive,
            detail="" if alive else "silent for 3s",
            fix=(
                "The kernel is either not loaded, or loaded but its output is "
                "not routed. Tell them apart by looking at FL's hint bar (top "
                "left): if it reads 'AgentFL ready', the kernel IS running and "
                "the problem is purely routing. In that case open Options > "
                "MIDI Settings and, in the OUTPUT list, enable "
                f"{tx!r} and set its Port number to the SAME number "
                f"{rx!r} has in the Input list."
            ),
        ))
        if not alive:
            return report

        # 5 -- full round trip
        try:
            reply = b.ping(timeout=3.0)
            ok = bool(reply.get("ok"))
            data = reply.get("data") or {}
            report.checks.append(Check(
                "request round trip", ok,
                detail=f"FL {data.get('fl_version')}, protocol v{data.get('protocol')}",
                fix=("Heartbeats arrive but requests do not, so FL's INPUT is "
                     f"not routed. Enable {rx!r} in the Input list and set its "
                     "Controller type to AgentFL."),
            ))
        except TimeoutError as exc:
            report.checks.append(Check(
                "request round trip", False, detail=str(exc),
                fix=f"Enable {rx!r} in FL's MIDI Input list, Controller type AgentFL.",
            ))
    finally:
        b.close()

    return report


def main() -> int:
    report = diagnose()
    print(report)
    print()
    print("bridge healthy" if report.ok
          else f"blocked at: {report.first_failure.name}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
