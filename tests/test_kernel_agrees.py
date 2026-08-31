"""Cross-check the kernel's codec against the client's.

The kernel reimplements framing because it runs inside FL and cannot import
this package. Two implementations of one protocol is exactly the setup where
they drift apart, and the failure mode is silence: the kernel decides an
incoming frame is not addressed to it and hands it back to FL, so nothing
raises anywhere and the MIDI configuration takes the blame.

This test loads the real kernel file with FL's modules stubbed out, then feeds
each side's output to the other.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The kernel imports FL's modules at import time. Stub them so it loads here.
for name in ("channels", "device", "general", "midi", "mixer", "patterns",
             "playlist", "plugins", "transport", "ui", "arrangement", "utils"):
    sys.modules.setdefault(name, types.ModuleType(name))

import importlib.util  # noqa: E402

from agentfl import sysex  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "agentfl_kernel", ROOT / "kernel" / "device_AgentFL.py")
kernel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kernel)


def test_constants_match():
    """Any divergence here makes every message invisible to the other side."""
    assert kernel.PROTOCOL_VERSION == sysex.PROTOCOL_VERSION
    assert kernel.SYSEX_MANUFACTURER == sysex.SYSEX_MANUFACTURER
    assert tuple(kernel.SYSEX_MAGIC) == tuple(sysex.SYSEX_MAGIC)
    assert kernel.HEADER_LEN == sysex.HEADER_LEN
    assert kernel.REQUEST_ID_LEN == sysex.REQUEST_ID_LEN
    assert kernel.DIR_REQUEST == sysex.DIR_REQUEST
    assert kernel.DIR_RESPONSE == sysex.DIR_RESPONSE
    assert kernel.DIR_HEARTBEAT == sysex.DIR_HEARTBEAT


def test_kernel_decodes_client_frames():
    payload = {"cmd": "inject", "params": {"code": "RESULT = 1 + 1"}}
    frames = sysex.encode(sysex.DIR_REQUEST, "feedface", payload)
    for raw in frames:
        parsed = kernel._decode_frame(bytes(raw))
        assert parsed is not None, "kernel rejected a frame the client produced"
        direction, rid, idx, total, _ = parsed
        assert direction == sysex.DIR_REQUEST
        assert rid == "feedface"
        assert total == len(frames)


def test_kernel_decodes_multichunk_client_frames():
    payload = {"cmd": "inject", "params": {"code": "q = 0\n" * 3000}}
    frames = sysex.encode(sysex.DIR_REQUEST, "feedface", payload)
    assert len(frames) > 1
    for raw in frames:
        assert kernel._decode_frame(bytes(raw)) is not None


def test_client_decodes_kernel_frames():
    """The kernel frames responses with F0/F7; the client must cope."""
    frames = kernel._encode_chunks(kernel.DIR_RESPONSE, "feedface",
                                   {"ok": True, "data": {"x": list(range(400))}})
    reasm = sysex.Reassembler()
    result = None
    for raw in frames:
        body = raw[1:-1]                      # strip the kernel's F0/F7
        frame = sysex.decode_frame(body)
        assert frame is not None, "client rejected a frame the kernel produced"
        got = reasm.feed(frame)
        if got is not None:
            result = got
    assert result["ok"] is True
    assert result["data"]["x"] == list(range(400))


def test_kernel_safe_handles_awkward_values():
    """FL returns values json refuses. They must degrade, not explode."""
    assert kernel._safe(float("nan")) == "nan"
    assert kernel._safe(float("inf")) == "inf"
    assert kernel._safe([1, 2, 3]) == [1, 2, 3]
    assert kernel._safe({"a": 1}) == {"a": 1}
    assert isinstance(kernel._safe(object()), str)
    deep = kernel._safe([[[[[[[[1]]]]]]]])
    assert deep is not None


def test_kernel_refuses_oversized_result():
    """Better a clear error than half a result presented as whole."""
    frames = kernel._encode_chunks(kernel.DIR_RESPONSE, "feedface",
                                   {"data": "x" * 400_000})
    reasm = sysex.Reassembler()
    result = None
    for raw in frames:
        got = reasm.feed(sysex.decode_frame(raw[1:-1]))
        if got is not None:
            result = got
    assert result["ok"] is False
    assert result["code"] == "result_too_large"


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ok    {name}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
