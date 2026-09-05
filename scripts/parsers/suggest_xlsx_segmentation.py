#!/usr/bin/env python3
"""
suggest_xlsx_segmentation.py
------------------------------
Finds rows in data/parsed/personregister_xi_parsed.tsv whose 13_raw_text
has an unbalanced parenthesis count -- the tell-tale sign of a splitter
miss where a name-head match landed one entry early or late, fusing two
(or leaving one) entries together (e.g. "Caesar, W. H. (1795-1872),
dansk Konsul i Bremen). II 310 391. III 16 191. D. Daa, Gregers (1658-
1712), ..." -- the trailing stray ")" after "Bremen" belongs to no "("
in this row at all; it is what is left of a lost split boundary between
Caesar and Daa.

For each such row, looks up every xlsx DimPer entry sharing its surname
(diacritic-normalized) and prints them alongside the row's raw text, so
a human can read off the correct segmentation directly from xlsx's
already-correct, already-split titles -- xlsx does not suffer from this
class of error since it was keyed and split by hand, not derived from
running column-reflow OCR text through a splitter regex.

This is a REPORTING tool only. It suggests segmentations; it does not
rewrite personregister_xi_parsed.tsv. Some flagged rows turn out to be a
defect already present in xlsx's own source text too (e.g.
"Schimmelmann, Heinrich, Lensgreve 1724-82)" is missing its opening
parenthesis in xlsx as well) -- those are noted as NOT fixable via xlsx
comparison, since xlsx carries the same defect.

Run from the repo root, AFTER fix_diacritics_from_xlsx.py:
  python scripts/parsers/suggest_xlsx_segmentation.py
"""
import csv
import os
import re
import unicodedata

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
XLSX_PATH = os.path.join(ROOT, "data", "raw", "HCA REPOSITORY V0.92", "PersonData-PQ-V0.92.xlsx")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_paren_segmentation_review.tsv")


def strip_diacritics(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c))


def xl_surname(title: str) -> str:
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(title))
    return t.split(",")[0].strip()


def paren_balance(s: str) -> int:
    return s.count("(") - s.count(")")


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]

    xl_by_surname = {}
    xl_defect_surnames = set()
    for d in dim:
        pid, title, desc, birth, death = d
        surname = xl_surname(title)
        key = strip_diacritics(surname).lower()
        xl_by_surname.setdefault(key, []).append((title, desc or ""))
        if paren_balance(str(title)) != 0 or paren_balance(str(desc) if desc else "") != 0:
            xl_defect_surnames.add(key)

    flagged = [r for r in rows if paren_balance(r["13_raw_text"]) != 0]
    print(f"rows with unbalanced parens in 13_raw_text: {len(flagged)}")
    print()

    out_rows = []
    for r in flagged:
        key = strip_diacritics(r["03_surname"]).lower()
        xl_entries = xl_by_surname.get(key, [])
        also_in_xlsx = key in xl_defect_surnames
        note = (
            "DEFECT ALSO IN XLSX -- not fixable via xlsx comparison, leave as known source defect"
            if also_in_xlsx else
            "xlsx segmentation looks clean -- use titles below to resegment this row"
        )
        print(f"=== {r['01_entry_id']} | {r['03_surname']} | {note}")
        print(f"  MINE: {r['13_raw_text'][:160]}")
        for title, desc in xl_entries:
            print(f"  XLSX: {title}  ||  {desc[:80]}")
        print()

        out_rows.append({
            "entry_id": r["01_entry_id"],
            "surname": r["03_surname"],
            "also_defect_in_xlsx": "yes" if also_in_xlsx else "no",
            "mine_raw_text": r["13_raw_text"],
            "xlsx_titles_same_surname": " | ".join(t for t, _ in xl_entries),
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "entry_id", "surname", "also_defect_in_xlsx", "mine_raw_text", "xlsx_titles_same_surname",
        ], delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}  ({len(out_rows)} rows)")


if __name__ == "__main__":
    main()
