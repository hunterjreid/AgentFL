# Getting the kernel to actually load

Five separate things stop a controller script from loading, and every one of
them presents identically: FL runs fine, the script never executes, and
nothing anywhere reports an error. All five were hit in one session. They are
listed in the order worth checking.

## 1. The Welcome wizard blocks script initialisation

**This is the big one and it is invisible.** While FL's "Welcome to FL Studio"
dialog is open, FL has not finished bringing the session up, and **no
controller script is loaded**. The main form exists, FL is responsive, the
window looks completely normal behind the dialog.

Dismissing the wizard loads the script immediately. Heartbeats start within a
second.

```bash
python scripts/restart_fl.py launch     # waits for the form, then closes it
```

This alone caused hours of misdiagnosis: it was blamed on MIDI routing, then
on the script header, then on the script's own code. The tell is that
**nothing at all** arrives on the wire, not even a malformed frame.

## 2. `supportedDevices` must be empty

```python
# name=AgentFL
# url=...
# receiveFrom=
# supportedDevices=          <- EMPTY
```

Naming a device there tells FL the script binds only to a port with exactly
that name. FL then filters the script out for every other port and never
imports it. Silent, like everything else here.

## 3. Registry values are all REG_SZ, and a DWORD crashes FL

Under `HKCU\Software\Image-Line\FL Studio 24\Devices\MIDI input\<port>`, every
value is a string, including numeric looking ones like `Port` and `Enabled`.

Writing `Enabled` as a DWORD does not fail at write time. FL reads it at
startup and **hard crashes**:

```
Exception: Invalid data type for 'Enabled'
Callstack: ... FLEngine_x64.dll ...
```

The callstack points into the audio engine and looks nothing like a registry
problem. `scripts/use-kernel.ps1` now writes strings explicitly and asserts
every value is REG_SZ afterwards.

## 4. FL rewrites its config on exit

An edit to those keys while FL is running is discarded silently when FL
closes. Always close FL first. `use-kernel.ps1` refuses to run otherwise.

## 5. A stale process holds the MIDI port

Windows MIDI **inputs are exclusive**. Server processes accumulate across
sessions, and only the oldest one holds the port, so every newer one hears
nothing and reports a dead bridge. Check for multiple `agentfl` or
`fl-studio-mcp` processes before changing any configuration.

## Diagnosing: what a missing `__pycache__` does and does not mean

A `__pycache__` next to the script proves FL imported it. **The absence proves
nothing.** FL was observed loading and running a script with no `__pycache__`
present, so treat missing bytecode as a weak hint, never as evidence the
script failed.

The reliable check is the wire. Listen for SysEx directly:

```python
import mido
name = next(n for n in mido.get_input_names() if n.startswith("FLStudioMCP TX"))
with mido.open_input(name) as port:
    ...  # AgentFL heartbeats carry magic 7d 41 47 46, "}AGF"
```

Traffic means the kernel is alive. Silence means it is not, and then the list
above is the order to work through.

## The one restart

Installing the kernel needs one FL restart, because FL binds scripts at
startup. After that, capability arrives as injected code and FL stays open.
If you are restarting FL to add a feature, you are editing the kernel, and
you should not be.
