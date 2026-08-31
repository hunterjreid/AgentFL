"""Protocol round trip tests.

These matter more than they look. A chunking bug does not raise, it produces a
frame the kernel decides is not addressed to it and hands back to FL, so the
symptom is silence and the instinct is to blame the MIDI setup. Testing the
codec offline is the only cheap way to rule that out.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentfl import sysex  # noqa: E402


def roundtrip(payload):
    """Encode then reassemble, exactly as kernel and client do to each other."""
    frames = sysex.encode(sysex.DIR_REQUEST, "abcd1234", payload)
    reasm = sysex.Reassembler()
    result = None
    for raw in frames:
        frame = sysex.decode_frame(bytes(raw))
        assert frame is not None, "own frame failed to decode"
        got = reasm.feed(frame)
        if got is not None:
            result = got
    return result, len(frames)


def test_small_payload_single_frame():
    payload = {"cmd": "ping", "params": {}}
    got, n = roundtrip(payload)
    assert got == payload
    assert n == 1


def test_large_payload_chunks_and_rejoins():
    payload = {"cmd": "inject", "params": {"code": "x = 1\n" * 2000}}
    got, n = roundtrip(payload)
    assert got == payload, "large payload did not survive chunking"
    assert n > 1, "expected multiple chunks for a large payload"


def test_all_bytes_are_sysex_safe():
    """Every byte must be under 0x80 or the MIDI stack silently mangles it."""
    payload = {"cmd": "inject", "params": {"code": "s = 'unicode: café 中'"}}
    frames = sysex.encode(sysex.DIR_REQUEST, "abcd1234", payload)
    for frame in frames:
        for byte in frame:
            assert 0 <= byte < 0x80, f"byte {byte:#x} is not SysEx safe"


def test_unicode_survives():
    payload = {"cmd": "inject", "params": {"code": "café 中文"}}
    got, _ = roundtrip(payload)
    assert got == payload


def test_out_of_order_chunks_rejoin():
    """Nothing guarantees arrival order, so reassembly must not assume it."""
    payload = {"cmd": "inject", "params": {"code": "y = 2\n" * 2000}}
    frames = sysex.encode(sysex.DIR_REQUEST, "abcd1234", payload)
    assert len(frames) > 2

    reasm = sysex.Reassembler()
    result = None
    for raw in reversed(frames):
        got = reasm.feed(sysex.decode_frame(bytes(raw)))
        if got is not None:
            result = got
    assert result == payload


def test_foreign_sysex_is_ignored():
    """Other devices share the port. Their traffic must not be parsed as ours."""
    assert sysex.decode_frame(bytes([0x43, 0x10, 0x4C, 0x00])) is None   # Yamaha
    assert sysex.decode_frame(bytes([0x7D, 0x4D, 0x43, 0x50, 1, 0])) is None  # "MCP"
    assert sysex.decode_frame(b"") is None


def test_oversized_request_raises_rather_than_truncating():
    huge = {"cmd": "inject", "params": {"code": "z" * 400_000}}
    try:
        sysex.encode(sysex.DIR_REQUEST, "abcd1234", huge)
    except ValueError as exc:
        assert "chunks" in str(exc)
    else:
        raise AssertionError("oversized payload should raise, not truncate")


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
