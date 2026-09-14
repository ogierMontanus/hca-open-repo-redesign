#!/usr/bin/env python3
"""
merge_person_references.py — add the segmentation's page references to the live set.

Plan step 10c. The segmented register cites 45,293 person→page references
against `references.csv`'s 39,361, and it is the better data: measured against
the authoritative ten-volume page list it is 16× cleaner (0.03 % invalid
citations against 0.47 %).

This folds the difference in **additively**. The live V0.82 rows stay exactly
as they are and keep their `Reg…` identifiers, so no person URL changes and
nothing can be lost; the segmentation only supplies rows the live set does not
already have. That is what makes the step reversible — dropping the added rows
restores the previous state exactly.

Dry-run by default. `--apply` writes.

What is deliberately NOT merged
-------------------------------
**Run-on entries — but only the ones that really are run-ons.**

27 entries have a citation list left behind in `09_description` as well as one
in `10_references_raw`. A first pass excluded all 27. That was too blunt:
they are two different defects, and only one of them is dangerous.

The register cites volumes in ascending order, which is what tells them apart:

  **Split list** (16 entries, 1,303 refs) — the parser ended the description
  early and put the head of the citation list there, keeping the tail in
  `10_references_raw`. The description's volumes *precede* the raw ones:
  Bournonville, August has "II 33 … VIII …" in the description and "X 2 7 21
  …" in the references. Both halves are his. Checked against the live data,
  every reference these entries add falls in the tail volumes — Baller,
  Sophie gains 24 volume-X references against the 1 the live register has.
  **Admitted.**

  **Run-on** (11 entries, 887 refs) — `10_references_raw` belongs to the
  *following* entry. The volumes go backwards: Scharff, Elvilda has her own
  "X 335 342 384." in the description while the references start at IV, and
  her `13_raw_text` visibly runs on into "Scharff, H…". Merging these would
  attribute hundreds of pages to the wrong person. **Excluded**, and written
  to the review file for the editors.

**Invalid citations.** The 14 references to pages that do not exist — see
`scripts/validation/check_page_references.py`. Never repaired, never merged.

**Uncrosswalked entries.** A register entry with no `Reg…` counterpart has
nowhere to contribute to; 614 references sit behind the 209 unresolved
crosswalk rows.

Usage:
    python scripts/segmentation/merge_person_references.py
    python scripts/segmentation/merge_person_references.py --apply
"""

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
CROSSWALK = ROOT / "data" / "curated" / "person_id_crosswalk.csv"
REFS = ROOT / "data" / "normalized" / "references.csv"
PAGES = ROOT / "data" / "normalized_v094" / "diary_pages.csv"
REVIEW = ROOT / "data" / "review" / "person_reference_merge_review.csv"

# An entry's own citation left behind in the description — "X 335 342 384." —
# means 11_references_parsed was filled from the following entry.
OWN_CITE_IN_DESCRIPTION = re.compile(
    r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\s+\d{1,3}(?:[\s,]+\d{1,3})*\s*\.")
FUSION_REF_FLOOR = 20      # below this the signature is usually a real cross-ref

VOL_NUM = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
           "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11}


VOL_IN_TEXT = re.compile(r"\b(I|II|III|IV|V|VI|VII|VIII|IX|X)\s+\d")


def runs_on_into_next_entry(description: str, references_raw: str) -> bool:
    """True when `references_raw` belongs to the entry AFTER this one.

    The register cites volumes in ascending order. So if the description's
    citations reach volume VIII and the reference list restarts at IV, that
    list is not a continuation of this entry — it is the next person's.

    This is what separates the 11 genuine run-ons from the 16 entries whose
    citation list the parser merely split in two. Excluding all 27, as a
    first pass did, threw away 1,303 valid references.
    """
    dv = [VOL_NUM[m.group(1)] for m in VOL_IN_TEXT.finditer(description or "")]
    rv = [VOL_NUM[m.group(1)] for m in VOL_IN_TEXT.finditer(references_raw or "")]
    if not dv or not rv:
        return False
    return max(dv) > min(rv)


def page_id(vol, page):
    return f"Pag{VOL_NUM.get(vol, 0):02d}{int(page):04d}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--apply", action="store_true", help="write references.csv")
    args = ap.parse_args()

    valid = set()
    with PAGES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            valid.add((r["vol"].strip(), int(r["page"])))

    walk = {}
    with CROSSWALK.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["reg_id"]:
                walk[r["person_id"]] = r["reg_id"]

    with REFS.open(encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        live = list(rdr)
        fields = list(rdr.fieldnames)
    have = defaultdict(set)
    max_seq = defaultdict(int)
    label = {}
    for r in live:
        if r["page"].strip().isdigit():
            have[r["entity_id"]].add((r["vol"].strip(), int(r["page"])))
        label.setdefault(r["entity_id"], r["entity_label"])
        try:
            max_seq[r["page_id"]] = max(max_seq[r["page_id"]], int(r["seq"]))
        except (ValueError, KeyError):
            pass

    with MASTER.open(encoding="utf-8", newline="") as f:
        master = list(csv.DictReader(f, delimiter="\t"))

    new_rows, review = [], []
    stats = defaultdict(int)
    gained = set()

    for m in master:
        pid = m.get("00_person_id", "")
        name = f"{m.get('03_surname','')}, {m.get('04_given_names','')}".strip(", ")
        refs = [t.strip() for t in (m.get("11_references_parsed") or "").split(";") if t.strip()]
        if not refs:
            continue

        if (len(refs) > FUSION_REF_FLOOR
                and OWN_CITE_IN_DESCRIPTION.search(m.get("09_description") or "")):
            if runs_on_into_next_entry(m.get("09_description") or "",
                                       m.get("10_references_raw") or ""):
                stats["excluded: run-on into next entry"] += len(refs)
                review.append({"person_id": pid, "name": name,
                               "reason": "run-on into next entry", "n_refs": len(refs),
                               "detail": (m.get("09_description") or "")[:120]})
                continue
            stats["admitted: split citation list"] += len(refs)

        reg = walk.get(pid)
        if not reg:
            stats["excluded: no crosswalk"] += len(refs)
            continue

        for tok in refs:
            vol, _, page = tok.rpartition(":")
            vol, page = vol.strip(), page.strip()
            if not page.isdigit() or (vol, int(page)) not in valid:
                stats["excluded: invalid page"] += 1
                continue
            if (vol, int(page)) in have[reg]:
                stats["already present"] += 1
                continue
            have[reg].add((vol, int(page)))
            pg = page_id(vol, page)
            max_seq[pg] += 1
            new_rows.append({"page_id": pg, "entity_id": reg,
                             "entity_label": label.get(reg, name),
                             "vol": vol, "page": page, "seq": max_seq[pg]})
            gained.add(reg)
            stats["ADDED"] += 1

    print(f"  live references.csv          {len(live):,} rows")
    for k in sorted(stats, key=lambda k: -stats[k]):
        print(f"     {k:<26} {stats[k]:>7,}")
    print(f"  persons gaining references   {len(gained):,}")
    print(f"  references.csv would become  {len(live) + len(new_rows):,} rows "
          f"(+{len(new_rows)/len(live)*100:.1f} %)")

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["person_id", "name", "reason", "n_refs", "detail"])
        w.writeheader(); w.writerows(review)
    print(f"  wrote {REVIEW.relative_to(ROOT)}  ({len(review):,} excluded entries)")

    if not args.apply:
        print("\n  dry run — nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(REFS, REFS.with_suffix(".csv.bak"))
    # Append, never re-sort. Sorting the whole file would move rows that this
    # step promised not to touch, and it does have an effect: the first
    # attempt re-ordered one place's visit list in web/data/places_visits.json
    # for no reason at all. Appending keeps the diff reviewable — every
    # pre-existing line stays on its line — and keeps "additive" true of the
    # file as well as of the data.
    merged = live + new_rows
    with REFS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(merged)
    REFS.with_suffix(".csv.bak").unlink()
    print(f"\n  wrote {REFS.relative_to(ROOT)}  ({len(merged):,} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
