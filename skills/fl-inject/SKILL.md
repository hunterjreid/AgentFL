---
name: fl-inject
description: Run Python inside FL Studio's live interpreter to read or change anything the FL API exposes. Use for any FL task involving mixer, channels, plugins, routing, transport, tempo or patterns. This is the primary way to act on FL.
---

# Injecting Python into FL

The equivalent of a browser's JavaScript console. Anything FL's API can do,
injected code can do, with no new plumbing per capability and no restart.

```python
import agentfl
fl = agentfl.connect()
```

## Two shapes

A single expression is evaluated and its value returned:

```python
fl.inject("mixer.trackCount()")
```

Anything longer is executed, and `RESULT` comes back if the code sets it:

```python
fl.inject("""
loud = [i for i in range(mixer.trackCount())
        if mixer.getTrackVolume(i) > 0.85]
RESULT = loud
""")
```

## Definitions persist

The namespace lives for the whole FL session. Define once, call cheaply after:

```python
fl.inject("""
def track_report(i):
    return {'name': mixer.getTrackName(i),
            'vol': mixer.getTrackVolume(i),
            'pan': mixer.getTrackPan(i)}
""")
fl.inject("RESULT = [track_report(i) for i in range(1, 8)]")
```

Prefer this over resending a large body every call. It is faster, and it keeps
each message inside the chunk limit.

## Hard rules

**Injected code runs on FL's UI thread.** There is no thread to move work onto
inside the sandbox. Slow code freezes FL's interface and can glitch audio on a
live project. Keep snippets short. Never write a polling loop or a sleep. The
kernel warns above 0.75s, and that warning means you did something wrong.

**Validate indices before writing.** An out of range index into
`plugins.setParamValue` and friends can hard crash FL and take the unsaved
project with it. Read the count first. Before any sweep that writes many
parameters, save the project.

**Read back before claiming success.** `ok` means the call did not raise. It
does not mean the value landed or that it was the right value. Read it back,
or capture the window, and say which one you did.

**Bulk work in one call, not many.** Every injection is a MIDI round trip.
Looping in Python on the agent side and injecting per track is many times
slower than injecting one loop.

## Reset

```python
fl.reset()
```

Clears the namespace without restarting FL. Use it when a definition has gone
stale, never as a way to recover from a crash.

## Know the holes first

Playlist clip moves, loading plugin instances and writing piano roll notes have
no API. No injection reaches them. See `docs/api-surface.md` and say so up
front rather than attempting workarounds that cannot work.
