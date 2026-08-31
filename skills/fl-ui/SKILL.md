---
name: fl-ui
description: Act on FL Studio's interface for the things that have no Python API, without moving the user's mouse. Use only for playlist clips, loading plugins, or menu actions that injection cannot reach.
---

# Touching FL's interface

Last resort, not first. If the FL API can do it, inject instead. This path
exists only for the operations that genuinely have no API.

## The rule that cannot be broken

**Never move the physical cursor.** `SetCursorPos`, `mouse_event` and
`SendInput` are banned. There is one pointer and the user is holding it.
Driving it makes the machine unusable while you work and steals focus from
whatever they were doing.

Everything here posts messages to FL's window handles instead. The cursor does
not move, and FL does not even need to be focused.

If a posted interaction is not honoured, do not reach for the real cursor.
Fall back to injection, or say the operation needs a human.

## Find FL and act

```python
from agentfl import window, pointer

win = window.main_window()
pointer.click(win.hwnd, x, y)            # client coordinates
pointer.click_screen(win.hwnd, sx, sy)   # absolute screen coordinates
```

Coordinates in `lParam` are client relative. Getting that wrong is silent: the
click lands somewhere else in FL and you will not be told.

## Drags are not guaranteed

Posted clicks are reliable. Posted drags may not be, because VCL applications
often take mouse capture and then read the real cursor position during the
drag, ignoring posted motion entirely.

Measure it, do not assume it:

```python
pointer.probe_drag(win.hwnd, x1, y1, x2, y2)
```

It reports whether the real cursor stayed put. It cannot tell you whether FL
acted on the drag, so capture the window before and after and compare.

## Snap decides whether a move is musically correct

Before dragging anything in the playlist or piano roll, check FL's snap
selector in the toolbar. If it reads `(none)`, a drag is pixel exact and will
land off the grid, which looks like a bug in your maths and is not. Set snap
to `Bar` first and FL quantises the result for you, which removes the need for
pixel precision entirely.

## Popups close between commands

FL's dropdown menus close when focus moves. Opening a menu in one command and
clicking an item in the next does not work: the menu is gone and the click
lands on whatever is underneath, which in the playlist means creating a clip
you did not want.

Open the menu and select the item **in the same command**, with the capture in
between if you need to see the options.

## Always verify with a capture

```python
from agentfl import screen
screen.grab_fl("captures/after.png", region=(0, 0, 900, 300))
```

A posted message returning success means it was delivered to the queue. It
does not mean FL did anything with it. Look.
