---
name: fl-pattern
description: Create, name and fill a pattern, then route it to the mixer. Use when asked to make a pattern, write a beat or a melody, put steps in the step sequencer, or send a channel to a mixer insert.
---

# Building a pattern

Every call below was run against FL 24.1.2 and verified by reading the result
back. Where something could not be verified it says so.

## The whole loop

```python
import agentfl
fl = agentfl.connect()

fl.inject("""
patterns.jumpToPattern(1)                       # creates it if absent
patterns.setPatternName(1, 'agent melody')

RIFF = [54, None, 57, None, 61, None, 59, None,
        57, None, 54, None, 57, 59, 61, None]   # None is a rest

import midi as m
for step, note in enumerate(RIFF):
    channels.setGridBit(0, step, 1 if note is not None else 0)
    if note is not None:
        channels.setStepParameterByIndex(0, 1, step, m.pPitch, note)

RESULT = [channels.getGridBit(0, s) for s in range(16)]
""")
```

`jumpToPattern` creates the pattern when it does not exist. That is the only
route to a pattern from nothing, because `patterns` has no create function.

## Verify the grid. You cannot currently verify the pitch

`getGridBit` reads back reliably. Check it in the same injection.

`getStepParam` is not what it looks like. It requires a `startPos` argument,
and called as `getStepParam(chan, pat, step, param)` it throws `RuntimeError`
on most steps and returns a wrong value on step 0. So **pitch writes are
accepted without error and cannot be read back**. Never report a melody as
confirmed because `setStepParameterByIndex` did not raise. Say the rhythm is
verified and the pitches are not.

## Routing to the mixer

```python
fl.inject("""
channels.setTargetFxTrack(0, 1)
mixer.setTrackName(1, 'MELODY')
mixer.setTrackVolume(1, 0.78)
RESULT = {'route': channels.getTargetFxTrack(0),
          'name': mixer.getTrackName(1)}
""")
```

Read `getTargetFxTrack` **before** writing. A channel is frequently already on
the insert you were about to assign, and saying "routed it" when nothing
changed is a false claim. Report what actually changed.

Volume is normalised, 1.0 is unity, about 0.78 leaves headroom.

## Pressing FL's buttons

```python
import midi as m
transport.globalTransport(m.FPT_Play, 1)
transport.globalTransport(m.FPT_Stop, 1)
transport.globalTransport(m.FPT_SnapMode, 1)
transport.globalTransport(m.FPT_F6, 1)          # channel rack
```

Verified: `FPT_Play` moves `transport.isPlaying()` 0 to 1 and `FPT_Stop` back.
`FPT_SnapMode` advances the snap selector, confirmed by reading the toolbar in
a screenshot, **not** by `ui.snapMode(0)`, which reported no change when the
interface had visibly changed. When a read contradicts the screen, distrust
the read.

## Two things you cannot do

**Add a channel or load an instrument.** `channels` has no `addChannel` and
nothing on the command bus adds one. An empty project cannot be populated. A
pattern written against a channel with nothing loaded is real data that makes
no sound, and that distinction must be stated rather than presented as a
finished beat.

**Place a clip in the playlist.** See `fl-arrange`. There is no API and posted
clicks do not work. This is the boundary of what an agent can do alone.
