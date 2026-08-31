---
name: fl-arrange
description: Place pattern clips in the playlist and arrange a track. Read this before attempting arrangement, because seven routes are already eliminated and the remaining leads are listed.
---

# Arranging: unsolved, and the highest value thing to solve

This is the most important missing capability. It is **not solved and not
closed**. Read `docs/arrangement-investigation.md` before starting, so you
work the frontier instead of repeating dead ends.

## Do not repeat these. All eliminated by measurement

- `playlist` module: 41 functions, none touch clips
- `arrangement` module: 9 functions, markers and selection only
- all 79 `FPT_` command bus ids
- `ui.insert` / `ui.paste` / `ui.enter` with the playlist focused
- `FPT_Insert` / `FPT_Paste` / `FPT_ItemMenu` / `FPT_Menu`, undo never moved
- posted mouse clicks: delivered, ignored, FL reads the real cursor
- posted keyboard: delivered, ignored

## The live lead: the REC bus

`general.processRECEvent` is readable via `REC_GetValue = 2`, verified by
reading `REC_Tempo` back as `140000`. Playlist clip constants exist
(`REC_PLClip_First/Last`, `REC_Pat_Clip`, `REC_PLTrack_First/Last`).

Only 9 of 65536 item offsets were sampled. **That is a sample, not a search.**
The untried leads, in order, are in the investigation doc: the low id
namespace starting at `0x00000000`, a full item sweep, the `REC_Chan_*` bases,
other flag combinations, song mode plus record, and the piano roll scripting
surface.

## Rules

- reading is safe, writing to an unidentified id is not. `general.undoUp()`
  recovers
- `getUndoHistoryPos()` before and after detects change cheaply
- `ui.getHintMsg()` after a write tells you what FL thinks it did. That is how
  `0x50015000` was identified as a knob rather than a clip
- batch large reads. A big result exceeds the SysEx chunk limit and hangs
- never say "impossible" from a sampled search. Say what was sampled
- `SetCursorPos` and `mouse_event` stay banned. The user keeps their mouse

## What the agent can still do for an arrangement

- create and name patterns, and fill them with steps (`fl-pattern`)
- name, colour, mute and solo playlist **tracks**, which is real preparation
- add and jump to arrangement markers via `arrangement.addAutoTimeMarker`, so
  the section structure is laid out even though the clips are not
- set tempo, routing, levels and plugin parameters

A useful handover is: patterns built and named, mixer routed and labelled,
markers placed for the sections. Then the only remaining action is dragging
clips onto lanes.

## If offline is acceptable

A `.flp` can be edited on disk, which does reach clips. It is not live: FL has
to close the file, the edit happens, and FL reopens it. That breaks the point
of this repo, so it belongs to batch work on closed projects and never to an
interactive session. Do not offer it as if it were equivalent.
