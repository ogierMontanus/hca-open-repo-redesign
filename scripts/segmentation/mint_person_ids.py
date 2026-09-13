#!/usr/bin/env python3
"""
mint_person_ids.py — give every person-register entry a stable identifier.

`01_entry_id` is a row number. It is assigned positionally at parse time, so
it renumbers whenever a row is inserted: `PerXI00001` is "Åberg" in a fresh
parse and "Abbott" in the committed file, and `PerXI05000` is two different
people. The project knew this in outline — `apply_person_emendations.py` gives
"01_entry_id renumbers" as a reason emendations are layered over the register
rather than edited into it — but nothing downstream could rely on an identity,
and the migration's person adoption needs one to crosswalk against.

This writes `00_person_id` (`HCAP00001`, …) as the first column.

Assigned once, then carried
---------------------------
The id is **not derived from content** and is never recomputed. A
content-derived id changes when a typo is fixed, which breaks every citation
to it — the defect this repository already objects to in V0.94's place ids,
where `OLDLocationID` consequently reaches nothing.

So: rows that already carry an id keep it, untouched, no matter how their
content changes. Only rows without one are assigned, from the next free
number. The script is idempotent, and **it will not renumber** — if that is
ever wanted it has to be done deliberately, by hand, with the crosswalk
rebuilt.

The column is committed, so git is its backup. `--verify` checks the
invariants without writing.

Usage:
    python scripts/segmentation/mint_person_ids.py --verify
    python scripts/segmentation/mint_person_ids.py
"""

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
ID_COL = "00_person_id"
PREFIX = "HCAP"
WIDTH = 5


def load(path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return list(r), list(r.fieldnames or [])


def next_number(rows) -> int:
    used = [r[ID_COL] for r in rows if r.get(ID_COL)]
    if not used:
        return 1
    nums = [int(u[len(PREFIX):]) for u in used
            if u.startswith(PREFIX) and u[len(PREFIX):].isdigit()]
    return max(nums, default=0) + 1


def verify(rows) -> int:
    problems = 0
    have = [r for r in rows if r.get(ID_COL)]
    print(f"  rows            {len(rows):,}")
    print(f"  with an id      {len(have):,}")
    missing = len(rows) - len(have)
    if missing:
        print(f"  MISSING an id   {missing:,}")
        problems += 1
    dupes = [i for i, n in Counter(r[ID_COL] for r in have).items() if n > 1]
    if dupes:
        print(f"  DUPLICATE ids   {len(dupes):,}   e.g. {dupes[:5]}")
        problems += 1
    bad = [r[ID_COL] for r in have
           if not (r[ID_COL].startswith(PREFIX)
                   and r[ID_COL][len(PREFIX):].isdigit())]
    if bad:
        print(f"  MALFORMED ids   {len(bad):,}   e.g. {bad[:5]}")
        problems += 1
    if not problems:
        print("  OK — every row has exactly one well-formed, unique id.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--verify", action="store_true",
                    help="check the invariants and exit without writing")
    args = ap.parse_args()

    if not MASTER.exists():
        sys.exit(f"missing {MASTER}")
    rows, fields = load(MASTER)

    if args.verify:
        if ID_COL not in fields:
            print(f"  {ID_COL} column is absent — nothing minted yet.")
            return 1
        return 1 if verify(rows) else 0

    fresh = ID_COL not in fields
    if fresh:
        fields = [ID_COL] + fields
        for r in rows:
            r[ID_COL] = ""

    n = next_number(rows)
    assigned = 0
    for r in rows:
        if r.get(ID_COL):
            continue                      # carried, never reassigned
        r[ID_COL] = f"{PREFIX}{n:0{WIDTH}d}"
        n += 1
        assigned += 1

    if not assigned:
        print("  nothing to do — every row already carries an id.")
        return 0

    backup = MASTER.with_suffix(".tsv.bak")
    shutil.copy2(MASTER, backup)
    tmp = MASTER.with_suffix(".tsv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(MASTER)
    backup.unlink()

    print(f"  {'minted' if fresh else 'filled'} {assigned:,} id(s); "
          f"{len(rows):,} rows now carry one")
    verify(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
