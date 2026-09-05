#!/usr/bin/env python3
"""
merge_dash_subentry_duplicates.py
-------------------------------------
The register writes a relative with no name of their own as a dash
sub-entry under the person before them:

    Rosen, Alfred von (1825-1912), svensk Kammerherre. X 66.
    — Hans Smaapiger, 1873 (Sophie (f. 1861), Benedicte (f. 1863) …). X 67.

The parse captured each such line TWICE:

  * as an `underpost` in the right place, carrying the parent's headword
    and the register's own wording -- this is the correct row;
  * as a spurious standalone `standardpost` whose 03_surname is the
    literal dash text ("- Hans Smaapiger"), which alphabetises to the very
    top of the file, far from the person it belongs to.

All 15 dash rows match an underpost on reference signature, so the
duplication is exact. This script drops the dash rows and keeps the
underposts, which already sort under the parent's surname -- what the
dash rows were asked to do.

Before dropping, the parent is written into the underpost's 12_see_also.
13 of the 17 underposts have empty 04_given_names, so "Butenschön" alone
does not say WHICH Butenschön; the link makes it explicit. It is taken
from the preceding row in the file -- the actual parent -- rather than
from the dash row's own see_also, which came from the reference
transcription and spells some names differently (Butenschøn/Butenschön,
Terán/Terån).

  python scripts/parsers/merge_dash_subentry_duplicates.py          # report
  python scripts/parsers/merge_dash_subentry_duplicates.py --apply
"""
import argparse
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")

DASHES = ("-", "–", "—")


def parent_name(rows, i):
    """Full name of the row above -- an underpost always follows its parent."""
    if i == 0:
        return ""
    p = rows[i - 1]
    return f"{p['03_surname'].strip()}, {p['04_given_names'].strip()}".strip().rstrip(",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    by_refs = {}
    for i, r in enumerate(rows):
        if r["02_entry_type"] == "underpost" and r["11_references_parsed"]:
            by_refs.setdefault(r["11_references_parsed"], []).append(i)

    drop, linked, unmatched = [], 0, []
    for i, r in enumerate(rows):
        if not r["03_surname"].lstrip().startswith(DASHES):
            continue
        twins = by_refs.get(r["11_references_parsed"], [])
        if len(twins) != 1:
            unmatched.append((r, f"{len(twins)} underposter med samme henvisninger"))
            continue
        drop.append(i)

    # Give every underpost an explicit parent link, not just the ones that
    # had a dash twin.
    for i, r in enumerate(rows):
        if r["02_entry_type"] != "underpost" or r["12_see_also"].strip():
            continue
        name = parent_name(rows, i)
        if name:
            r["12_see_also"] = name
            linked += 1

    print(f"dash-rækker fundet      : {len(drop) + len(unmatched)}")
    print(f"  dubletter der fjernes : {len(drop)}")
    print(f"  uden entydig underpost: {len(unmatched)}")
    for r, why in unmatched:
        print(f"    [!] {r['01_entry_id']} {r['03_surname']}: {why}")
    print(f"underposter der får 12_see_also: {linked}")

    if not args.apply:
        return

    dropset = set(drop)
    out = [r for i, r in enumerate(rows) if i not in dropset]
    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
