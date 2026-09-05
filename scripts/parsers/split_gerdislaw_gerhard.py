#!/usr/bin/env python3
"""
One-off split of the fused Gerdislaw/Gerhard row in
data/parsed/personregister_xi_parsed.tsv into its two real entries:
"Gerdislaw, Charlotte von, tysk Forfatterinde, Ruegen (...). V 169."
and "Gerhard (Gert) (ca. 1292-1340), holstensk Greve, Hertug af
Soenderjylland. IV 359." The splitter fused them because "Gerhard
(Gert)" immediately follows a page-reference-ending "V 169." without a
name-head pattern the splitter recognised there.

Run from the repo root, AFTER fix_diacritics_from_xlsx.py and the
hyphen/line-wrap fixes:
  python scripts/parsers/split_gerdislaw_gerhard.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    target = [r for r in rows if "Ubekjendt" in r["04_given_names"]]
    if len(target) != 1:
        raise SystemExit(f"expected exactly 1 target row, found {len(target)}")
    old = target[0]

    charlotte_given = (
        "Charlotte von, tysk Forfatterinde, Rügen "
        "(»en Ubekjendt paa Rygen«). V 169."
    )
    charlotte = {k: "" for k in fieldnames}
    charlotte.update({
        "02_entry_type": "standardpost",
        "03_surname": "Gerdislaw",
        "04_given_names": charlotte_given,
        "05_sort_key": f"Gerdislaw, {charlotte_given}",
        "13_raw_text": f"Gerdislaw, {charlotte_given}",
    })

    gerhard = {k: "" for k in fieldnames}
    gerhard.update({
        "02_entry_type": "standardpost",
        "03_surname": "Gerhard",
        "04_given_names": "Gert",
        "05_sort_key": "Gerhard, Gert",
        "06_birth_year": old["06_birth_year"],
        "07_death_year": old["07_death_year"],
        "08_year_note": old["08_year_note"],
        "09_description": old["09_description"],
        "10_references_raw": old["10_references_raw"],
        "11_references_parsed": old["11_references_parsed"],
        "13_raw_text": (
            f"Gerhard (Gert) (ca. {old['06_birth_year']}-{old['07_death_year']}), "
            f"{old['09_description']} {old['10_references_raw']}"
        ),
    })

    out = []
    for r in rows:
        if r is old:
            out.append(charlotte)
            out.append(gerhard)
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
