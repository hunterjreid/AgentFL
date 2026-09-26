"""AgentFL as an MCP server, so any MCP client can make music in FL Studio.

Six tools and no more. A catalogue of FL commands is the design that made
the old bridge useless: it only ever holds what someone thought of, and
growing it costs an FL restart. Everything musical goes through fl_inject.

    claude mcp add agentfl -- agentfl-mcp
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP, Image

from . import actions

mcp = FastMCP(
    "agentfl",
    instructions=(
        "Drive a live FL Studio. fl_inject runs Python inside FL (modules "
        "channels, mixer, patterns, playlist, plugins, transport, ui, general, "
        "midi); definitions persist for the session. fl_see returns a capture "
        "of FL's window, and fl_click, fl_drag and fl_drop take points in that "
        "capture's pixels. None of them move the user's mouse or need FL in "
        "front. Adding channels, loading plugins and placing clips have no "
        "Python API, so use fl_drop and fl_click for those. Read results back "
        "after acting; ok only means nothing raised. Never start playback "
        "unless the user asks."
    ),
)


def _json(obj) -> str:
    return json.dumps(obj, indent=1, default=str)


@mcp.tool()
def fl_inject(code: str, timeout: float = 10.0) -> str:
    """Run Python inside FL Studio's live interpreter.

    A single expression returns its value. Longer code returns whatever it
    assigns to RESULT. Runs on FL's UI thread, so keep it short: no loops that
    wait, no sleeps. Validate indices before writing, since an out of range
    plugin or mixer index can crash FL.
    """
    return _json(actions.inject(code, timeout))


@mcp.tool()
def fl_read() -> str:
    """Snapshot of the open project: tempo, transport, channels, patterns,
    named mixer inserts and whether there is unsaved work."""
    return _json(actions.read())


@mcp.tool()
def fl_see(max_width: int = 1600) -> Image:
    """Capture FL's main window as it looks now, even if covered by other
    windows. Pixel coordinates in this image are what fl_click, fl_drag and
    fl_drop take, scaled back up if max_width shrank it."""
    return Image(data=actions.see(max_width), format="png")


@mcp.tool()
def fl_drop(files: list[str], x: int | None = None, y: int | None = None,
            target: str = "channels") -> str:
    """Drop files on FL as if dragged from Explorer. target is channels,
    playlist, mixer or browser. A .wav on the rack's empty bottom strip adds a
    sampler; a .fst channel preset loads a synth; a .wav on the playlist adds
    an audio clip. x, y are full size fl_see pixels; omit them for the centre."""
    return actions.drop(files, x, y, target)


@mcp.tool()
def fl_click(x: int, y: int, right: bool = False) -> str:
    """Click FL at a point in full size fl_see pixels, without the real mouse."""
    return actions.click(x, y, right)


@mcp.tool()
def fl_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Drag inside FL between two full size fl_see points, without the real mouse."""
    return actions.drag(x1, y1, x2, y2)


def main() -> None:
    actions.dpi_aware()
    mcp.run()


if __name__ == "__main__":
    main()
