#!/usr/bin/env python3
"""
remove_given_name_prefix_from_description.py
-------------------------------------------------
Column 4 (04_given_names) vs column 9 (09_description): for every row,
checks whether 09_description starts with the row's own 04_given_names
verbatim -- a leftover from calibrate_names_from_reference.py, which
filled empty given-name fields from the reference source but never
trimmed the reference's description text, which itself repeats the name
before the first comma:

    Abad | 04="Leandro" | 09="Leandro, Hotelvaert i Toledo."
                                ^^^^^^^ duplicate of column 4

After the name prefix is removed, the description sometimes still opens
with the person's OWN life-span parenthesis (also duplicated from the
reference, since the parser never re-ran year extraction on this
already-populated row):

    Abendrot | 04="August" | 09="August (dod 1867), tysk ..."
    -> strip name -> "(dod 1867), tysk ..."
    -> ALSO lift the year -> 07="1867", 09="tysk ..."

That second step only fires on a genuine life span (a range, an
explicit "d."/"dod", or an "f. Chr." form) and only into an EMPTY
06/07 -- it never overwrites a year the row already has.

Usage:
  --sample N   write the first N matches (default 20) to
               data/curated/personregister_xi_given_name_prefix_sample.tsv
               for review; makes NO changes to the parsed file.
  --apply      remove the duplicated prefix (and lift any resulting
               leading life span) across ALL matching rows and write
               personregister_xi_parsed.tsv in place. Only run this
               after reviewing the sample.

  python scripts/parsers/remove_given_name_prefix_from_description.py --sample 20
  python scripts/parsers/remove_given_name_prefix_from_description.py --apply
"""
import argparse
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
SAMPLE_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_given_name_prefix_sample.tsv")

# Same life-span shape used elsewhere in this pipeline (refine_description_
# segmentation.py): a range, an explicit death, or a BC year. Includes the
# OCR variants seen in this register ("Aar" capitalised, "gi." for "gl.").
LIFE_AT_START = re.compile(
    r"^\(\s*(?:"
    r"(?:d\.|død)\s*(?P<dy>\d{3,4})(?P<age>,\s*\d{1,3}\s*(?:år|Aa?r)\s*g[li]\.?)?"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})(?P<bfrac>/\d{2,4})?\s*(?:\(\?\))?\s*"
    r"[–—-]\s*(?:ca\.\s*|efter\s*)?(?P<d>\d{2,4}|\?)"
    r"|(?:ca\.\s*)?(?P<bc>\d{3,4})\s*f\.\s*Chr\."
    r")\s*(?P<fchr>f\.\s*Chr\.)?\s*\)"
)


def find_matches(rows):
    matches = []
    for r in rows:
        gn = r["04_given_names"].strip()
        desc = r["09_description"].strip()
        if gn and desc.startswith(gn):
            matches.append(r)
    return matches


def strip_prefix(row):
    gn = row["04_given_names"].strip()
    desc = row["09_description"].strip()
    rest = desc[len(gn):].lstrip()
    rest = rest.lstrip(",").strip()
    return rest


def years_from(m):
    """(birth, death, note) from a LIFE_AT_START match."""
    if m.group("age"):
        note = m.group("age").strip(", ")
    else:
        note = ""
    if m.group("dy"):
        return "", m.group("dy"), note
    if m.group("bc"):
        return m.group("bc"), "", "f. Kr. (BC)"
    b = m.group("b") or ""
    d = m.group("d") or ""
    if d and b and d != "?" and len(d) < len(b):
        d = b[: len(b) - len(d)] + d          # "1838-76" -> 1876
    if m.group("bfrac"):
        note = f"{b}{m.group('bfrac')}"        # "1476/77" preserved
    if m.group("fchr"):
        note = "f. Kr. (BC)"
    return b, d, note


def strip_prefix_and_lift_years(row):
    """Returns (new_description, birth, death, note) -- birth/death/note
    are '' when the row already has a year (nothing new to WRITE), but
    the leading life-span text is stripped from the description either
    way, since it is redundant with 06/07 whether or not those were
    already populated by an earlier pass."""
    rest = strip_prefix(row)
    birth = death = note = ""
    m = LIFE_AT_START.match(rest)
    if m:
        already_has_year = bool(row["06_birth_year"].strip() or row["07_death_year"].strip())
        if not already_has_year:
            birth, death, note = years_from(m)
        rest = rest[m.end():].strip().lstrip(",").strip()
    return rest, birth, death, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None,
                     help="write the first N matches to a review TSV; no changes made")
    ap.add_argument("--apply", action="store_true",
                     help="remove the duplicated prefix across all matches, in place")
    args = ap.parse_args()

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    matches = find_matches(rows)
    print(f"rows where 09_description starts with 04_given_names: {len(matches)}")

    if args.apply:
        n = n_years = 0
        for r in rows:
            gn = r["04_given_names"].strip()
            desc = r["09_description"].strip()
            if gn and desc.startswith(gn):
                new_desc, birth, death, note = strip_prefix_and_lift_years(r)
                r["09_description"] = new_desc
                if birth or death:
                    r["06_birth_year"] = r["06_birth_year"] or birth
                    r["07_death_year"] = r["07_death_year"] or death
                    if note and not r["08_year_note"].strip():
                        r["08_year_note"] = note
                    n_years += 1
                n += 1
        with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        print(f"applied: removed duplicated prefix from {n} rows")
        print(f"         also lifted a life span into 06/07 for {n_years} of those")
        return

    n = args.sample if args.sample is not None else 20
    sample = matches[:n]
    out_rows = []
    for r in sample:
        new_desc, birth, death, note = strip_prefix_and_lift_years(r)
        out_rows.append({
            "entry_id": r["01_entry_id"],
            "surname": r["03_surname"],
            "given_names": r["04_given_names"],
            "description_before": r["09_description"],
            "description_after": new_desc,
            "birth_year_lifted": birth,
            "death_year_lifted": death,
            "year_note_lifted": note,
        })

    os.makedirs(os.path.dirname(SAMPLE_TSV), exist_ok=True)
    with open(SAMPLE_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {len(out_rows)}-row sample to {os.path.relpath(SAMPLE_TSV, ROOT)}")


if __name__ == "__main__":
    main()
