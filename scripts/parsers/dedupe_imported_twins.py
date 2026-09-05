#!/usr/bin/env python3
"""
dedupe_imported_twins.py
----------------------------
Removes the duplicate rows created by import_reference_missing_candidates.py.

That import decided a reference person was "missing" by comparing NAME
TEXT. Wherever our row had an empty given-name field, or spelled the
name differently from the reference, the comparison failed and the
reference person was imported -- producing a second row for someone we
already had. 393 such twins exist.

A pair is only treated as the same person when it agrees on all of:
surname (diacritic-insensitive), the COMPLETE set of volume:page
references, and both year fields. Page references are the
transcription-stable identifier, so full-signature equality is strong
evidence; requiring the years to agree as well guards against two
relatives who happen to be cited on exactly the same pages.

Which copy survives, in order:
  1. the one with more non-empty fields (more complete);
  2. on a tie, the one with the longer description;
  3. on a tie, the ORIGINAL row rather than the import -- our OCR is
     right where the reference has its own systematic errors (it reads
     "Gornelis" for "Cornelis", "G. G. J." for "C. C. J.").
Any field the losing row has and the winner lacks is copied over first,
so nothing the import contributed is thrown away.

  python scripts/parsers/dedupe_imported_twins.py
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")

MERGE_FIELDS = (
    "04_given_names", "06_birth_year", "07_death_year", "08_year_note",
    "09_description", "10_references_raw", "11_references_parsed", "12_see_also",
)


def norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def filled(row) -> int:
    return sum(1 for k, v in row.items() if v.strip())


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    order = {id(r): i for i, r in enumerate(rows)}

    groups = defaultdict(list)
    for r in rows:
        if r["02_entry_type"] != "standardpost":
            continue
        sig = tuple(sorted(x for x in r["11_references_parsed"].split(";") if x))
        if not sig:
            continue
        groups[(norm(r["03_surname"]), sig, r["06_birth_year"], r["07_death_year"])].append(r)

    drop = set()
    merged = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        winner = sorted(
            members,
            key=lambda r: (-filled(r), -len(r["09_description"]), order[id(r)]),
        )[0]
        for other in members:
            if other is winner:
                continue
            for fld in MERGE_FIELDS:
                if not winner[fld].strip() and other[fld].strip():
                    winner[fld] = other[fld]
                    merged += 1
            drop.add(id(other))
        winner["05_sort_key"] = (
            f"{winner['03_surname']}, {winner['04_given_names']}".strip().rstrip(",")
        )

    out = [r for r in rows if id(r) not in drop]
    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"duplicate groups merged : {sum(1 for m in groups.values() if len(m) > 1)}")
    print(f"rows removed            : {len(drop)}")
    print(f"fields filled from twin  : {merged}")
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
