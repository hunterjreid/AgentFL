"""agentfl: drive FL Studio the way an agent drives a browser.

Four primitives, deliberately mirroring what browser automation gives you:

    inject   run Python inside FL's live interpreter   (the powerful one)
    read     structured snapshot of the project
    see      capture FL's window as an image
    point    click and drag FL's UI without moving the real cursor

`inject` is the centrepiece for the same reason JavaScript injection is the
centrepiece in a browser: anything the host can do, injected code can do, and
it needs no new plumbing per capability. The kernel installed inside FL knows
nothing about music. It only knows how to run what it is given, which is why
adding a feature never means restarting FL again.
"""

from .bridge import Bridge, BridgeError, InjectResult, NotConnected
from .doctor import diagnose

__all__ = [
    "Bridge",
    "BridgeError",
    "InjectResult",
    "NotConnected",
    "diagnose",
    "connect",
]

__version__ = "0.1.0"


def connect(rx: str | None = None, tx: str | None = None) -> Bridge:
    """Open a bridge to a running FL Studio."""
    from .bridge import DEFAULT_RX, DEFAULT_TX
    return Bridge(rx or DEFAULT_RX, tx or DEFAULT_TX).connect()
