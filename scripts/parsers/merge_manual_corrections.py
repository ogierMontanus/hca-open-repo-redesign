#!/usr/bin/env python3
"""
merge_manual_corrections.py
-------------------------------
Three-way merge of the manually corrected register against the machine
OCR pass, both of which branched from the same base.

    base    data/curated/personregister_xi_review_full.tsv          (10.079)
    branch A data/curated/personregister_xi_review_full_ocr_refined.tsv
             -- machine: J6sika->Jósika, 6 regenerated 05_sort_key
    branch B data/curated/personregister_xi_review_full_2026-09-05-manual-corrections.csv
             -- manual: 14 rows edited, 9 "B" split rows, 2 splits that
                landed on a duplicate id, 1 row deleted

Branch B is authoritative for content: it is hand-checked editorial work.
Branch A only contributes to rows B never touched, so nothing manual is
overwritten.

05_sort_key is NOT authoritative anywhere -- it is defined as
    f"{surname}, {given_names}"
by parse_personregister_xi.py:sort_key(). It is therefore regenerated from
the merged name fields at the end rather than merged, which also resolves
the two apparent A/B conflicts (PerXI01219, PerXI01920) without a
judgement call: take B's name fields, derive the key.

Structural repairs applied (all reported):
  * the 2 split rows that reused their parent's id get the "B" suffix the
    other 9 already use;
  * one malformed 11_references_parsed;
  * "loannou" -> "Ioannou" (lowercase L for capital I).

Deliberately NOT touched -- these need a human decision, see the report:
  * the Ioannou/Insinger pair that is now duplicated;
  * the 929-row parallel alphabet in PerXI00001-00929.

    python scripts/parsers/merge_manual_corrections.py            # report
    python scripts/parsers/merge_manual_corrections.py --apply
"""
import argparse
import csv
import os
import re
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CUR = os.path.join(ROOT, "data", "curated")
BASE = os.path.join(CUR, "personregister_xi_review_full.tsv")
BRANCH_A = os.path.join(CUR, "personregister_xi_review_full_ocr_refined.tsv")
BRANCH_B = os.path.join(CUR, "personregister_xi_review_full_2026-09-05-manual-corrections.csv")
OUT = os.path.join(CUR, "personregister_xi_merged_2026-09-06.tsv")

# Splits the manual pass made that landed on the parent's id instead of
# taking the "B" suffix used by the other nine. Value = surname of the row
# that should be renamed (the second occurrence), so the rename cannot hit
# the wrong one if row order ever changes.
DUP_ID_SPLITS = {
    "PerXI02349": "Caralis (Pseud.)",
    "PerXI04955": "loannou",
}

# field -> {entry_id: (expected_wrong_value, corrected_value)}
DEFECT_FIXES = {
    "11_references_parsed": {
        "PerXI04955": ("VII:47;VII:54VII:X:133", "VII:47;VII:54;X:133"),
    },
    "03_surname": {
        # capital I misread as lowercase l -- the same OCR family already
        # documented in the 2026-09-05 scan.
        "PerXI04955B": ("loannou", "Ioannou"),
    },
}

REF_OK = re.compile(r"^(?:(?:I{1,3}|IV|VI{0,3}|IX|X):\d+)(?:;(?:I{1,3}|IV|VI{0,3}|IX|X):\d+)*$")

# A page-reference run sitting inside 04_given_names means the entry is
# still fused with the one after it -- the manual split trimmed some
# fields but not this one. Regenerating 05_sort_key from such a row would
# pull the fused text back into a key the manual pass had already cleaned
# (PerXI01608 is exactly that case), so those rows keep their hand-set key
# and are reported instead.
FUSED_GIVEN = re.compile(r"(?:I{1,3}|IV|VI{0,3}|IX|X)\s\d+")


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def sort_key(row):
    """The register's own derived key -- see parse_personregister_xi.py."""
    base = f"{row['03_surname'].strip()}, {row['04_given_names'].strip()}"
    return base.strip().rstrip(",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    base = load(BASE)
    a_rows = load(BRANCH_A)
    b_rows = load(BRANCH_B)
    fields = list(base[0].keys())

    base_by = {r["01_entry_id"]: r for r in base}
    a_by = {r["01_entry_id"]: r for r in a_rows}

    merged = [dict(r) for r in b_rows]

    # ---- 1. give the two reused ids the "B" suffix -----------------
    seen = Counter()
    renamed = []
    for r in merged:
        eid = r["01_entry_id"]
        seen[eid] += 1
        want = DUP_ID_SPLITS.get(eid)
        if want and seen[eid] > 1:
            if r["03_surname"].strip() != want:
                raise SystemExit(
                    f"refusing to rename {eid}: expected second row surname "
                    f"{want!r}, found {r['03_surname']!r}")
            r["01_entry_id"] = eid + "B"
            renamed.append((eid, r["01_entry_id"], want))

    # ---- 2. targeted defect repairs --------------------------------
    fixed = []
    for col, per_id in DEFECT_FIXES.items():
        for eid, (want_old, new) in per_id.items():
            hits = [r for r in merged if r["01_entry_id"] == eid]
            if len(hits) != 1:
                raise SystemExit(f"{eid}: expected 1 row, found {len(hits)}")
            r = hits[0]
            if r[col].strip() != want_old:
                raise SystemExit(
                    f"{eid}.{col}: expected {want_old!r}, found {r[col]!r} "
                    "-- the row changed, re-check the fix")
            r[col] = new
            fixed.append((eid, col, want_old, new))

    # ---- 3. branch A fixes, only where B left the row alone ---------
    def differs(x, y):
        return {c for c in fields if (x.get(c) or "").strip() != (y.get(c) or "").strip()}

    b_touched = set()
    for r in merged:
        eid = r["01_entry_id"]
        o = base_by.get(eid)
        if o and differs(r, o):
            b_touched.add(eid)

    applied_a, skipped_a = [], []
    for eid, a in a_by.items():
        o = base_by.get(eid)
        if not o:
            continue
        cols = differs(a, o)
        if not cols:
            continue
        rows_here = [r for r in merged if r["01_entry_id"] == eid]
        if not rows_here:
            skipped_a.append((eid, sorted(cols), "row absent from manual pass"))
            continue
        r = rows_here[0]
        for c in sorted(cols):
            if c == "05_sort_key":
                continue  # regenerated below; never merged
            if eid in b_touched and (r.get(c) or "").strip() != (o.get(c) or "").strip():
                skipped_a.append((eid, [c], f"manual pass set it to {r[c]!r}"))
                continue
            before = r[c]
            r[c] = a[c]
            applied_a.append((eid, c, before, a[c]))

    # ---- 4. regenerate the derived sort key ------------------------
    resorted, held_back = [], []
    for r in merged:
        want = sort_key(r)
        if r["05_sort_key"].strip() == want:
            continue
        if FUSED_GIVEN.search(r["04_given_names"]):
            held_back.append((r["01_entry_id"], r["04_given_names"], r["05_sort_key"]))
            continue
        resorted.append((r["01_entry_id"], r["05_sort_key"], want))
        r["05_sort_key"] = want

    # ---- 5. validate ------------------------------------------------
    ids = Counter(r["01_entry_id"] for r in merged)
    dupes = {k: v for k, v in ids.items() if v > 1}
    bad_refs = [r["01_entry_id"] for r in merged
                if r["11_references_parsed"].strip()
                and not REF_OK.match(r["11_references_parsed"].strip())]

    # ---- report -----------------------------------------------------
    print(f"base {len(base)}  branchA {len(a_rows)}  branchB {len(b_rows)}  -> merged {len(merged)}")
    print(f"\n1. reused ids given the B suffix: {len(renamed)}")
    for old, new, sur in renamed:
        print(f"     {old} -> {new}  ({sur})")
    print(f"\n2. targeted defect repairs: {len(fixed)}")
    for eid, col, o, n in fixed:
        print(f"     {eid}.{col}: {o!r} -> {n!r}")
    print(f"\n3. branch-A fixes applied: {len(applied_a)}")
    for eid, c, o, n in applied_a:
        print(f"     {eid}.{c}: {o!r} -> {n!r}")
    print(f"   branch-A fixes skipped (manual pass wins): {len(skipped_a)}")
    for eid, cols, why in skipped_a:
        print(f"     {eid} {cols}: {why}")
    print(f"\n4. 05_sort_key regenerated: {len(resorted)}")
    for eid, o, n in resorted[:25]:
        print(f"     {eid}: {o[:56]!r} -> {n[:56]!r}")
    if len(resorted) > 25:
        print(f"     ... and {len(resorted)-25} more")
    print("")
    print(f"   sort_key held back -- 04_given_names still fused: {len(held_back)}")
    for eid, giv, key in held_back:
        print(f"     {eid}: given_names={giv[:62]!r}")
        print(f"     {'':>14} kept sort_key={key[:62]!r}")

    print(f"\n5. validation")
    print(f"     duplicate ids  : {len(dupes)} {dupes if dupes else '(OK)'}")
    print(f"     malformed refs : {len(bad_refs)} {bad_refs if bad_refs else '(OK)'}")

    if not args.apply:
        print("\n(dry run -- rerun with --apply to write)")
        return 0
    if dupes or bad_refs:
        raise SystemExit("refusing to write: validation failed")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(merged)
    print(f"\nwrote {os.path.relpath(OUT, ROOT)} ({len(merged)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
