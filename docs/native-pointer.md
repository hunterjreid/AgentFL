# The native pointer: drops and clicks without the mouse

The Python API cannot add a channel, load a plugin or effect, or place a
playlist clip. A person does all of those with the mouse: drag a file in, or
click on the playlist. `reverse-engineering/drop/fldrop.c` does the same from
inside FL, with no physical cursor movement, while FL sits behind other
windows. Measured on FL 24.1.2, Windows 11, 24 Sep 2026.

## What works, verified by reading the result back

| action | how | verified by |
|---|---|---|
| add a sampler channel | drop a `.wav` on the channel rack's empty bottom strip | `channels.channelCount(True)` +1, type 0 |
| load a synth | drop a channel preset `.fst` (3x Osc etc.) on the rack | new channel, type 2 |
| load a mixer effect | select the insert, drop a plugin database `.fst` on an effect slot | `plugins.getPluginName(insert, slot)` |
| audio clip on the playlist | drop a `.wav` on the playlist | clip visible, channel type 4 |
| pattern clip on the playlist | `mouse.click` with the draw tool, snap on Bar | `ui.getHintMsg()` reads `bar:01:00 for 1:00:00` |
| scroll the playlist | `mouse.drag` the top scrollbar thumb | ruler in a window capture |

## How it works

`fldrop.dll` is loaded onto FL's UI thread by a `WH_GETMESSAGE` hook from
`agentfl/drop.py` or `agentfl/mouse.py`. A registered message (`AgentFL.Drop`,
`AgentFL.Mouse`) triggers it; the request is a file in `%TEMP%`.

Drops call the target window's own `IDropTarget` (the `OleDropTargetInterface`
window property, FL's code in `FLEngine_x64.dll`) with a shell `IDataObject`:
DragEnter, DragOver, Drop, exactly as Explorer does.

Clicks send `WM_MOUSEMOVE`/`WM_LBUTTONDOWN`/`WM_LBUTTONUP` to the deepest FL
window under the agent's point.

## Why FL refused at first, and the fix

FL does not trust the coordinates it is handed. It checks where the cursor is,
which window is under it, and whether a button is down. With the real cursor
elsewhere, or another app covering FL, DragEnter succeeds, DragOver returns
`E_UNEXPECTED` (a Delphi safecall exception) and Drop is silently declined.

For the length of one action every one of those questions is answered from
the agent's pointer:

- the import AND delay-load tables of every non-system module in FL. The
  engine delay-loads `GetPhysicalCursorPos`, invisible in the normal table
- user32's own pointer slots: `GetCursorPos`, `GetCursorInfo`,
  `GetMessagePos`, `WindowFromPoint`, `WindowFromPhysicalPoint` are each
  `jmp [rip+disp]`, so swapping the slot catches callers that used
  `GetProcAddress`. The saved original is what the fake falls back to, or it
  recurses
- `WindowFromPoint` answers with FL's own window for any point inside FL, not
  only the exact agent point. **Occlusion was the last blocker**: while
  another window covered FL the real answer was that window, and FL threw
- foreground, active window, button state, and the trigger message's `pt`

All of it is restored 0.3 s after a drop and at the end of a click. The DLL
pins itself so it cannot unload while FL's imports point into it. A hooked DLL
stays loaded in FL for the session, so each rebuild gets a new file name
(`fldropN.dll`) and `drop.DLL` picks the newest.

## Traps, each one hit

- **FL resolves the target by what is at the point, not the window you pass.**
  A drop point outside the channel rack lands on the playlist and makes an
  audio clip channel (type 4) instead of a sampler.
- **Loading a plugin opens its editor,** which then covers the rack; the next
  drop lands on the editor and REPLACES that plugin's preset. Close editors
  (`channels.showEditor(i, 0)`, or WM_CLOSE on `TPluginForm`) after each load.
- **Dropping on an existing channel's name replaces its sample.** Aim at the
  empty strip at the bottom of the rack, and re-measure the rack every time.
- **Snap defaults to (none).** Clips land wherever the click is, up to a step
  late. Set `ui.snapMode` until `ui.getSnapMode() == midi.Snap_Bar`.
- **After placing a clip FL keeps it selected,** and the next click only
  deselects. Retry each placement until the hint reads `bar:01:00`.
- **A click just after a bar line hits the previous clip's edge.** Click the
  centre of the bar (see below).
- **Do not place clips while the song plays.** The view shifted and clips
  landed on the wrong tracks.
- **Handing FL a file on the command line** (`FL64.exe sample.wav`) raises a
  "Dropped sample(s)" dialog (audio clip / audio track / instrument track /
  cancel) whose buttons take posted clicks. A second route to add sounds.
- **A Python process that is not DPI aware gets scaled coordinates.** A
  `WindowFromPoint` check from it can report the wrong window.
- **Never grab someone else's window for a test.** Create and own it.

## The agent pointer

`agentfl/ghost.py` draws a click-through orange arrow labelled with the
action, which glides to every point the agent acts on. The human keeps their
own cursor and can see what the agent is doing.

## Placing clips reliably (learned laying out a 32 bar track)

- **Measure the grid, never estimate it.** Read the pixel run of a known block
  of clips from a window capture (for example bars 5 to 12 on one track) and
  derive x of bar 1 and px per bar from it. An estimate off by half a pixel per
  bar puts later clicks into the previous bar.
- **Click the centre of the bar,** not near its start. Snap is Bar, so the
  clip still lands on the bar line, and half a bar of error is tolerated.
- **Verify every clip with the hint, and print every result.** A filtered
  report hid a run of failures once. `bar:01:00 for 1:00:00` is the only pass.
- **Zoom with the plain mouse wheel over the time ruler** (`wheel` op, negative
  delta zooms out). Ctrl+wheel over the grid zoomed in both directions.
  Dragging the scrollbar thumb's edge only scrolls. FL will not zoom out past
  the song's length, so an empty song stays at about 17 bars: place the first
  section, then zoom out further.
- **The paint brush drag fills only every other bar** here, for the same
  select/deselect reason as clicks. Centre clicks are slower but exact.

## Exporting (File > Export > MP3), done without the keyboard

- **A click that opens a menu does not return until the menu closes.** FL runs
  menus and dialogs as modal loops inside the click's `SendMessage`, so the
  fake pointer stays on and the result file stays locked until every modal
  window has closed, and no second click can start. Make that one click, then
  drive everything after it with posted keys.
- **FL's popup menus (`TQuickPopupMenuWindow`) take posted keys.** From File:
  Down x9 reaches Export, Right opens it, then Wave is first and MP3 second.
- **Save As is the standard `#32770` dialog.** `WM_SETTEXT` the Edit with
  control id 1001, then post `WM_COMMAND IDOK`.
- **The render window (`TWAVRenderForm`) starts on a posted Enter.** Its
  buttons are drawn, not controls. A 32 bar song rendered to MP3 in 5 s.

## Traps found building the README demo (26 Sep 2026)

- **A step that is already on keeps its old note.** `setGridBit(ch, s, 1)` on a
  lit step plus a new `pPitch` stacks a second note under the first, so the
  channel plays chords. Turn every step off first, then write.
- **Bar snap rounds to the nearest bar.** A click at exactly the centre of bar
  1 lands the clip on bar 2. Aim about 30 percent into the bar.
- **Off screen, FL leaves black holes in a capture.** It skips painting what
  is off the desktop. `screen.capture_window` forces a full repaint first.
- **The user may move FL while you work.** Maximising it changed the layout
  under a run of clicks and five placements missed. Re-measure from a fresh
  capture after anything outside the agent could have touched FL.
- **FL crashed once in `USER32!GetWindowRect`** (access violation, offset
  0x3cf8b on 10.0.26100.9444) straight after a clip placement. The native
  pointer does not patch that function; the cause is not known. The same
  placements ran clean after a relaunch. Save before long click runs.
- **`FPT_Save` on an unsaved project opens Save As in FL's last used
  folder,** which can be one of the user's own project folders. Fill the
  filename box yourself (`Edit` with control id 1001, found by walking the
  dialog's children) rather than accepting the default.
