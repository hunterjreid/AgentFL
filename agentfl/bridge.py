"""The MIDI bridge between an agent and the AgentFL kernel inside FL Studio.

SysEx over a pair of loopback MIDI ports is not an obvious transport for an
RPC channel, and it is worth saying why it is the right one. FL's scripting
sandbox does not give a script sockets or a filesystem, so MIDI is the only
way data leaves the process at all. Every richer looking option (a local HTTP
server, a named pipe, a file on disk) is unavailable inside FL, not merely
slower.

Two ports are needed because MIDI is unidirectional:

    agent  -> "AgentFL RX" -> FL Studio        (requests)
    FL Studio -> "AgentFL TX" -> agent         (responses and heartbeats)
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import mido

from . import sysex

DEFAULT_RX = "FLStudioMCP RX"   # agent writes here, FL reads
DEFAULT_TX = "FLStudioMCP TX"   # FL writes here, agent reads


class BridgeError(RuntimeError):
    pass


class NotConnected(BridgeError):
    pass


@dataclass
class InjectResult:
    ok: bool
    value: object = None
    stdout: list = None
    elapsed: float = 0.0
    mode: str = ""
    error: str = ""
    traceback: str = ""
    warning: str = ""

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        if not self.ok:
            return f"<InjectResult FAILED {self.error!r}>"
        return f"<InjectResult {self.value!r} in {self.elapsed}s>"


def _match_port(names: list[str], wanted: str) -> str | None:
    """Windows appends an index to MIDI port names, so match on prefix.

    'AgentFL RX' is presented by the driver as 'AgentFL RX 0'. Matching
    exactly finds nothing and looks exactly like a missing port.
    """
    for name in names:
        if name == wanted or name.startswith(wanted + " "):
            return name
    return None


class Bridge:
    def __init__(self, rx: str = DEFAULT_RX, tx: str = DEFAULT_TX):
        self.rx_name = rx
        self.tx_name = tx
        self._out = None
        self._in = None
        self._reasm = sysex.Reassembler()
        self.last_heartbeat: float = 0.0
        self.fl_version: str = "unknown"

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> "Bridge":
        outs = mido.get_output_names()
        ins = mido.get_input_names()

        out_name = _match_port(outs, self.rx_name)
        in_name = _match_port(ins, self.tx_name)
        if out_name is None:
            raise BridgeError(
                f"no MIDI output port matching {self.rx_name!r}. "
                f"Create it in loopMIDI. Present: {outs}"
            )
        if in_name is None:
            raise BridgeError(
                f"no MIDI input port matching {self.tx_name!r}. "
                f"Create it in loopMIDI. Present: {ins}"
            )

        # Exclusive on Windows: a stale process holding this port makes a
        # perfectly healthy kernel look dead, so name that in the error.
        try:
            self._out = mido.open_output(out_name)
            self._in = mido.open_input(in_name)
        except Exception as exc:
            raise BridgeError(
                f"could not open MIDI ports ({exc}). Windows MIDI inputs are "
                "exclusive, so check for another agentfl or fl-studio-mcp "
                "process already holding them."
            ) from exc
        return self

    def close(self) -> None:
        for port in (self._out, self._in):
            try:
                if port is not None:
                    port.close()
            except Exception:
                pass
        self._out = self._in = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_exc):
        self.close()

    # -- transport ---------------------------------------------------------

    def _require(self):
        if self._out is None or self._in is None:
            raise NotConnected("call connect() first")

    def _drain(self) -> None:
        """Discard buffered traffic so a stale reply cannot answer a new call."""
        self._require()
        for _ in self._in.iter_pending():
            pass

    def _send(self, request_id: str, cmd: str, params: dict) -> None:
        payload = {"v": sysex.PROTOCOL_VERSION, "cmd": cmd, "params": params}
        for frame in sysex.encode(sysex.DIR_REQUEST, request_id, payload):
            self._out.send(mido.Message("sysex", data=frame))

    def _await(self, request_id: str, timeout: float) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._in.iter_pending():
                if msg.type != "sysex":
                    continue
                frame = sysex.decode_frame(bytes(msg.data))
                if frame is None:
                    continue
                if frame.direction == sysex.DIR_HEARTBEAT:
                    self.last_heartbeat = time.time()
                    continue
                if frame.direction != sysex.DIR_RESPONSE:
                    continue
                if frame.request_id != request_id:
                    continue
                done = self._reasm.feed(frame)
                if done is not None:
                    return done
            time.sleep(0.002)
        raise TimeoutError(
            f"no response to {request_id} within {timeout}s. Either the kernel "
            "is not loaded in FL, or FL's MIDI output port is not routed back "
            "(a live kernel with an unrouted output looks exactly like this)."
        )

    def call(self, cmd: str, params: dict | None = None,
             timeout: float = 5.0) -> dict:
        self._require()
        self._drain()
        request_id = secrets.token_hex(4)
        self._send(request_id, cmd, params or {})
        return self._await(request_id, timeout)

    # -- commands ----------------------------------------------------------

    def wait_alive(self, timeout: float = 3.0) -> bool:
        """Watch for a heartbeat. Proves the kernel is loaded AND routed back.

        Distinct from ping(): this needs nothing from us, so it separates "the
        kernel is not running" from "our request never reached it".
        """
        self._require()
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self._in.iter_pending():
                if msg.type != "sysex":
                    continue
                frame = sysex.decode_frame(bytes(msg.data))
                if frame is not None and frame.direction == sysex.DIR_HEARTBEAT:
                    self.last_heartbeat = time.time()
                    return True
            time.sleep(0.01)
        return False

    def ping(self, timeout: float = 3.0) -> dict:
        reply = self.call("ping", timeout=timeout)
        if reply.get("ok"):
            self.fl_version = reply["data"].get("fl_version", "unknown")
        return reply

    def reset(self) -> dict:
        """Clear the injected namespace without restarting FL."""
        return self.call("reset")

    def inject(self, code: str, timeout: float = 10.0) -> InjectResult:
        """Run Python inside FL Studio and return what it produced.

        A single expression is evaluated and its value returned. Anything
        longer is executed, and the value of RESULT comes back if the code
        sets it. Definitions persist for the rest of the FL session.
        """
        reply = self.call("inject", {"code": code}, timeout=timeout)
        if not reply.get("ok"):
            return InjectResult(
                ok=False,
                error=reply.get("error", "unknown error"),
                traceback=reply.get("traceback", "") or "",
            )
        data = reply.get("data") or {}
        return InjectResult(
            ok=True,
            value=data.get("value"),
            stdout=data.get("stdout") or [],
            elapsed=data.get("elapsed", 0.0),
            mode=data.get("mode", ""),
            warning=data.get("warning", "") or "",
        )
