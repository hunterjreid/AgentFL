# Placing playlist clips: open investigation

**Status: not solved, not closed.** Placing a clip in the playlist is the
highest value missing capability. Seven routes have been eliminated by
measurement and several remain untried. This document exists so the next
session starts from the frontier instead of repeating the dead ends.

All measurements on FL Studio Producer Edition v24.1.2 build 4394.

## Eliminated, with evidence

| Route | Evidence |
|---|---|
| `playlist` module | 41 functions enumerated. Tracks, mute/solo, colours, live mode, display zone. No clip functions exist |
| `arrangement` module | 9 functions. Markers and selection only |
| Command bus | all 79 `FPT_` ids enumerated, none create a clip |
| `ui.insert` / `ui.paste` / `ui.enter` | playlist focused (`getFocusedFormCaption` returned `Playlist -`), `getUndoHistoryPos` never moved |
| `FPT_Insert` / `FPT_Paste` / `FPT_ItemMenu` / `FPT_Menu` | same, undo never moved, no popup opened (`ui.isInPopupMenu` stayed 0) |
| Posted mouse click | `WM_LBUTTONDOWN`/`UP` at correct client coordinates. Physical cursor confirmed unmoved, no clip appeared. FL takes mouse capture and reads the real cursor |
| Posted keyboard | `WM_KEYDOWN`/`UP` with correct scan-code lParam for space (play/stop). `transport.isPlaying()` never changed |

## The REC bus: partially explored, the best lead

`general.processRECEvent(id, value, flags)` is FL's internal parameter bus and
**it is readable**: `REC_GetValue = 2`. Verified by reading `REC_Tempo`, which
returned `140000`, matching the known tempo.

Relevant id constants:

```
REC_PLClip_First      0x00000000      <- note: ZERO
REC_PLClip_Last       0x5fffffff
REC_Pat_First         0x50000000
REC_Playlist_First    0x50000000
REC_Pat_Clip          0x50005000
REC_Chan_Clip         0x00005000      <- an item offset, not an absolute id
REC_PLTrack_First     0x60000000
REC_PLTrack_Last      0x6fffffff
REC_ItemMask          0x0000ffff
REC_ItemRange         0x00010000
REC_MaxPat            4096
```

The encoding is almost certainly
`REC_Pat_First + pattern * REC_ItemRange + item`, because
`REC_Pat_First + REC_MaxPat * REC_ItemRange` lands exactly on `REC_Pat_Last`.

**What was tried:** a scan of 20 patterns x 9 guessed item offsets, plus 20
playlist tracks x 4 offsets. Every read returned 0 on an empty playlist.
Writes were attempted at five ids; only `0x50015000` moved the undo position,
and FL's hint bar then reported **"Undone knob tweaks"**, so that id is a
parameter, not a clip slot.

**Why this is not conclusive:** `REC_ItemMask` is `0xFFFF`, so there are 65536
item offsets per pattern and only 9 were sampled. That is not an exhaustive
search, and it should not be described as one.

## Untried, in rough order of promise

1. **The low id namespace.** `REC_PLClip_First` is `0x00000000`, a completely
   different range from `REC_Pat_First`. It was never scanned. If playlist
   clips are addressed from zero, everything above looked in the wrong place.
2. **Full item sweep for one pattern.** Walk all 65536 offsets of
   `REC_Pat_First + 1 * REC_ItemRange + item` reading each. Batch it, because
   a large result exceeds the SysEx chunk limit and the call hangs (observed).
3. **`REC_Chan_*` bases.** These were filtered out of the constant dump by
   mistake and never examined. `REC_Chan_Clip` is `0x5000`, an item offset,
   which implies a channel base to add it to.
4. **Flag combinations.** Only one write combination was tried
   (`REC_UpdateValue | REC_UpdateControl | REC_SetChanged | REC_Store`).
   `REC_Init`, `REC_InitStore`, `REC_SetAll`, `REC_Store` alone, and
   `REC_NoSaveUndo` are all unexplored.
5. **Song mode plus recording.** Switching transport to song mode
   (`FPT_Mode`) and arming record was never tested for clip creation.
6. **FL's piano roll scripting surface.** A separate API from controller
   scripts, with its own module. Untouched.
7. **Diff learning.** Snapshot the id space, have a human place exactly one
   clip, snapshot again, diff. `scripts/rec_scan.py` does this and the
   baseline is already clean (0 non-zero ids on an empty playlist), so any
   non-zero afterwards is pure signal. This is the highest confidence route
   and it needs one human action.

## Rules for continuing

- Reading the REC bus is safe. Writing to an unidentified id is not: it can
  move parameters, and `general.undoUp()` is the recovery.
- `getUndoHistoryPos()` before and after is the cheapest change detector.
- Check `ui.getHintMsg()` after a write. FL names what it just did, which is
  how `0x50015000` was identified as a knob rather than a clip.
- Never conclude "impossible" from a sampled search. Say what was sampled.
