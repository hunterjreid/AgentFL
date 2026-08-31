---
name: fl-connect
description: Bring the FL Studio bridge up and diagnose it when it is down. Use whenever an FL action fails, the bridge reports dead, FL was just restarted, or before the first injection of a session.
---

# Connecting to FL Studio

## Always diagnose before rebuilding anything

```bash
python -m agentfl.doctor
```

Five layers, checked in order. The first failure is the only one that means
anything, because a break at one layer makes every check below it noise.

## The failure that actually happens

The kernel is loaded and healthy inside FL, emitting heartbeats, while the
agent side hears nothing at all. Both halves look correct in isolation.

Tell it apart in one glance: **look at FL's hint bar, top left of FL's
window.** If it reads `AgentFL ready`, the kernel is running fine and the
problem is purely that FL is not routing its output.

Fix, in FL: **Options > MIDI Settings**, the **Output** list. Enable
`FLStudioMCP TX` and set its Port number to the same number `FLStudioMCP RX`
has in the Input list.

This is worth internalising because the symptom points at the script and the
cause is a checkbox. Do not start rewriting the kernel.

## Layer by layer

| Symptom | Cause | Fix |
|---|---|---|
| No main form found | FL not running | Start FL |
| Ports missing | loopMIDI ports not created | Create `FLStudioMCP RX` and `FLStudioMCP TX` in loopMIDI |
| Ports will not open | another process holds them | Windows MIDI inputs are exclusive. Kill stale `fl-studio-mcp` or `agentfl` processes. Several can accumulate across sessions and only the oldest gets the port |
| No heartbeat, hint bar reads `AgentFL ready` | output port unrouted | MIDI Settings, Output list, matching port number |
| No heartbeat, hint bar empty | kernel not loaded | `powershell -File kernel\install.ps1`, then set Controller type to `AgentFL` on the input, then restart FL |
| Heartbeat arrives, ping times out | input unrouted | Enable `FLStudioMCP RX` in the Input list, Controller type `AgentFL` |

## Restarting FL

Only two things justify it: installing the kernel for the first time, and a
change to the wire protocol. Adding capability never does. If you are about to
restart FL to add a feature, you are editing the kernel and you should not be.

## Verify, do not assume

```python
import agentfl
fl = agentfl.connect()
print(fl.ping())
```

A successful ping proves both directions are routed. Nothing less does.
