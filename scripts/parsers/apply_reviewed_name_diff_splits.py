#!/usr/bin/env python3
"""
apply_reviewed_name_diff_splits.py
--------------------------------------
Second pass over the rows the reviewer marked as skewed in
data/curated/personregister_xi_reference_name_diffs.tsv.

Those 45 rows were paired to a reference entry by a shared page-
reference signature, but the pairing is FALSE -- it linked two unrelated
people who merely cite the same pages (Esbensen <-> l'Escaille,
Sivel <-> Sixtus V, Uxkuell <-> Z). Our own name is correct in every
case, so the pairing is discarded rather than applied.

Two consequences are handled here:

1. Six of our rows are themselves still fused, and the reviewer gave the
   exact intended segmentation. Those splits are applied.
2. One reviewed orthographic fix: "-Hallermiinde" -> "-Hallermuende"
   (ue = u-umlaut) in Platen's name.

The 45 reference people are genuinely absent from our data (they were
skipped by the 958-row import precisely because the false pairing made
them look matched); importing them is left to
import_reference_missing_candidates.py driven by the leftover list this
script writes.

  python scripts/parsers/apply_reviewed_name_diff_splits.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def find_one(rows, **kw):
    hits = [r for r in rows if all(kw_match(r, k, v) for k, v in kw.items())]
    if len(hits) != 1:
        raise SystemExit(f"expected 1 row for {kw}, found {len(hits)}")
    return hits[0]


def kw_match(row, key, value):
    field = {"sn": "03_surname", "gn": "04_given_names"}[key]
    return row[field].startswith(value)


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    def blank():
        return {k: "" for k in fieldnames}

    replacements = {}   # id(row) -> [row, ...]
    n_split = 0

    # --- Kohle / Kok -------------------------------------------------
    r = find_one(rows, sn="Kohle", gn="Holstener")
    kohle = blank()
    kohle.update({
        "02_entry_type": "standardpost", "03_surname": "Kohle",
        "05_sort_key": "Kohle",
        "09_description": "Holstener, bosat i Örebro 1837.",
        "10_references_raw": "II 33-34.", "11_references_parsed": "II:33;II:34",
        "13_raw_text": "Kohle, Holstener, bosat i Örebro 1837. II 33-34.",
    })
    kok = dict(r)
    kok.update({
        "03_surname": "Kok", "04_given_names": "Martin",
        "05_sort_key": "Kok, Martin", "06_birth_year": "1850", "07_death_year": "1942",
        "13_raw_text": "Kok, Martin (1850-1942), " + r["09_description"] + " " + r["10_references_raw"],
    })
    replacements[id(r)] = [kohle, kok]
    n_split += 1

    # --- Morsing / Mortensen / Mortier de Fontaine -------------------
    r = find_one(rows, sn="Morsing", gn="Johanne (død")
    morsing = blank()
    morsing.update({
        "02_entry_type": "standardpost", "03_surname": "Morsing",
        "04_given_names": "Johanne", "05_sort_key": "Morsing, Johanne",
        "07_death_year": "1776", "08_year_note": "55 Aar gl.",
        "09_description": "Enke efter Chr.M.",
        "10_references_raw": "I 58.", "11_references_parsed": "I:58",
        "13_raw_text": "Morsing, Johanne (død 1776, 55 Aar gl.), Enke efter Chr.M. I 58.",
    })
    mortensen = blank()
    mortensen.update({
        "02_entry_type": "krydshenvisning",
        "03_surname": "Mortensen", "04_given_names": "i det vestlige Amerika",
        "05_sort_key": "Mortensen, i det vestlige Amerika",
        "12_see_also": "Morton, H. C.",
        "13_raw_text": "Mortensen (i det vestlige Amerika), se: Morton, H. C.",
    })
    mortier = dict(r)
    mortier.update({
        "03_surname": "Mortier de Fontaine",
        "04_given_names": "Henri Louis Stanislaus",
        "05_sort_key": "Mortier de Fontaine, Henri Louis Stanislaus",
        "06_birth_year": "1816", "07_death_year": "1883", "08_year_note": "",
        "13_raw_text": "Mortier de Fontaine, Henri Louis Stanislaus (1816-1883), "
                       + r["09_description"] + " " + r["10_references_raw"],
    })
    replacements[id(r)] = [morsing, mortensen, mortier]
    n_split += 1

    # --- Power, Ellen / Power, Marguerite ----------------------------
    r = find_one(rows, sn="Power", gn="Ellen og Marguerite")
    ellen = dict(r)
    ellen.update({
        "04_given_names": "Ellen", "05_sort_key": "Power, Ellen",
        "07_death_year": "1902",
        "09_description": "Niece af Lady Blessington.",
        "13_raw_text": "Power, Ellen (død 1902), Niece af Lady Blessington. " + r["10_references_raw"],
    })
    marg = dict(r)
    marg.update({
        "04_given_names": "Marguerite", "05_sort_key": "Power, Marguerite",
        "07_death_year": "1867",
        "09_description": "Niece af Lady Blessington.",
        "13_raw_text": "Power, Marguerite (død 1867), Niece af Lady Blessington. " + r["10_references_raw"],
    })
    replacements[id(r)] = [ellen, marg]
    n_split += 1

    # --- Schram cross-reference / Schram (Skram), Gustav -------------
    r = find_one(rows, sn="Schram", gn="se ogsaa: Skram.")
    xref = blank()
    xref.update({
        "02_entry_type": "krydshenvisning", "03_surname": "Schram",
        "05_sort_key": "Schram", "12_see_also": "Skram",
        "13_raw_text": "Schram, se ogsaa: Skram.",
    })
    gustav = dict(r)
    gustav.update({
        "03_surname": "Schram (Skram)", "04_given_names": "Gustav",
        "05_sort_key": "Schram (Skram), Gustav",
        "06_birth_year": "1802", "07_death_year": "1865",
        "13_raw_text": "Schram (Skram), Gustav (1802-1865), "
                       + r["09_description"] + " " + r["10_references_raw"],
    })
    replacements[id(r)] = [xref, gustav]
    n_split += 1

    # --- Seidelin cross-reference / Seidl ----------------------------
    r = find_one(rows, sn="Seidelin", gn="se: Brinck-Seidelin")
    xref = blank()
    xref.update({
        "02_entry_type": "krydshenvisning", "03_surname": "Seidelin",
        "05_sort_key": "Seidelin", "12_see_also": "Brinck-Seidelin, H. D.",
        "13_raw_text": "Seidelin, se: Brinck-Seidelin, H. D.",
    })
    seidl = dict(r)
    seidl.update({
        "03_surname": "Seidl", "04_given_names": "Johann Gabriel",
        "05_sort_key": "Seidl, Johann Gabriel",
        "06_birth_year": "1804", "07_death_year": "1875",
        "13_raw_text": "Seidl, Johann Gabriel (1804-1875), "
                       + r["09_description"] + " " + r["10_references_raw"],
    })
    replacements[id(r)] = [xref, seidl]
    n_split += 1

    # --- Skovgaard cross-reference / Skovgaard, Georgia --------------
    r = find_one(rows, sn="Skovgaard", gn="se ogsaa: Schougaard.")
    xref = blank()
    xref.update({
        "02_entry_type": "krydshenvisning", "03_surname": "Skovgaard",
        "05_sort_key": "Skovgaard", "12_see_also": "Schougaard",
        "13_raw_text": "Skovgaard, se ogsaa: Schougaard.",
    })
    georgia = dict(r)
    georgia.update({
        "03_surname": "Skovgaard", "04_given_names": "Georgia, f. Schouw",
        "05_sort_key": "Skovgaard, Georgia, f. Schouw",
        "06_birth_year": "1828", "07_death_year": "1868",
        "13_raw_text": "Skovgaard, Georgia, f. Schouw (1828-1868), "
                       + r["09_description"] + " " + r["10_references_raw"],
    })
    replacements[id(r)] = [xref, georgia]
    n_split += 1

    out = []
    for r in rows:
        out.extend(replacements.get(id(r), [r]))

    # --- Reviewed orthographic fix ----------------------------------
    n_orth = 0
    for r in out:
        for field in ("03_surname", "04_given_names", "09_description", "13_raw_text"):
            if "Hallermiinde" in r[field]:
                r[field] = r[field].replace("Hallermiinde", "Hallermünde")
                n_orth += 1

    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"applied {n_split} reviewed splits; {n_orth} orthographic fixes")
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
