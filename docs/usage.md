
# Using AgentFL

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

## Connect an agent

Six actions, the same from a shell or over MCP. Points are pixels in the image
`see` returns, so an agent looks, picks a spot and acts on it.

```
agentfl ping                          is FL there
agentfl read                          tempo, channels, patterns, inserts
agentfl inject "mixer.setTrackVolume(1, 0.7)"
agentfl inject -f build_drums.py
agentfl see fl.png                    capture FL, even when it is covered
agentfl drop kick.wav --at 154 149    add a channel, load a plugin, place audio
agentfl click 612 488
agentfl drag 300 200 700 200
```

Over MCP (`pip install -e .[mcp]`):

```bash
claude mcp add agentfl -- agentfl-mcp
```

The server exposes `fl_inject`, `fl_read`, `fl_see`, `fl_drop`, `fl_click` and
`fl_drag`, and nothing else. Every musical capability is Python sent through
`fl_inject`, which is why the list never has to grow.

None of them take over your mouse or your screen. Captures come from FL's own
surface, and clicks and drops happen inside FL. FL has to be open and not
minimised, and that is all. Set `AGENTFL_GHOST=1` to see an agent pointer
glide to each point it acts on.

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

**No Python API, done through the native pointer instead.** FL's API has no
function for adding a channel, loading a plugin or placing a playlist clip.
AgentFL does those the way a person does, by dropping files and clicking, but
from inside FL so your own mouse never moves. See `docs/native-pointer.md`.

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
agentfl/drop.py            file drops into FL, the native pointer
agentfl/mouse.py           clicks and drags into FL, the native pointer
agentfl/actions.py         the six actions shared by the CLI and MCP
agentfl/cli.py             agentfl command
agentfl/mcp_server.py      agentfl-mcp server
agentfl/screen.py          capturing FL
agentfl/doctor.py          layered diagnosis
skills/                    task level skills an agent invokes
docs/api-surface.md        what FL's API can and cannot do
docs/native-pointer.md     drops and clicks without the mouse
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
