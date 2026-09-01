# AgentFL

Drive FL Studio the way an agent drives a browser. FL is the page, and injected
Python is the JavaScript console.

```
inject   run Python inside FL's live interpreter      the powerful one
read     structured snapshot of the project
see      capture FL's window as an image
point    click and drag FL's UI, without moving your mouse
```

## Why injection rather than more tools

The usual FL bridge ships a fixed table of commands compiled into a controller
script. FL loads that script once at startup, so every new capability means
editing the script and restarting FL, and you lose the open project each time.
The table is also always incomplete, because it can only contain what someone
thought of in advance.

The kernel here has no command table. It knows three things: ping, inject and
reset. It knows nothing about mixers, channels, plugins or patterns, and it
never should. Capability arrives as Python source over the wire and runs in
FL's own interpreter, in a namespace that persists for the FL session.

Adding a feature is therefore sending a different string. FL stays open.

## Install

Once, and only once:

```powershell
pip install -e .
powershell -File kernel\install.ps1
```

Then in FL, **Options > MIDI Settings**:

| List | Port | Setting |
|---|---|---|
| Input | `FLStudioMCP RX` | Controller type `AgentFL`, Port `42` |
| Output | `FLStudioMCP TX` | Port `42`, the same number |

The output row is the one that gets missed. Without it the kernel loads and
runs perfectly, heartbeats into nothing, and the agent side reports a dead
bridge. Restart FL once. That should be the last time.

Verify:

```bash
python -m agentfl.doctor
```

It checks five layers in order and names the one that broke, because a flat
"not connected" sends you rewriting a script that was never the problem.

## Use

```python
import agentfl

fl = agentfl.connect()
fl.ping()

fl.inject("mixer.trackCount()")                    # expression, returns a value
fl.inject("mixer.setTrackVolume(3, 0.7)")          # statement
fl.inject("""
def loud(threshold=0.85):
    return [i for i in range(mixer.trackCount())
            if mixer.getTrackVolume(i) > threshold]
RESULT = loud()
""")
```

Definitions persist, so `loud()` stays callable for the rest of the FL session
without being resent.

## What injection reaches, and what it does not

Generic across every plugin, with no per-plugin work, because FL exposes
parameters by index:

```python
fl.inject("""
count = plugins.getParamCount(0, 3)
RESULT = [(i, plugins.getParamName(i, 0, 3), plugins.getParamValue(i, 0, 3))
          for i in range(count)]
""")
```

Reachable: mixer, channels, plugin parameters, routing, transport, tempo,
patterns, colours, naming, selection.

**Not reachable, at any price.** FL's Python API has no function for these, so
no amount of injection gets you there:

- moving, adding or deleting playlist clips
- loading a new plugin instance
- writing piano roll notes

For those, see `docs/api-surface.md`. The honest options are the UI layer or
leaving the job to a human, and pretending otherwise wastes an afternoon.

## The mouse rule

Nothing in this repo may move the physical cursor. No `SetCursorPos`, no
`mouse_event`, no `SendInput`. Those drive the one pointer the user is also
holding, which makes the machine unusable while an agent works.

UI interaction is posted messages to FL's window handles instead, so the
cursor never moves and FL does not need focus. Posted clicks are reliable.
Posted drags may not be, because VCL applications often read the real cursor
during a drag. `pointer.probe_drag` answers that on your build rather than
assuming it. When a drag is not honoured, the answer is injection or a human,
never the real cursor.

## Layout

```
kernel/device_AgentFL.py   installed into FL, never edited to add features
kernel/install.ps1         one time installer
agentfl/sysex.py           wire protocol, mirrored by the kernel
agentfl/bridge.py          MIDI transport, request/response
agentfl/window.py          finding FL's windows by class
agentfl/pointer.py         posted mouse messages, cursor untouched
agentfl/screen.py          capturing FL
agentfl/doctor.py          layered diagnosis
skills/                    task level skills an agent invokes
docs/api-surface.md        what FL's API can and cannot do
```

## Why MIDI

It looks like an odd transport for RPC. It is the only one available. FL's
scripting sandbox gives a script no sockets and no filesystem, so MIDI SysEx is
the only way bytes leave the process. Every richer looking option is not slower,
it is absent.

## License

MIT. See `LICENSE`.

FL Studio and Image-Line are trademarks of Image-Line nv. This project is not
affiliated with or endorsed by them.
