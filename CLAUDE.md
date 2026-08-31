# Rules for agents working in this repo

## Never move the physical cursor

`SetCursorPos`, `mouse_event` and `SendInput` are banned. There is one pointer
and the user is holding it. Moving it makes the machine unusable while you
work and steals focus from whatever they were doing.

UI actions go through `agentfl.pointer`, which posts messages to FL's window
handles. The cursor does not move and FL does not need focus.

If a posted interaction is not honoured, do not fall back to the real cursor.
Fall back to injection, or say the operation needs a human.

## Never add features to the kernel

`kernel/device_AgentFL.py` exposes ping, inject and reset. That is the whole
surface and it is deliberate. Editing it requires restarting FL, which loses
the open project, and that restart loop is the entire problem this repo
exists to remove.

If you want FL to do something new, send Python. The only reason to touch the
kernel is a change to the wire protocol itself, and then `agentfl/sysex.py`
must change in lockstep, because a protocol mismatch presents as silence
rather than an error.

## Injected code runs on FL's UI thread

There is no thread to move work onto inside the sandbox. Slow injected code
freezes FL's interface and can glitch audio on a live project. Keep snippets
short. The kernel flags anything over 0.75s. Never write a polling loop or a
sleep inside injected code.

## Validate indices before writing

Out of range indices into `plugins.setParamValue` and friends can hard crash
FL and take the unsaved project with it. Read the count first, and before any
sweep that writes many parameters, save.

## Diagnose in layers, never guess

Run `python -m agentfl.doctor`. The failure that actually happens is a kernel
that is loaded and healthy while the agent hears nothing, because FL's MIDI
OUTPUT port is unrouted. Both halves look fine alone. FL's hint bar shows
`AgentFL ready` when the kernel is live, which separates "not loaded" from
"not routed" in one glance.

## Do not claim FL did something without checking

An injected call returning `ok` means the call did not raise. It does not mean
the result is what was wanted. Read the value back, or capture the window, and
say which one you did.

## Know what is impossible before promising it

Playlist clip moves, loading plugin instances and writing piano roll notes
have no Python API. See `docs/api-surface.md`. Say so plainly rather than
attempting workarounds that cannot work.

## Style

No em dashes or en dashes anywhere. Comments explain why, not what.
