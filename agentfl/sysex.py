"""Wire protocol shared with kernel/device_AgentFL.py.

Every constant here has a twin in the kernel. If you change one, change both,
because a mismatch shows up as silence rather than an error: the kernel simply
decides the frame is not addressed to it and hands it back to FL.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field

PROTOCOL_VERSION = 1

SYSEX_MANUFACTURER = 0x7D
SYSEX_MAGIC = (0x41, 0x47, 0x46)  # "AGF"

DIR_REQUEST = 0x01
DIR_RESPONSE = 0x02
DIR_HEARTBEAT = 0x03

REQUEST_ID_LEN = 8
HEADER_LEN = 1 + 3 + 1 + REQUEST_ID_LEN + 1 + 1

CHUNK_PAYLOAD = 256
MAX_CHUNKS = 128


def encode(direction: int, request_id: str, payload: object) -> list[list[int]]:
    """Serialise a payload into one or more SysEx bodies.

    Returns raw byte lists WITHOUT F0/F7 framing, because mido adds those
    itself. The kernel is tolerant of either, but sending both would double
    them here.
    """
    rid = (request_id.encode("ascii") + b"00000000")[:REQUEST_ID_LEN]
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    b64 = base64.b64encode(body.encode("utf-8"))

    pieces = [b64[i:i + CHUNK_PAYLOAD] for i in range(0, len(b64), CHUNK_PAYLOAD)] or [b""]
    if len(pieces) > MAX_CHUNKS:
        raise ValueError(
            f"request needs {len(pieces)} chunks, protocol allows {MAX_CHUNKS}. "
            "Send less code, or define a helper once and call it."
        )

    frames = []
    total = len(pieces)
    for idx, piece in enumerate(pieces):
        frame = [SYSEX_MANUFACTURER, *SYSEX_MAGIC, direction & 0x7F]
        frame.extend(rid)
        frame.append(idx & 0x7F)
        frame.append(total & 0x7F)
        frame.extend(piece)
        frames.append(frame)
    return frames


@dataclass
class Frame:
    direction: int
    request_id: str
    index: int
    total: int
    payload: bytes


def decode_frame(data: bytes) -> Frame | None:
    """Parse one SysEx body. Returns None when the frame is not ours."""
    if len(data) < HEADER_LEN:
        return None
    if data[0] != SYSEX_MANUFACTURER:
        return None
    if tuple(data[1:4]) != SYSEX_MAGIC:
        return None
    return Frame(
        direction=data[4],
        request_id=bytes(data[5:5 + REQUEST_ID_LEN]).decode("ascii", "replace"),
        index=data[5 + REQUEST_ID_LEN],
        total=data[6 + REQUEST_ID_LEN],
        payload=bytes(data[HEADER_LEN:]),
    )


@dataclass
class Reassembler:
    """Collects chunks until a full message is available.

    Keyed by request id so interleaved responses cannot corrupt each other.
    """

    _slots: dict = field(default_factory=dict)

    def feed(self, frame: Frame):
        """Add a frame. Returns the decoded payload once complete, else None."""
        slot = self._slots.get(frame.request_id)
        if slot is None or slot["total"] != frame.total:
            slot = {"total": frame.total, "parts": {}}
            self._slots[frame.request_id] = slot
        slot["parts"][frame.index] = frame.payload
        if len(slot["parts"]) < frame.total:
            return None
        del self._slots[frame.request_id]
        joined = b"".join(slot["parts"][i] for i in range(frame.total))
        return json.loads(base64.b64decode(joined).decode("utf-8"))
