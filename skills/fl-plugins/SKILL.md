---
name: fl-plugins
description: Read and change parameters on any plugin in FL Studio, VST or native, without per-plugin integration. Use when asked to adjust a plugin, find what a plugin exposes, sweep settings, or map a parameter by name.
---

# Controlling any plugin

There is no per-plugin integration work in FL, and this is the single most
useful fact in the whole API. FL exposes parameters by index for every plugin
it hosts, so one loop covers every plugin you will ever load.

```python
plugins.getParamCount(index, slotIndex)
plugins.getParamName(paramIndex, index, slotIndex)
plugins.getParamValue(paramIndex, index, slotIndex)
plugins.setParamValue(value, paramIndex, index, slotIndex)
plugins.isValid(index, slotIndex)
plugins.getPluginName(index, slotIndex)
```

`index` is the mixer track or channel, `slotIndex` the effect slot on it.

## Find what is loaded

```python
fl.inject("""
found = []
for track in range(mixer.trackCount()):
    for slot in range(10):
        if plugins.isValid(track, slot):
            found.append({'track': track, 'slot': slot,
                          'name': plugins.getPluginName(track, slot),
                          'params': plugins.getParamCount(track, slot)})
RESULT = found
""")
```

One call, whole project. Do not loop on the agent side and inject per track.

## Dump a plugin's parameters

```python
fl.inject("""
t, s = 3, 0
RESULT = [(i, plugins.getParamName(i, t, s), plugins.getParamValue(i, t, s))
          for i in range(plugins.getParamCount(t, s))]
""")
```

## Two real limits, both of which will bite

**Some VST3 plugins report zero parameters** until the wrapper's parameter
notification is enabled. A count of zero means "not exposed", not "no
parameters". Check the wrapper settings before concluding the plugin is
uncontrollable.

**Names are frequently useless.** Plenty of plugins report `Param 12` for
everything. When names do not identify what you need, map by behaviour: read
every value, have the user move the control they mean, read again, and diff.

```python
fl.inject("RESULT = [plugins.getParamValue(i, 3, 0) for i in range(plugins.getParamCount(3, 0))]")
# user moves the knob
fl.inject("RESULT = [plugins.getParamValue(i, 3, 0) for i in range(plugins.getParamCount(3, 0))]")
```

The index that changed is the one you want. This is more reliable than the
name list and takes ten seconds.

## Before writing

Values are normalised 0.0 to 1.0. Read the current value first so you can put
it back. Save the project before sweeping many parameters, because a bad index
can crash FL and lose the project.

```python
fl.inject("""
t, s, p = 3, 0, 12
before = plugins.getParamValue(p, t, s)
plugins.setParamValue(0.62, p, t, s)
RESULT = {'before': before, 'after': plugins.getParamValue(p, t, s)}
""")
```

Reading `after` back in the same call is the cheapest possible proof the write
landed. Do it every time.

## Cannot be done

Loading a new plugin instance. Nothing in `plugins` creates one. Only existing
instances can be controlled.
