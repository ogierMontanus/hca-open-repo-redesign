#!/usr/bin/env python3
"""
check_label_corruption.py — find labels damaged by a global find-and-replace.

`data/normalized/entities.csv` contains 18 labels in which the letters "wor"
have been replaced by "Pag":

    Festen paa KenilPagth        ->  Festen paa Kenilworth   (W. Scott)
    Household Pagds              ->  Household words         (Dickens)
    Journey to Angora (William AinsPagth)   ->  Ainsworth
    Einige Pagte über Pferdezucht           ->  Einige worte
    Om Holger-Danske-Sagnet (Pauline Pagm)  ->  Pauline worm

That is not OCR. OCR does not turn three letters into a different three
letters consistently, in the middle of words, across unrelated entries. It is
a substitution that was meant to hit something else — most likely the `Pag…`
page-handle prefix — and ran over the label text on its way past.

The damage is in the V0.82 workbook, so it is upstream of this repository and
shows on the live site today. V0.94's work registry does not have it, which is
how it was noticed: the corrupted entries are among the handful that fail to
crosswalk between the two.

**Nothing is repaired here.** The corrected spelling is obvious in every case,
but the fix belongs in the workbook — correcting it downstream would leave the
source wrong and silently diverge the two. The list is written out so someone
can fix it where it lives.

Usage:
    python scripts/validation/check_label_corruption.py
    python scripts/validation/check_label_corruption.py --write
"""

import argparse
import csv
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "data" / "normalized" / "entities.csv"
OUT = ROOT / "data" / "review" / "label_corruption.csv"

# "Pag" sitting against letters is never a page handle: a real one is
# "Pag010003", digits only, and always stands alone.
EMBEDDED_PAG = re.compile(r"[a-zæøåA-ZÆØÅ]Pag|Pag[a-zæøå]")

# …but it IS how several perfectly good names begin. The pattern above matches
# 24 labels, of which 6 are real people and one real place. There is no
# mechanical way to tell "Pagds" (words) from "Pagani" (a surname) — the test
# is whether replacing Pag with wor yields a word, and that is a judgement.
# So the six are named here rather than guessed at, and anything new that
# starts with Pag will show up as a finding for a human to add or fix.
LEGITIMATE = {
    "Pagani", "Paganini", "Paget", "Pagh", "Pagliani-Gagliardi",
}


def is_legitimate(label: str) -> bool:
    first = re.split(r"[,\s(]", (label or "").strip(), maxsplit=1)[0]
    return first in LEGITIMATE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    hits = []
    with ENTITIES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            for field in ("label", "description"):
                v = r.get(field) or ""
                if EMBEDDED_PAG.search(v) and not is_legitimate(v):
                    hits.append({
                        "entity_id": r["entity_id"],
                        "entity_type": r["entity_type"],
                        "field": field,
                        "current": v.replace("\n", " ")[:160],
                        "suggested": v.replace("Pag", "wor").replace("\n", " ")[:160],
                    })

    print(f"  labels damaged by a wor -> Pag substitution: {len(hits)}")
    print(f"     (real Pag- names excluded by name: {', '.join(sorted(LEGITIMATE))})")
    by_type = {}
    for h in hits:
        by_type[h["entity_type"]] = by_type.get(h["entity_type"], 0) + 1
    print(f"     by entity type: {by_type}")
    for h in hits[:8]:
        print(f"     {h['entity_id']}  {h['current'][:52]}")
        print(f"     {'':>12}  -> {h['suggested'][:52]}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["entity_id", "entity_type", "field",
                                              "current", "suggested"])
            w.writeheader()
            w.writerows(hits)
        print(f"\n  wrote {OUT.relative_to(ROOT)}")

    print("\n  Not repaired. The damage is in the source workbook; fixing it "
          "here\n  would leave the source wrong and diverge the two.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
