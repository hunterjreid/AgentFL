"""Checks that need a real FL Studio running. Safe to run any time.

Nothing here writes to the project or moves the cursor. It answers three
questions that cannot be answered offline:

    1. can we find FL's window
    2. does the posted message path leave the user's mouse alone
    3. is the bridge routed in both directions

    python tests/live_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentfl import doctor, pointer, window  # noqa: E402


def check_window():
    print("== FL window ==")
    win = window.main_window()
    if win is None:
        print("  FL Studio is not running")
        return None
    print(f"  hwnd      {win.hwnd}")
    print(f"  class     {win.cls}")
    print(f"  title     {win.title!r}")
    print(f"  rect      {win.rect}  size {win.size[0]}x{win.size[1]}")
    print(f"  minimized {win.minimized}")
    if win.rect[0] < 0 or win.rect[1] < 0:
        print("  note      negative origin is normal on a left-hand monitor")
    return win


def check_cursor_untouched(win):
    """The mouse rule, verified rather than asserted.

    Posts a harmless move to a corner of FL's own title area and confirms the
    physical cursor did not follow. No button is pressed, so FL cannot act on
    it even if it wanted to.
    """
    print("\n== mouse safety ==")
    if win is None:
        print("  skipped, FL not running")
        return
    before = pointer.cursor_pos()
    pointer._post(win.hwnd, pointer.WM_MOUSEMOVE, 0, 5, 5)
    after = pointer.cursor_pos()
    print(f"  cursor before {before}")
    print(f"  cursor after  {after}")
    if before == after:
        print("  PASS: posting a mouse message did not move the real cursor")
    else:
        print("  FAIL: the cursor moved. Something is using SetCursorPos.")


def check_bridge():
    print("\n== bridge ==")
    report = doctor.diagnose()
    print("\n".join("  " + line for line in str(report).splitlines()))
    if report.ok:
        print("\n  bridge healthy")
    else:
        print(f"\n  blocked at: {report.first_failure.name}")


if __name__ == "__main__":
    win = check_window()
    check_cursor_untouched(win)
    check_bridge()
