# FL's API surface, as measured

Measured against **FL Studio Producer Edition v24.1.2 [build 4394]**, Python
3.12.1, by injecting into the running application. Nothing here is recalled or
inferred. Regenerate with `python -m agentfl.probe --sandbox`.

Knowing the holes matters more than knowing the surface, so the things that do
not work are stated as plainly as the things that do.

## Module sizes

| Module | Functions |
|---|---|
| `mixer` | 71 |
| `ui` | 71 |
| `channels` | 48 |
| `playlist` | 41 |
| `device` | 34 |
| `utils` | 29 |
| `patterns` | 25 |
| `general` | 24 |
| `transport` | 20 |
| `plugins` | 13 |
| `arrangement` | 9 |

## Writing notes: the step sequencer is the way in

The piano roll has no API, but the step sequencer does, and it writes into the
same pattern:

```python
channels.setGridBit(channel, step, 1)                 # place a step
channels.getGridBit(channel, step)                    # read it back
channels.setStepParameterByIndex(...)                 # per step pitch etc
channels.getStepParam(...) / getCurrentStepParam(...)
```

This is the only route from an agent to notes inside a pattern. Verify a write
with `getGridBit` in the same injection, because a silently ignored write is
otherwise indistinguishable from success.

## The command bus: 79 commands

`transport.globalTransport(midi.FPT_X, 1)` dispatches FL's own commands, the
ones its buttons and hotkeys drive. All 79 on this build:

```
FPT_AddAltMarker  FPT_AddMarker    FPT_ArrangementJog FPT_ChannelJog   FPT_Copy
FPT_CountDown     FPT_Cut          FPT_Delete         FPT_Down         FPT_Enter
FPT_Escape        FPT_F1..FPT_F12  FPT_FastForward    FPT_HZoomJog     FPT_Insert
FPT_ItemMenu      FPT_Jog          FPT_Jog2           FPT_Left         FPT_Loop
FPT_LoopRecord    FPT_MarkerJumpJog FPT_MarkerSelJog  FPT_Menu         FPT_Metronome
FPT_MixerWindowJog FPT_Mode        FPT_MoveJog        FPT_Mute         FPT_Next
FPT_NextMixerWindow FPT_NextWindow FPT_No             FPT_NudgeMinus   FPT_NudgePlus
FPT_Overdub       FPT_Paste        FPT_PatternJog     FPT_Play         FPT_Previous
FPT_PreviousNext  FPT_Punch        FPT_PunchIn        FPT_PunchOut     FPT_Record
FPT_Rewind        FPT_Right        FPT_Save           FPT_SaveNew      FPT_ShuffleJog
FPT_Snap          FPT_SnapMode     FPT_StepEdit       FPT_Stop         FPT_Strip
FPT_StripHold     FPT_StripJog     FPT_TapTempo       FPT_TempoJog     FPT_TrackJog
FPT_Undo          FPT_UndoJog      FPT_UndoUp         FPT_Up           FPT_VZoomJog
FPT_WaitForInput  FPT_WindowJog    FPT_Yes
```

`FPT_Save`, `FPT_Undo` and `FPT_Snap` are the ones worth reaching for first:
save before anything destructive, undo to back out, snap because a move made
with snap off lands off the grid and looks like an arithmetic bug.

There is no command for adding a channel or loading a plugin. Scanning this
list for one is how you confirm that, rather than assuming.

## Plugin parameters are generic

No per-plugin work. FL exposes parameters by index for anything it hosts:

```python
plugins.getParamCount(index, slotIndex)
plugins.getParamName(paramIndex, index, slotIndex)
plugins.getParamValue(paramIndex, index, slotIndex)
plugins.setParamValue(value, paramIndex, index, slotIndex)
plugins.isValid(index, slotIndex)
plugins.getPluginName(index, slotIndex)
```

Two limits worth expecting: some VST3s report zero parameters until the
wrapper's parameter notification is on, and many name everything `Param 12`,
in which case map by behaviour (read all values, have the user move the
control, read again, diff).

## Cannot be done

Confirmed by reading the full module listings, not by assumption.

| Want | Why not |
|---|---|
| Add a channel | `channels` has no `addChannel`. Nothing on the command bus either |
| Load a plugin instance | nothing in `plugins` creates one |
| Move a playlist clip | `playlist` exposes tracks, not clips |
| Write piano roll notes directly | no API. Use the step sequencer instead |

An empty project therefore cannot be filled from nothing. Work with the
channels a project already has, or say a human needs to add the instrument.
Say it at the start, not after an hour.

## The sandbox

Python 3.12.1. More permissive than folklore suggests, and less useful than
that sounds:

| Probe | Result |
|---|---|
| `import os` | works, returns a real cwd |
| `import sys` | works |
| `import socket` | works, `socket.socket` constructs |
| `import ast` | works |
| `open` in builtins | present |
| `tempfile.gettempdir()` | **TypeError: bad argument type for built-in operation** |

So the imports succeed but the underlying file operations are stubbed: the
failure surfaces deep inside `tempfile`, not at the import. Treat the
filesystem as unavailable. MIDI SysEx stays the transport, not because nothing
else exists, but because nothing else works.

Do not conclude from `import socket` succeeding that a socket transport is
viable. It has not been tested end to end, and the filesystem looked available
too.
