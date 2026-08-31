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

## Check the Welcome wizard first. It is the usual cause

While FL's "Welcome to FL Studio" dialog is open, **no controller script is
loaded at all**. FL looks completely normal behind it: main form present,
responsive, MIDI configured. Nothing reaches the wire.

```bash
python scripts/restart_fl.py launch     # waits for the form, then dismisses it
```

Heartbeats start within a second of the dialog closing. Check this before
touching any configuration, because it presents exactly like a broken script,
a broken route and a broken install all at once. See `docs/install-traps.md`
for the other four ways a script silently fails to load.

## Reading the wire directly beats every other diagnostic

Traffic means the kernel is alive, silence means it is not, and nothing else
is as decisive. AgentFL heartbeats carry magic `7d 41 47 46` (`}AGF`) twice a
second.

Do not use a missing `__pycache__` as evidence: FL has been observed running a
script without writing one.

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
