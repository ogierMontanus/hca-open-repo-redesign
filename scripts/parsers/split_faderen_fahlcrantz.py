#!/usr/bin/env python3
"""
One-off split of the fused "Faderen, se: ... Fahlcrantz, ..." row in
data/parsed/personregister_xi_parsed.tsv into its two real entries:
a cross-reference ("Faderen, se: Collin, Jonas d. Æ.") and a standardpost
for Fahlcrantz, Christian Erich. The splitter missed this boundary
because the "se:"-target ends mid-sentence at a name that itself has no
comma before the year-parenthesis pattern the splitter expects there.

Run from the repo root, AFTER fix_diacritics_from_xlsx.py:
  python scripts/parsers/split_faderen_fahlcrantz.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    target = [r for r in rows if r["03_surname"] == "Faderen"]
    if len(target) != 1:
        raise SystemExit(f"expected exactly 1 'Faderen' row, found {len(target)}")
    old = target[0]
    assert "Fahlcrantz" in old["04_given_names"], old["04_given_names"]

    crossref = {k: "" for k in fieldnames}
    crossref.update({
        "02_entry_type": "krydshenvisning",
        "03_surname": "Faderen",
        "05_sort_key": "Faderen",
        "12_see_also": "Collin, Jonas d. Æ.",
        "13_raw_text": "Faderen, se: Collin, Jonas d. Æ.",
    })

    standardpost = {k: "" for k in fieldnames}
    standardpost.update({
        "02_entry_type": "standardpost",
        "03_surname": "Fahlcrantz",
        "04_given_names": "Christian Erich",
        "05_sort_key": "Fahlcrantz, Christian Erich",
        "06_birth_year": old["06_birth_year"],
        "07_death_year": old["07_death_year"],
        "08_year_note": old["08_year_note"],
        "09_description": old["09_description"],
        "10_references_raw": old["10_references_raw"],
        "11_references_parsed": old["11_references_parsed"],
        "13_raw_text": (
            f"Fahlcrantz, Christian Erich ({old['06_birth_year']}-{old['07_death_year']}), "
            f"{old['09_description']} {old['10_references_raw']}"
        ),
    })

    out = []
    for r in rows:
        if r is old:
            out.append(crossref)
            out.append(standardpost)
        else:
            out.append(r)

    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    assert len(out) == len(rows) + 1

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"wrote {len(out)} rows (was {len(rows)})")


if __name__ == "__main__":
    main()
