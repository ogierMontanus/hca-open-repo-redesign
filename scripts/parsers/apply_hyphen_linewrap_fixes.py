#!/usr/bin/env python3
"""
apply_hyphen_linewrap_fixes.py
--------------------------------
Applies the 'join_linewrap' fixes from
data/curated/ocr_hyphen_linewrap_candidates.tsv to
data/parsed/personregister_xi_parsed.tsv: each is a line-wrap hyphen
artifact ("Gottholdi- ne" -> "Gottholdine") in 03_surname, 04_given_names
or 09_description. The 'remove_space_keep_hyphen' rows (real hyphenated
compounds like "tysk- svensk") are intentionally NOT applied here -- they
need the space removed but the hyphen kept, a different edit, and there
are only 5 of them.

05_sort_key is rebuilt from the (now-fixed) 03_surname/04_given_names.
13_raw_text is patched with the same substring replacement as the
source field, since it always contains the identical matched span
verbatim (it is the pre-split raw OCR text the other fields were
parsed out of).

Run from the repo root, AFTER fix_diacritics_from_xlsx.py:
  python scripts/parsers/apply_hyphen_linewrap_fixes.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
CANDIDATES_TSV = os.path.join(ROOT, "data", "curated", "ocr_hyphen_linewrap_candidates.tsv")


def rebuild_sort_key(r):
    return f"{r['03_surname']}, {r['04_given_names']}".strip().rstrip(",")


def main():
    with open(CANDIDATES_TSV, encoding="utf-8") as f:
        candidates = [c for c in csv.DictReader(f, delimiter="\t") if c["fix_type"] == "join_linewrap"]

    by_entry_field = {}
    for c in candidates:
        by_entry_field.setdefault((c["entry_id"], c["field"]), []).append((c["matched"], c["proposed_fix"]))

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    applied = 0
    for r in rows:
        touched = False
        for field in ("03_surname", "04_given_names", "09_description"):
            fixes = by_entry_field.get((r["01_entry_id"], field))
            if not fixes:
                continue
            text = r[field]
            for matched, fixed in fixes:
                if matched in text:
                    text = text.replace(matched, fixed, 1)
                    r["13_raw_text"] = r["13_raw_text"].replace(matched, fixed, 1)
                    applied += 1
                    touched = True
            r[field] = text
        if touched:
            r["05_sort_key"] = rebuild_sort_key(r)

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"applied {applied} join fixes across {len(rows)} rows")


if __name__ == "__main__":
    main()
