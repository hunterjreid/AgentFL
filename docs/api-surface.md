# What FL's Python API can and cannot do

Knowing the holes matters more than knowing the surface. Every hour lost to
this project so far went into trying to reach something that has no API, so
check here before promising a capability.

Run `python -m agentfl.probe` against a live FL to regenerate the verified
half of this document. Anything below marked **unverified** is reasoning from
the module list, not a measurement, and should be confirmed before it is
relied on.

## Reachable by injection

| Area | Module | Notes |
|---|---|---|
| Mixer tracks | `mixer` | volume, pan, mute, solo, name, colour, routing, peaks |
| Channels | `channels` | volume, pan, mute, solo, name, colour, selection |
| Plugin parameters | `plugins` | generic by index, works on any VST or native plugin |
| Transport | `transport` | play, stop, record, song position, loop mode |
| Tempo | `mixer`, `general` | read directly, write via REC events |
| Patterns | `patterns` | select, name, colour, count |
| Arrangement markers | `arrangement` | add and jump to markers |
| UI navigation | `ui` | focus windows, menus, hint bar, selection |

### Plugin parameters are generic, which is the important one

There is no per-plugin integration work. FL exposes parameters by index for
every plugin it hosts:

```python
plugins.getParamCount(index, slotIndex)
plugins.getParamName(paramIndex, index, slotIndex)
plugins.getParamValue(paramIndex, index, slotIndex)
plugins.setParamValue(value, paramIndex, index, slotIndex)
```

Two real limits. Some VST3 plugins report zero parameters until the wrapper's
parameter notification is enabled. Many plugins name parameters uselessly
(`Param 12`), so an agent often has to map names by sweeping values and
watching what changes rather than by reading the list.

### `general.processRECEvent` is the back door

The widest reach in the API. It addresses FL's internal REC event ids, which
cover parameters the friendly modules never expose. It is also the easiest way
to corrupt a project, since an unknown id writes somewhere unintended. Probe
with reads before writes.

## Not reachable, at any price

No amount of injection reaches these. They have no API.

| Want | Reality | Actual options |
|---|---|---|
| Move, add or delete a playlist clip | `playlist` only does track names, colours, mute and performance mode | posted UI messages, or a human |
| Load a new plugin instance | nothing in `plugins` creates one | posted UI messages, or a human |
| Write piano roll notes | separate scripting surface, not reachable from a controller script | FL's own piano roll scripts, triggered manually |
| Create a pattern from scratch | `patterns` selects and renames, does not create | clone an existing pattern, or a human |

If a task needs one of these, say so at the start rather than after an hour of
attempts. That is the single most useful thing this document does.

## Editing the .flp instead

A project file can be edited offline, which reaches everything above,
including playlist clips. It is not live: FL must save, close the file, and
reload it. That breaks the entire point of this repo, so it belongs to batch
work on projects that are not currently open, never to interactive use.

## The sandbox

FL's scripting environment is CPython 3.12 with restrictions. Confirmed
available: `base64`, `json`, `math`, `time`, `traceback`. No sockets. No
threads to move slow work onto, which is why injected code blocking FL's UI
thread is a real hazard rather than a theoretical one.

Filesystem access is **unverified**. FL writes `__pycache__` next to the
kernel, so CPython itself clearly has disk access, but whether `open()` is
reachable from injected code is a separate question about restricted builtins.
Worth one probe, because if reads work then large code can be dropped on disk
and imported instead of chunked over MIDI.
