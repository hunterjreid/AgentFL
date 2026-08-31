"""Snapshot FL's REC event space so two snapshots can be diffed.

The REC bus is FL's own internal parameter bus, and `REC_GetValue` makes it
readable, which turns an undocumented id space into something that can be
learned empirically: snapshot, change one thing by hand, snapshot again, diff.
Whatever moved is the id for the thing you changed.

Reading is safe. Writing to an id you have not identified is not, so this
script only reads.

    python scripts/rec_scan.py before.json
    #  ... place ONE clip in the playlist by hand ...
    python scripts/rec_scan.py after.json
    python scripts/rec_scan.py --diff before.json after.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agentfl  # noqa: E402

# Read in batches: one injection per batch keeps the MIDI round trips down,
# and a batch that is too large blows the SysEx chunk limit on the way back.
BATCH = 220

SCAN = """
import midi as m
out = {}
for eid in %(ids)s:
    try:
        v = general.processRECEvent(eid, 0, m.REC_GetValue)
        if v:                      # only non-zero is interesting
            out[str(eid)] = v
    except Exception:
        pass
RESULT = out
"""


def id_space() -> list[int]:
    """The ids worth scanning, derived from the constants FL exposes.

    REC_Pat_First + pattern * REC_ItemRange + item, with REC_MaxPat patterns,
    lands exactly on REC_Pat_Last, which is what makes this encoding credible
    rather than a guess.
    """
    PAT_FIRST = 0x50000000
    PLTRACK_FIRST = 0x60000000
    ITEM_RANGE = 0x10000

    ids: list[int] = []
    # per pattern, a spread of item offsets around the known clip offset
    for pat in range(0, 20):
        base = PAT_FIRST + pat * ITEM_RANGE
        for item in (0x0000, 0x1000, 0x4000, 0x5000, 0x5001, 0x5002,
                     0x6000, 0x7000, 0x8000):
            ids.append(base + item)
    # per playlist track
    for track in range(0, 20):
        base = PLTRACK_FIRST + track * ITEM_RANGE
        for item in (0x0000, 0x0001, 0x1000, 0x5000):
            ids.append(base + item)
    return ids


def scan(fl) -> dict:
    found: dict[str, int] = {}
    ids = id_space()
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        r = fl.inject(SCAN % {"ids": repr(chunk)}, timeout=20)
        if r.ok and isinstance(r.value, dict):
            found.update(r.value)
        elif not r.ok:
            print(f"  batch at {i} failed: {r.error}", file=sys.stderr)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", help="file to write the snapshot to")
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    args = ap.parse_args()

    if args.diff:
        before = json.loads(Path(args.diff[0]).read_text())
        after = json.loads(Path(args.diff[1]).read_text())
        keys = set(before) | set(after)
        changed = [(k, before.get(k), after.get(k)) for k in sorted(keys, key=int)
                   if before.get(k) != after.get(k)]
        if not changed:
            print("nothing changed in the scanned id space")
            print("the clip lives outside it, or clips are not on the REC bus")
            return 1
        print(f"{len(changed)} ids changed:")
        for k, b, a in changed:
            print(f"  {int(k):#010x}  {b}  ->  {a}")
        return 0

    fl = agentfl.connect()
    try:
        found = scan(fl)
    finally:
        fl.close()

    print(f"{len(found)} non-zero ids")
    for k in sorted(found, key=int)[:40]:
        print(f"  {int(k):#010x}  {found[k]}")
    if args.out:
        Path(args.out).write_text(json.dumps(found, indent=2))
        print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
