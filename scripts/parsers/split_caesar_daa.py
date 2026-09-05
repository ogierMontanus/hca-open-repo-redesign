#!/usr/bin/env python3
"""
One-off split of the fused Caesar/Daa row in
data/parsed/personregister_xi_parsed.tsv, confirmed against xlsx DimPer
(which has clean separate "Caesar, W. H. (1795-1872)" and "Daa, Gregers
(1658-1712)" entries). The splitter fused them at "Bremen). II 310 391.
III 16 191. D. Daa, Gregers ..." because the name-head pattern for "Daa,
Gregers" wasn't recognised right after a reference list ending in a
lone initial ("D.").

Run from the repo root, AFTER fix_diacritics_from_xlsx.py:
  python scripts/parsers/split_caesar_daa.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    target = [r for r in rows if r["03_surname"] == "Caesar" and "Daa, Gregers" in r["13_raw_text"]]
    if len(target) != 1:
        raise SystemExit(f"expected exactly 1 target row, found {len(target)}")
    old = target[0]

    caesar = {k: "" for k in fieldnames}
    caesar.update({
        "02_entry_type": "standardpost",
        "03_surname": "Caesar",
        "04_given_names": "W. H.",
        "05_sort_key": "Caesar, W. H.",
        "06_birth_year": "1795",
        "07_death_year": "1872",
        "09_description": "dansk Konsul i Bremen.",
        "10_references_raw": "II 310 391. III 16 191.",
        "11_references_parsed": "II:310;II:391;III:16;III:191",
        "13_raw_text": "Caesar, W. H. (1795-1872), dansk Konsul i Bremen. II 310 391. III 16 191.",
    })

    daa = {k: "" for k in fieldnames}
    daa.update({
        "02_entry_type": "standardpost",
        "03_surname": "Daa",
        "04_given_names": "Gregers",
        "05_sort_key": "Daa, Gregers",
        "06_birth_year": "1658",
        "07_death_year": "1712",
        "09_description": "Søn af Valdemar D., Generalmajor.",
        "10_references_raw": "IV 363.",
        "11_references_parsed": "IV:363",
        "13_raw_text": "Daa, Gregers (1658-1712), Søn af Valdemar D., Generalmajor. IV 363.",
    })

    out = []
    for r in rows:
        if r is old:
            out.append(caesar)
            out.append(daa)
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
