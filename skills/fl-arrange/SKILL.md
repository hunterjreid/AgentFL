---
name: fl-arrange
description: Place pattern clips in the playlist and arrange a track. Read this before attempting arrangement, because the automated routes are measured and they do not work.
---

# Arranging, and why the agent cannot do it alone

This is the one boundary in FL that has not been crossed. Read this before
promising an arrangement, not after an hour of attempts.

## Three routes, all measured, all closed

**No API.** `playlist` exposes 41 functions and not one touches clips. It is
tracks (`getTrackName`, `setTrackColor`, `muteTrack`, `soloTrack`,
`selectTrack`), live performance mode, and display zone. `arrangement` adds
markers and selection only. There is no add, move or delete for clips.

**Not on the command bus.** All 79 `FPT_` commands were listed. Nothing places
a clip. `FPT_Cut`, `FPT_Copy` and `FPT_Paste` exist, but they act on an
existing selection, and there is nothing to select in an empty playlist.

**Posted clicks are ignored.** A `WM_LBUTTONDOWN` / `WM_LBUTTONUP` pair posted
to FL's main form at valid playlist client coordinates placed nothing. The
message was delivered and the physical cursor correctly did not move. FL takes
mouse capture and reads the real cursor position, so posted input does not
drive the playlist. This is measured on FL 24.1.2, not assumed.

## What to do instead

Say it plainly and early: **arrangement is the human's part.** Do everything
else, and hand over a project where placing clips is the only thing left.

Do not:

- reach for `SetCursorPos` or `mouse_event`. Banned, and the reason is in
  CLAUDE.md. The user keeps their mouse
- retry posted clicks with different coordinates. The coordinates were right
- claim an arrangement happened because a call returned without error. Look at
  the playlist

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
