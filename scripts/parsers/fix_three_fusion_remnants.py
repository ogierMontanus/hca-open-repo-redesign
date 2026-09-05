#!/usr/bin/env python3
"""
fix_three_fusion_remnants.py
--------------------------------
Repairs the three rows left with fields scrambled by earlier fusions,
per reviewer instruction.

  Gerdislaw   -- the whole entry sat in 04_given_names. Split into given
                 names, description and page references.
  Gluecksborg -- Christian IX's row carried its page references AND a
                 "Se ogsaa" cross-reference inside 09_description.
                 Split into 10/11 and 12.
  Hansen      -- an unnamed Hansen whose 04_given_names held the whole
                 description plus references, and whose 06/07 years were
                 wrong: 1798-1873 belongs to Grosserer A. N. Hansen, who
                 is only MENTIONED in the parenthetical as a possible
                 identification ("218 maaske = ..."), not to this person.
                 The years are therefore cleared, not moved.

  python scripts/parsers/fix_three_fusion_remnants.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def one(rows, surname, needle):
    hits = [r for r in rows
            if r["03_surname"] == surname
            and (needle in r["04_given_names"] or needle in r["09_description"])]
    if len(hits) != 1:
        raise SystemExit(f"expected 1 row for {surname}/{needle!r}, found {len(hits)}")
    return hits[0]


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    # --- Gerdislaw ---------------------------------------------------
    r = one(rows, "Gerdislaw", "Ubekjendt")
    r["04_given_names"] = "Charlotte von"
    r["05_sort_key"] = "Gerdislaw, Charlotte von"
    r["09_description"] = "tysk Forfatterinde, Rügen (»en Ubekjendt paa Rygen«)"
    r["10_references_raw"] = "V 169."
    r["11_references_parsed"] = "V:169"
    r["13_raw_text"] = (
        "Gerdislaw, Charlotte von, tysk Forfatterinde, Rügen "
        "(»en Ubekjendt paa Rygen«). V 169."
    )

    # --- Glucksborg / Christian IX -----------------------------------
    r = one(rows, "Glücksborg", "Konge af Danmark")
    r["09_description"] = "Broder til Hertug Carl af G., 1863 Konge af Danmark (Christian IX)."
    r["10_references_raw"] = "II 422 424. IV 127."
    r["11_references_parsed"] = "II:422;II:424;IV:127"
    r["12_see_also"] = "Danmark, Christian (IX)"
    r["13_raw_text"] = (
        "Glücksborg, Christian, Prins af Slesvig-Holsten-Sønderborg-G. (1818-1906), "
        "Broder til Hertug Carl af G., 1863 Konge af Danmark (Christian IX). "
        "II 422 424. IV 127. — Se ogsaa: Danmark, Christian (IX)."
    )

    # --- Hansen ------------------------------------------------------
    r = one(rows, "Hansen", "Hambros Firma")
    r["04_given_names"] = ""
    r["05_sort_key"] = "Hansen"
    # 1798-1873 are A. N. Hansen's, named only as a possible match.
    r["06_birth_year"] = ""
    r["07_death_year"] = ""
    r["09_description"] = (
        "London 1847, ansat i Hambros Firma? 218: maaske = Grosserer A. N. Hansen, "
        "231 maaske hans Søn Alfred (se denne))"
    )
    r["10_references_raw"] = "III 218 231."
    r["11_references_parsed"] = "III:218;III:231"
    r["13_raw_text"] = (
        "Hansen, London 1847, ansat i Hambros Firma? III 218 231. "
        "(218 maaske = Grosserer A. N. Hansen (1798-1873), "
        "231 maaske hans Søn Alfred (se denne))."
    )

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print("repaired 3 rows: Gerdislaw, Glücksborg, Hansen")


if __name__ == "__main__":
    main()
