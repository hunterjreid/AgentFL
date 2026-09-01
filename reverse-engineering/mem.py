"""Snapshot and diff FL64's private memory, read-only, from outside.

    python mem.py snapshot <pid> <outfile>
    python mem.py diff <before> <after>

The diff is the reverse-engineering workhorse: snapshot with an empty project,
have FL change one thing (add a channel, drop a step), snapshot again, and the
diff shows exactly which regions and offsets moved. That narrows FL's project
model from 98 MB to a handful of structures. Nothing here writes to FL.
"""
import ctypes
import pickle
import sys
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
PAGE_RW, PAGE_WC, PAGE_GUARD = 0x04, 0x08, 0x100


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

# Writable private data only, and skip large regions (samples/video/GPU buffers)
# where the project model does not live and which make the diff noisy.
MAX_REGION = 16 * 1024 * 1024


def _read(h, base, size):
    buf = (ctypes.c_char * size)()
    got = ctypes.c_size_t(0)
    if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size, ctypes.byref(got)):
        return bytes(buf[:got.value])
    return b""


def snapshot(pid, outfile):
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print("OpenProcess failed", ctypes.get_last_error()); return 1
    regions, addr, mbi = {}, 0, MBI()
    total = 0
    while addr < 0x7FFFFFFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base, size = mbi.BaseAddress or 0, mbi.RegionSize
        want = (mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE
                and mbi.Protect in (PAGE_RW, PAGE_WC) and not (mbi.Protect & PAGE_GUARD)
                and 0 < size <= MAX_REGION)
        if want:
            data = _read(h, base, size)
            if data:
                regions[base] = data
                total += len(data)
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt
    with open(outfile, "wb") as fh:
        pickle.dump(regions, fh, protocol=4)
    print(f"snapshot: {len(regions)} private regions, {total // (1024*1024)} MB -> {outfile}")
    return 0


def _changed_runs(a, b, min_gap=16):
    """Offsets where a and b differ, coalesced into runs."""
    runs, start, last = [], None, None
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            if start is None:
                start = i
            elif i - last > min_gap:
                runs.append((start, last)); start = i
            last = i
    if start is not None:
        runs.append((start, last))
    return runs


def diff(before, after):
    with open(before, "rb") as fh:
        A = pickle.load(fh)
    with open(after, "rb") as fh:
        B = pickle.load(fh)
    a_keys, b_keys = set(A), set(B)
    new = sorted(b_keys - a_keys)
    gone = sorted(a_keys - b_keys)
    print(f"regions: {len(A)} before, {len(B)} after | new={len(new)} gone={len(gone)}")
    for base in new[:20]:
        print(f"  NEW region @ {base:#x} size {len(B[base])}")

    common = sorted(a_keys & b_keys)
    changed_regions = 0
    for base in common:
        a, b = A[base], B[base]
        if a == b:
            continue
        runs = _changed_runs(a, b)
        if not runs:
            continue
        changed_regions += 1
        if changed_regions <= 40:
            print(f"  region @ {base:#x}: {len(runs)} run(s)")
            for s, e in runs[:6]:
                span = b[s:e + 1][:32]
                print(f"      +{s:#08x}..{e:#x}  {span.hex()}")
    print(f"changed regions: {changed_regions}")
    return 0


def diff3(idle_a, idle_b, after):
    """Signal = changed(idle_b -> after) minus regions that also change idle->idle.

    idle_a and idle_b are two snapshots with nothing done between them, so their
    delta is pure engine noise. Any region in that noise set is masked out, and
    what remains is the project-model change FL made.
    """
    with open(idle_a, "rb") as fh:
        IA = pickle.load(fh)
    with open(idle_b, "rb") as fh:
        IB = pickle.load(fh)
    with open(after, "rb") as fh:
        AF = pickle.load(fh)

    noisy = {b for b in (set(IA) & set(IB)) if IA[b] != IB[b]}
    print(f"masking {len(noisy)} noisy regions")

    new = sorted(set(AF) - set(IB))
    for base in new[:20]:
        print(f"  NEW region @ {base:#x} size {len(AF[base])}")

    signal = 0
    for base in sorted(set(IB) & set(AF)):
        if base in noisy:
            continue
        a, b = IB[base], AF[base]
        if a == b:
            continue
        runs = _changed_runs(a, b)
        if not runs:
            continue
        signal += 1
        print(f"  SIGNAL region @ {base:#x}: {len(runs)} run(s)")
        for s, e in runs[:8]:
            before_bytes = a[s:e + 1][:24]
            after_bytes = b[s:e + 1][:24]
            print(f"      +{s:#08x}  {before_bytes.hex()}  ->  {after_bytes.hex()}")
    print(f"signal regions (noise masked): {signal}")
    return 0


def diff4(idle_a, idle_b, sig_before, sig_after):
    """Isolate one action. Noise = regions changing idle_a->idle_b. Signal =
    changes sig_before->sig_after with those noisy regions masked out. Use to
    single out e.g. placing playlist clips without the mixer edits before it.
    """
    snaps = {}
    for name in (idle_a, idle_b, sig_before, sig_after):
        with open(name, "rb") as fh:
            snaps[name] = pickle.load(fh)
    IA, IB, SB, SA = snaps[idle_a], snaps[idle_b], snaps[sig_before], snaps[sig_after]

    noisy = {b for b in (set(IA) & set(IB)) if IA[b] != IB[b]}
    print(f"masking {len(noisy)} noisy regions")

    new = sorted(set(SA) - set(SB))
    for base in new[:30]:
        print(f"  NEW region @ {base:#x} size {len(SA[base])}")
    gone = sorted(set(SB) - set(SA))
    for base in gone[:10]:
        print(f"  GONE region @ {base:#x} size {len(SB[base])}")

    signal = 0
    for base in sorted(set(SB) & set(SA)):
        if base in noisy:
            continue
        a, b = SB[base], SA[base]
        if a == b:
            continue
        runs = _changed_runs(a, b)
        if not runs:
            continue
        signal += 1
        print(f"  SIGNAL region @ {base:#x}: {len(runs)} run(s)")
        for s, e in runs[:10]:
            print(f"      +{s:#08x}  {a[s:e+1][:24].hex()}  ->  {b[s:e+1][:24].hex()}")
    print(f"signal regions (noise masked): {signal}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "snapshot":
        raise SystemExit(snapshot(int(sys.argv[2]), sys.argv[3]))
    if cmd == "diff":
        raise SystemExit(diff(sys.argv[2], sys.argv[3]))
    if cmd == "diff3":
        raise SystemExit(diff3(sys.argv[2], sys.argv[3], sys.argv[4]))
    if cmd == "diff4":
        raise SystemExit(diff4(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]))
    print("usage: mem.py snapshot <pid> <out> | diff <a> <b> "
          "| diff3 <idleA> <idleB> <after> | diff4 <idleA> <idleB> <sigBefore> <sigAfter>")
    raise SystemExit(2)
