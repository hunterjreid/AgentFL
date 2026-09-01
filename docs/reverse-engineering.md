# Reverse engineering FL's project model in memory

The Python API is the sanctioned way to drive FL, and the rest of this repo
uses it. It cannot do four things: add a channel, load a plugin instance, place
a playlist clip, or write piano roll notes. Those are the operations that need
FL's native project model, not its Python wrapper. This document is the map for
reaching that model directly.

## Why the bridge exists at all, stated with evidence

FL runs its embedded CPython as a hard sandbox, and this is the single most
important fact about the whole system. Measured inside FL's own interpreter,
every C-extension object constructor returns NULL:

| operation | result inside FL |
|---|---|
| `open()` a file | `_io.FileIO returned NULL` |
| `socket.socket()` | `_socket.socket returned NULL` |
| start a thread | `start_new_thread returned NULL` |
| `import ctypes` then use it | `LoadLibrary returned NULL` |
| pure Python (json, math, str) | works |

This holds in the main interpreter (InterpreterID 0) as well as the controller
script subinterpreter, so it is not a subinterpreter quirk, it is deliberate.
The consequence: **no file, socket, or thread channel can be opened from FL's
Python.** MIDI SysEx is not a clumsy choice, it is the only channel FL leaves
open. Do not go looking for a "simpler" transport; there is not one.

## The opening: the sandbox is Python only

Native code in FL's process is not sandboxed at all. Two footholds follow.

**External, read-only, cannot crash FL.** `ReadProcessMemory` from a separate
process reads FL's entire address space. This is the safe way to observe the
project model, and it is where all reverse engineering should start. See
`reverse-engineering/mem.py`.

**Injected, in-process, unrestricted.** A DLL loaded into FL64 runs full Win32:
it can `fopen`, spawn threads, and call FL's own functions. It can also run
Python through FL's already-loaded `python312.dll` by resolving
`PyGILState_Ensure` / `PyRun_SimpleString` at runtime and holding the GIL
properly. Note this lands in the main interpreter, which does not contain the
`channels` / `mixer` API objects; those live in the script subinterpreter. So
injection is the path for native memory work, not for reaching the Python API.

## Finding the model: snapshot, change one thing, diff

FL's private memory is about 80 MB on an empty project. The model hides in
there among audio buffers, UI bitmaps, and undo history. The technique that
isolates it:

1. Snapshot FL's private, writable regions with `ReadProcessMemory`.
2. Change exactly one thing in FL.
3. Snapshot again and diff.

Two disciplines make the diff readable, and skipping either buries the signal:

- **Stop the transport.** A playing DAW rewrites meters, playheads, and voice
  state every frame. Diffs taken while playing are almost pure noise.
- **Mask the idle noise floor.** Even stopped, roughly three dozen regions
  churn on their own (timers, caches). Take two idle snapshots with nothing
  changed between them; any region that differs is noise and gets masked out of
  the real diff. `mem.py diff4` does exactly this.

One change at a time, transport stopped, noise masked: that is when a single
struct field falls out of the noise.

## Pinning a struct field

To locate where a playlist clip stores its bar position:

1. Transport stopped. Snapshot.
2. Place one clip at bar 1. Snapshot. The new allocation is the clip object.
3. Move that same clip to bar 5, change nothing else. Snapshot.

The bytes that move by a constant step across those snapshots are the position
field. Repeat for length, pattern id, and track. The same loop works for a
channel (add one), a mixer value (nudge one fader), or a note (draw one).

What has already been observed with this method: placing clips allocates new
private regions (the clip objects), loading a plugin writes its path as a
UTF-16 string, and the playlist redraw shows up as an ARGB pixel buffer that
must be recognised and ignored because it is rendering, not model.

## The honest limits

Native RE reaches everything the Python API cannot, but it is fragile: struct
layouts and function addresses shift with every FL build, so anything found
here is version specific and must be re-derived, or anchored to stable strings
rather than absolute addresses. It is a real research effort, not a quick
unlock. The Python API, where it works, is stable across versions; native is
the tool for the four things the API refuses, and only those.
