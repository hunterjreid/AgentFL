# name=AgentFL
# url=https://github.com/hunterjreid/agent-fl
# receiveFrom=
# supportedDevices=
"""AgentFL kernel: a permanent, capability-free bridge into FL Studio.

Leave `supportedDevices` EMPTY. Naming a device there tells FL the script only
binds to a port with exactly that name, so FL silently filters the script out
for every other port and never imports it. The symptom is indistinguishable
from a script that crashed on import: no output, no error, and no
`__pycache__` next to the file. That missing `__pycache__` is the quickest way
to tell "FL never loaded this" from "FL loaded it and it failed".

This file is deliberately the ONLY thing that ever gets installed into FL.
It exposes exactly three commands: ping, inject, and cancel. It knows
nothing about mixers, channels, plugins or patterns, and it never should.

Everything an agent wants to DO arrives as Python source over SysEx and is
executed inside FL's own interpreter, in a namespace that persists for the
lifetime of the FL session. Adding a capability is therefore sending a
different string, not editing this file, which is what removes the
edit-restart-FL loop entirely.

Install once. If you find yourself wanting to edit this file to add a
feature, that feature belongs in injected code instead.
"""

import base64
import json
import time

try:
    import traceback
except Exception:                                    # pragma: no cover
    traceback = None

import channels
import device
import general
import midi
import mixer
import patterns
import playlist
import plugins
import transport
import ui

# Optional across FL builds. Bound anyway so injected code can test them.
try:
    import arrangement
except Exception:
    arrangement = None
try:
    import utils
except Exception:
    utils = None


# ---------------------------------------------------------------------------
# Wire protocol. Mirrored exactly by agentfl/sysex.py.
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 1

SYSEX_MANUFACTURER = 0x7D                # non-commercial / educational use
SYSEX_MAGIC = (0x41, 0x47, 0x46)         # "AGF"

DIR_REQUEST = 0x01
DIR_RESPONSE = 0x02
DIR_HEARTBEAT = 0x03

REQUEST_ID_LEN = 8

# manufacturer + magic + direction + request id + chunk index + chunk count
HEADER_LEN = 1 + 3 + 1 + REQUEST_ID_LEN + 1 + 1

# Payload bytes per outgoing chunk. Conservative: some MIDI stacks choke well
# before the theoretical limit, and a response that never arrives is far worse
# than one that arrives in four pieces.
CHUNK_PAYLOAD = 256
MAX_CHUNKS = 128

HEARTBEAT_INTERVAL = 0.5

# An inject that runs longer than this has almost certainly hung FL's UI
# thread. We cannot pre-empt it (no threads in the sandbox), but we can report
# it so the caller learns which snippet is the offender.
SLOW_INJECT_SECONDS = 0.75


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------

_fl_version = "unknown"
_send_sysex = None
_last_heartbeat = 0.0

# Reassembly buffers for multi-chunk requests, keyed by request id.
_inbox = {}

# The persistent namespace injected code runs in. Survives across calls, so a
# helper defined once stays callable for the rest of the FL session.
_NS = {}

_print_buffer = []


def _ns_print(*args, **kwargs):
    """Replaces print() inside injected code so output comes back to the agent.

    FL's script output window is not readable from outside the process, so
    anything printed there is lost. Capturing it here is the only way an agent
    ever sees it.
    """
    sep = kwargs.get("sep", " ")
    try:
        _print_buffer.append(sep.join(str(a) for a in args))
    except Exception:
        _print_buffer.append("<unprintable>")


def _reset_namespace():
    _NS.clear()
    _NS.update({
        "__builtins__": __builtins__,
        "channels": channels,
        "device": device,
        "general": general,
        "midi": midi,
        "mixer": mixer,
        "patterns": patterns,
        "playlist": playlist,
        "plugins": plugins,
        "transport": transport,
        "ui": ui,
        "arrangement": arrangement,
        "utils": utils,
        "print": _ns_print,
    })


# ---------------------------------------------------------------------------
# FL lifecycle
# ---------------------------------------------------------------------------

def OnInit():
    global _fl_version, _send_sysex
    try:
        _fl_version = ui.getVersion()
    except Exception:
        _fl_version = "unknown"

    # Name differs across builds; resolve once.
    _send_sysex = getattr(device, "midiOutSysex", None)
    if _send_sysex is None:
        _send_sysex = getattr(device, "midiOutSysEx", None)

    _reset_namespace()

    print("[AgentFL] kernel up. FL %s, protocol v%d, sysex=%s"
          % (_fl_version, PROTOCOL_VERSION, _send_sysex is not None))

    # The hint bar is the only kernel state visible from outside FL without a
    # working return path, which makes it the one way to tell "script not
    # loaded" apart from "script loaded but output port not routed".
    _hint("AgentFL ready sysex=%s" % (_send_sysex is not None))
    _emit_heartbeat()


def OnDeInit():
    print("[AgentFL] kernel down.")


def OnIdle():
    global _last_heartbeat
    now = time.time()
    if now - _last_heartbeat >= HEARTBEAT_INTERVAL:
        _last_heartbeat = now
        try:
            _emit_heartbeat()
        except Exception as exc:
            _hint("AgentFL heartbeat error %s" % type(exc).__name__)


def OnRefresh(flags):
    return


def OnMidiMsg(event):
    """Older FL builds deliver incoming SysEx here."""
    event.handled = _on_sysex(event)


def OnSysEx(event):
    """FL 21+ / scripting v40 delivers incoming SysEx here."""
    event.handled = _on_sysex(event)


def _hint(text):
    try:
        ui.setHintMsg(str(text))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------

def _encode_chunks(direction, request_id, payload_obj):
    """Serialise payload and split it into wire-safe chunks.

    Base64 keeps every byte under 0x80, which SysEx requires. Returns a list
    of framed byte strings, each ready to hand to device.midiOutSysex.
    """
    rid = request_id.encode("ascii")
    rid = (rid + b"00000000")[:REQUEST_ID_LEN]

    body = json.dumps(payload_obj, ensure_ascii=True, separators=(",", ":"))
    b64 = base64.b64encode(body.encode("utf-8"))

    pieces = [b64[i:i + CHUNK_PAYLOAD] for i in range(0, len(b64), CHUNK_PAYLOAD)]
    if not pieces:
        pieces = [b""]
    if len(pieces) > MAX_CHUNKS:
        # Refuse rather than silently truncate: a half a result is a lie.
        return _encode_chunks(direction, request_id, {
            "ok": False,
            "error": "result too large: %d chunks, limit %d. Return less, or "
                     "page it." % (len(pieces), MAX_CHUNKS),
            "code": "result_too_large",
        })

    out = []
    total = len(pieces)
    for idx, piece in enumerate(pieces):
        frame = bytearray()
        frame.append(SYSEX_MANUFACTURER)
        frame.extend(SYSEX_MAGIC)
        frame.append(direction & 0x7F)
        frame.extend(rid)
        frame.append(idx & 0x7F)
        frame.append(total & 0x7F)
        frame.extend(piece)
        out.append(bytes([0xF0]) + bytes(frame) + bytes([0xF7]))
    return out


def _decode_frame(data):
    """Parse one incoming frame. Returns None if it is not ours."""
    if len(data) < HEADER_LEN:
        return None
    if data[0] != SYSEX_MANUFACTURER:
        return None
    if (data[1], data[2], data[3]) != SYSEX_MAGIC:
        return None
    direction = data[4]
    try:
        rid = bytes(data[5:5 + REQUEST_ID_LEN]).decode("ascii", "replace")
    except Exception:
        return None
    idx = data[5 + REQUEST_ID_LEN]
    total = data[6 + REQUEST_ID_LEN]
    return direction, rid, idx, total, bytes(data[HEADER_LEN:])


def _send(direction, request_id, payload_obj):
    if _send_sysex is None:
        return
    for frame in _encode_chunks(direction, request_id, payload_obj):
        try:
            _send_sysex(frame)
        except Exception as exc:
            print("[AgentFL] sysex send failed: %s" % exc)
            return


def _emit_heartbeat():
    _send(DIR_HEARTBEAT, "00000000", {
        "v": PROTOCOL_VERSION,
        "fl_version": _fl_version,
        "ts": time.time(),
    })


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

def _on_sysex(event):
    raw = getattr(event, "sysex", None)
    if raw is None:
        return False
    raw = bytes(raw)
    if raw[:1] == b"\xf0":
        raw = raw[1:]
    if raw[-1:] == b"\xf7":
        raw = raw[:-1]

    parsed = _decode_frame(raw)
    if parsed is None:
        return False                       # not ours, let FL have it
    direction, rid, idx, total, piece = parsed
    if direction != DIR_REQUEST:
        return False

    # Reassemble. Chunks may in principle arrive out of order, so index them
    # rather than appending.
    slot = _inbox.get(rid)
    if slot is None or slot["total"] != total:
        slot = {"total": total, "parts": {}, "started": time.time()}
        _inbox[rid] = slot
    slot["parts"][idx] = piece
    if len(slot["parts"]) < total:
        return True                        # consumed, waiting for the rest

    del _inbox[rid]
    try:
        b64 = b"".join(slot["parts"][i] for i in range(total))
        request = json.loads(base64.b64decode(b64).decode("utf-8"))
    except Exception as exc:
        _send(DIR_RESPONSE, rid, {
            "ok": False,
            "error": "undecodable request: %s" % exc,
            "code": "bad_request",
        })
        return True

    _send(DIR_RESPONSE, rid, _handle(request))
    return True


def _handle(request):
    cmd = request.get("cmd", "")
    params = request.get("params") or {}
    started = time.time()
    try:
        if cmd == "ping":
            data = _cmd_ping(params)
        elif cmd == "inject":
            data = _cmd_inject(params)
        elif cmd == "reset":
            _reset_namespace()
            data = {"reset": True}
        else:
            return {"ok": False, "error": "unknown command: %s" % cmd,
                    "code": "unknown_command"}
        return {"ok": True, "v": PROTOCOL_VERSION, "data": data,
                "elapsed": round(time.time() - started, 4)}
    except Exception as exc:
        return {"ok": False, "code": "kernel_error",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": _format_exc()}


def _cmd_ping(params):
    return {
        "kernel": "AgentFL",
        "protocol": PROTOCOL_VERSION,
        "fl_version": _fl_version,
        "sysex_out": _send_sysex is not None,
        "namespace_keys": len(_NS),
        "ts": time.time(),
    }


def _cmd_inject(params):
    """Run Python inside FL and return whatever it produced.

    Semantics, chosen to match what a REPL does because that is what an agent
    expects: if the source is a single expression it is evaluated and its
    value returned; otherwise it is executed and the value of RESULT (if the
    code sets it) is returned. Anything printed is captured either way.
    """
    source = params.get("code")
    if not isinstance(source, str) or not source.strip():
        return {"error": "no code supplied"}

    del _print_buffer[:]
    started = time.time()
    value = None
    mode = "exec"

    try:
        compiled = compile(source, "<inject>", "eval")
        mode = "eval"
    except SyntaxError:
        compiled = compile(source, "<inject>", "exec")

    if mode == "eval":
        value = eval(compiled, _NS)
    else:
        exec(compiled, _NS)
        value = _NS.get("RESULT")

    elapsed = time.time() - started
    out = {
        "mode": mode,
        "value": _safe(value),
        "stdout": list(_print_buffer),
        "elapsed": round(elapsed, 4),
    }
    if elapsed > SLOW_INJECT_SECONDS:
        # Injected code runs on FL's UI thread. Slow code is not just slow, it
        # freezes the interface and can glitch audio, so say so loudly.
        out["warning"] = ("took %.2fs on FL's UI thread; this blocks the "
                          "interface and can glitch audio" % elapsed)
    del _print_buffer[:]
    return out


def _format_exc():
    if traceback is None:
        return None
    try:
        return traceback.format_exc()[-2000:]
    except Exception:
        return None


def _safe(obj, depth=0):
    """Coerce an arbitrary Python value into something JSON can carry.

    FL's API hands back plenty of objects that json refuses. Falling back to
    repr keeps a result useful instead of turning it into an error.
    """
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # NaN and inf are not valid JSON and silently corrupt the parse.
        if obj != obj or obj in (float("inf"), float("-inf")):
            return repr(obj)
        return obj
    if depth >= 6:
        return repr(obj)[:200]
    if isinstance(obj, (list, tuple)):
        return [_safe(x, depth + 1) for x in obj[:500]]
    if isinstance(obj, dict):
        return dict((str(k), _safe(v, depth + 1))
                    for k, v in list(obj.items())[:500])
    return repr(obj)[:500]
