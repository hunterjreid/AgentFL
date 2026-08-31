# Placing playlist clips: open investigation

**Status: not solved, not closed.** The highest value missing capability.
Several routes are eliminated by measurement, and the REC bus address space is
now correctly mapped after an early mistake sent the search into the wrong
range entirely.

All measurements on FL Studio Producer Edition v24.1.2 build 4394, against a
real project (`Cold Pocket`) containing an actual audio clip and markers, so a
zero reading means "not here" rather than "nothing loaded".

## The correction that matters most

**`channels.getRecEventId(0)` returns `0x40000`, not `0x50000000`.**

An early scan assumed the playlist lived under `REC_Pat_First` (`0x50000000`)
and swept a few thousand ids there. Every read returned 0, and that was
briefly taken as evidence that clips are not on the bus. It was evidence that
the search was in the wrong address space.

Ask FL for the base. Do not derive it from constants:

```python
base = channels.getRecEventId(channel)      # 0x40000 for channel 0
general.processRECEvent(base + midi.REC_Chan_Vol, 0, midi.REC_GetValue)
```

Verified live reads on a loaded project:

| Offset | Id | Value |
|---|---|---|
| `REC_Chan_Vol` | `0x40000` | 10000 |
| `REC_Chan_Pan` | `0x40001` | 6400 |
| `REC_Chan_Mute` | `0x40007` | 1 |
| `REC_Chan_Plugin_First` | `0x48000` | `REC_InvalidID` |
| `REC_Chan_Clip` | `0x45000` | 0 |
| `REC_Chan_PianoRoll` | `0x44000` | 0 |

The bus is readable and correct. `REC_GetValue = 2`.

## Eliminated, with evidence

| Route | Evidence |
|---|---|
| `playlist` module | 41 functions. Tracks, mute/solo, colours, live mode. No clip functions |
| `arrangement` module | 9 functions. Markers and selection only |
| Command bus | all 79 `FPT_` ids enumerated, none create a clip |
| `ui.insert`/`paste`/`enter`, `FPT_Insert`/`Paste`/`ItemMenu`/`Menu` | playlist focused, `getUndoHistoryPos` never moved, no popup opened |
| Posted keyboard | correct scan-code lParam for space, `transport.isPlaying()` unchanged |
| Posted clicks **on the playlist** | ignored, tested against the correct window (see below) |
| `REC_Chan_Clip` write | `0x45000` moves undo but places no clip. Value encoding unknown |

## Posted input: works on FL, fails on the playlist canvas

This distinction was missed at first and is important.

**Posted clicks do work on FL.** FL's "Save changes?" dialog was dismissed by
posting `WM_LBUTTONDOWN`/`UP` to the `TQuickFocusBtn` "No" button. FL closed,
the physical cursor never moved. So FL's message loop processes posted mouse
input normally.

**The playlist ignores them**, and not because the wrong window was targeted.
FL's playlist is its own child window, `TEventEditForm`, titled `Playlist -`,
found by enumerating children of `TFruityLoopsMainForm` (`EnumWindows` only
returns top level windows, which is why it was invisible at first). Posting a
click there, with correct client coordinates, did not move the playhead.

Conclusion: the playlist canvas takes mouse capture and reads the real cursor.
Anything drawn by FL rather than backed by a child control will behave the
same way. Anything that IS a real control can be driven by posted messages.

Useful child windows found: `TEventEditForm` (playlist), `TStepSeqForm`
(channel rack), `TFXForm` (mixer), `TSampleListForm` (browser).

## Untried, in order of promise

1. **Sweep channel 0's item space with and without a clip, and diff.** Read
   `0x40000` to `0x4FFFF` on a project with a clip, then on one without, and
   compare. This is the only method that does not depend on guessing which
   offset means what. Batch the reads: a large result exceeds the SysEx chunk
   limit and the call hangs, which was observed.
2. **The value encoding for `REC_Chan_Clip`.** The write is accepted and moves
   undo, so the id is real. The value `96` was arbitrary. Position, length and
   pattern are presumably packed, and `TLC_SubNum_ClipPos = 0x10000` hints at
   the field layout.
3. **`REC_Chan_PianoRoll` at `0x44000`.** A separate, high value lead: if
   notes are writable on the bus, that solves melody writing properly rather
   than through the step sequencer.
4. **A playlist track base.** `channels.getRecEventId` exists for channels.
   Look for the equivalent for playlist tracks rather than assuming
   `REC_PLTrack_First` arithmetic.
5. **Flag combinations.** Only two were tried.
6. **Song mode plus record.**

## Rules for continuing

- ask FL for ids (`getRecEventId`), never derive them from constants
- reading is safe, writing to an unidentified id is not. `general.undoUp()`
  recovers, and it works
- `getUndoHistoryPos()` before and after is the cheapest change detector
- `ui.getHintMsg()` after a write names what FL thinks it did. That is how an
  early candidate was identified as a knob rather than a clip
- work on a **copy** of a project. FL takes a `.flp` path on the command line,
  which loads a known arranged project with no mouse involved
- never conclude "impossible" from a sampled search. State what was sampled
