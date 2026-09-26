"""The six things an agent does to FL, shared by the CLI and the MCP server.

inject, read, see, drop, click, drag. Nothing here knows about music: every
musical capability is Python sent through `inject`, which is why this list
stays this short and never needs FL restarting to grow.

Coordinates everywhere are pixels in the image `see` returns, measured from
the top left of FL's main window. An agent looks at the capture, picks a
point, and acts on that same point, without ever converting to the screen.

None of this moves the physical cursor or needs FL in front. Captures come
from FL's own surface, and clicks and drops go through the native pointer.
"""

from __future__ import annotations

import ctypes
import io
import threading

from . import bridge, window

_lock = threading.Lock()
_fl: bridge.Bridge | None = None


def dpi_aware() -> None:
    """Make window rects and pointer points share one pixel space.

    Without this Windows hands a scaled rect to a process that is not DPI
    aware, and every click lands a fraction of the window away from where
    the capture said it should.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def _bridge() -> bridge.Bridge:
    global _fl
    if _fl is None:
        window.dismiss_welcome()
        _fl = bridge.Bridge().connect()
    return _fl


def inject(code: str, timeout: float = 10.0) -> dict:
    """Run Python in FL's interpreter. An expression returns its value;
    longer code returns whatever it assigns to RESULT."""
    global _fl
    with _lock:
        try:
            res = _bridge().inject(code, timeout=timeout)
        except bridge.BridgeError:
            # MIDI ports are exclusive and go stale if FL restarts, so one
            # reconnect separates a dropped port from a dead kernel.
            if _fl is not None:
                _fl.close()
            _fl = None
            res = _bridge().inject(code, timeout=timeout)
    out = {"ok": res.ok}
    if res.ok:
        out["value"] = res.value
        if res.stdout:
            out["stdout"] = res.stdout
        if res.warning:
            out["warning"] = res.warning
    else:
        out["error"] = res.error
        if res.traceback:
            out["traceback"] = res.traceback
    return out


_READ = """
import channels, mixer, patterns, transport, general, ui
def _col(c):
    return '#%06x' % (c & 0xFFFFFF)
RESULT = {
    'fl': general.getVersion(),
    'tempo': mixer.getCurrentTempo() / 1000,
    'playing': bool(transport.isPlaying()),
    'song_mode': transport.getLoopMode() == 1,
    'unsaved': bool(general.getChangedFlag()),
    'hint': ui.getHintMsg(),
    'channels': [
        {'index': i, 'name': channels.getChannelName(i),
         'color': _col(channels.getChannelColor(i)),
         'type': channels.getChannelType(i),
         'insert': channels.getTargetFxTrack(i)}
        for i in range(channels.channelCount(True))],
    'patterns': [
        {'index': i, 'name': patterns.getPatternName(i),
         'color': _col(patterns.getPatternColor(i)),
         'length': patterns.getPatternLength(i)}
        for i in range(1, patterns.patternCount() + 1)],
    'inserts': [
        {'index': i, 'name': mixer.getTrackName(i),
         'volume': round(mixer.getTrackVolume(i), 3)}
        for i in range(mixer.trackCount())
        if mixer.getTrackName(i) not in ('Insert %d' % i, 'Master', 'Current')
        or i == 0],
}
"""


def read() -> dict:
    """A structured snapshot of the open project."""
    return inject(_READ)


def _main() -> window.Win:
    win = window.main_window()
    if win is None:
        raise RuntimeError("FL Studio is not running")
    if win.minimized:
        raise RuntimeError("FL is minimised; restore it so it has a surface to capture and act on")
    return win


def see(max_width: int | None = None) -> bytes:
    """PNG of FL's main window, rendered from FL itself, not the screen."""
    from . import screen

    img = screen.capture_window(_main().hwnd)
    if max_width and img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _to_screen(x: int, y: int) -> tuple[int, int]:
    left, top, right, bottom = _main().rect
    if not (0 <= x < right - left and 0 <= y < bottom - top):
        raise ValueError(f"({x}, {y}) is outside FL's window ({right - left}x{bottom - top})")
    return left + x, top + y


def drop(files: list[str], x: int | None = None, y: int | None = None,
         target: str = "channels") -> str:
    """Drop files on FL, the way dragging them in from Explorer does.

    A .wav on the channel rack adds a sampler, a channel preset .fst loads a
    synth, a plugin .fst on a mixer slot loads an effect, a .wav on the
    playlist becomes an audio clip. With no point, the target window's centre.
    """
    from . import drop as _drop

    at = None
    if x is not None and y is not None:
        sx, sy = _to_screen(x, y)
        hwnd = _drop.find_target(target)
        at = window.screen_to_client(hwnd, sx, sy)
    return _drop.drop(files, target=target, at=at)


def click(x: int, y: int, right: bool = False) -> str:
    from . import mouse

    return mouse.click(*_to_screen(x, y), right=right)


def drag(x1: int, y1: int, x2: int, y2: int) -> str:
    from . import mouse

    return mouse.drag(*_to_screen(x1, y1), *_to_screen(x2, y2))
