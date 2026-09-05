#!/usr/bin/env python3
"""
compare_to_xlsx.py
--------------------
Compares data/parsed/personregister_xi_parsed.tsv (after diacritics
have been corrected via fix_diacritics_from_xlsx.py) against
data/raw/HCA REPOSITORY V0.92/PersonData-PQ-V0.92.xlsx (sheet DimPer),
matching on (diacritic-normalized surname, birth year, death year).

Reports the row-count divergence with the two KNOWN structural
categories subtracted out (this project's own "se:" cross-reference
rows, which xlsx does not carry as separate rows at all, and the
handful of dash sub-entries this project splits out separately),
leaving only the residual, unexplained divergence for review.

For every surname where my data and xlsx disagree on WHICH specific
people are filed under it (the "Ahlefeldt-shaped" case: both sources
have entries for that surname, but not the same set of people), a
full side-by-side row is written to
data/curated/personregister_xi_vs_xlsx_review.tsv for manual review.

Run from the repo root, AFTER fix_diacritics_from_xlsx.py:
  python scripts/parsers/compare_to_xlsx.py
"""
import csv
import os
import re
import unicodedata
from collections import Counter, defaultdict

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
XLSX_PATH = os.path.join(ROOT, "data", "raw", "HCA REPOSITORY V0.92", "PersonData-PQ-V0.92.xlsx")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_vs_xlsx_review.tsv")


def strip_diacritics(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c))


def xl_surname(title: str) -> str:
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(title))
    return t.split(",")[0].strip()


def xl_given(title: str) -> str:
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(title))
    parts = t.split(",", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        mine = list(csv.DictReader(f, delimiter="\t"))

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]

    print(f"Min parser total : {len(mine)}")
    print(f"XLSX DimPer total: {len(dim)}")
    print(f"Rå forskel       : {len(mine) - len(dim)}")
    print()

    by_type = Counter(x["02_entry_type"] for x in mine)
    n_seealso = by_type["krydshenvisning"]
    n_sub = by_type["underpost"]
    xl_dash_sub = sum(1 for d in dim if str(d[1]).strip().startswith("-"))
    print("Kendte strukturelle kategorier, trukket ud af forskellen:")
    print(f"  mine krydshenvisninger ('se:')      : {n_seealso}  (xlsx bærer ~0 som egen række)")
    print(f"  mine underposter (tankestreg-arvet) : {n_sub}  (xlsx bærer {xl_dash_sub} som egen '-'-titel-række)")
    explained = n_seealso + (n_sub - xl_dash_sub)
    residual_rowcount = (len(mine) - len(dim)) - explained
    print(f"  forklaret af disse to kategorier    : {explained}")
    print(f"  RESTERENDE, uforklaret rå forskel    : {residual_rowcount}")
    print()

    # --- Precise person-level comparison (year-keyed) ---
    xl_by_key = defaultdict(list)
    xl_by_surname = defaultdict(list)
    for d in dim:
        pid, title, desc, birth, death = d
        surname = xl_surname(title)
        given = xl_given(title)
        surname_norm = strip_diacritics(surname).lower()
        xl_by_surname[surname_norm].append((surname, given, desc or "", birth, death))
        if birth is not None and death is not None:
            xl_by_key[(surname_norm, int(birth), int(death))].append((surname, given, desc or ""))

    standardposts = [x for x in mine if x["02_entry_type"] == "standardpost"]
    with_years = [x for x in standardposts if x["06_birth_year"] and x["07_death_year"]]
    matched = 0
    unmatched = []
    for x in with_years:
        b, d = int(x["06_birth_year"]), int(x["07_death_year"])
        if "f. Kr." in x["08_year_note"]:
            b, d = -b, -d
        key = (strip_diacritics(x["03_surname"]).lower(), b, d)
        if key in xl_by_key:
            matched += 1
        else:
            unmatched.append(x)

    print(f"Standardposter MED begge årstal        : {len(with_years)}")
    print(f"  match på (efternavn+år) i xlsx        : {matched}")
    print(f"  UDEN match -- reel divergens til gennemsyn: {len(unmatched)}")
    print()

    # --- Build the surname-level "Ahlefeldt-shaped" review file ---
    # For every surname (diacritic-normalized) where either side has an
    # unmatched entry, list every entry my side and xlsx's side each
    # have under that surname, side by side, for a human to reconcile.
    affected_surnames = sorted({strip_diacritics(x["03_surname"]).lower() for x in unmatched})

    # Also include standardpost entries WITHOUT both years, if their
    # surname is already flagged (they can't be year-matched, but they
    # belong in the same human-review bucket for that surname).
    mine_by_surname = defaultdict(list)
    for x in standardposts:
        mine_by_surname[strip_diacritics(x["03_surname"]).lower()].append(x)

    review_rows = []
    for s in affected_surnames:
        mine_entries = mine_by_surname.get(s, [])
        xl_entries = xl_by_surname.get(s, [])
        n = max(len(mine_entries), len(xl_entries))
        # Pair by matching year first (exact matches removed from view
        # would hide context), then list leftovers unpaired.
        xl_pool = list(xl_entries)
        pairs = []
        for me in mine_entries:
            match = None
            if me["06_birth_year"] and me["07_death_year"]:
                b, d = int(me["06_birth_year"]), int(me["07_death_year"])
                if "f. Kr." in me["08_year_note"]:
                    b, d = -b, -d
                for i, xe in enumerate(xl_pool):
                    if xe[3] is not None and xe[4] is not None and int(xe[3]) == b and int(xe[4]) == d:
                        match = xl_pool.pop(i)
                        break
            if match is None and not (me["06_birth_year"] and me["07_death_year"]):
                # No year on either side to anchor on (common for
                # dateless single-visit mentions, e.g. "Ahlefeldt,
                # Grevinde, Berlin 1.1.1846"): fall back to comparing
                # text directly. My parser only fills 04_given_names
                # when a year-parenthesis was found (see YEAR_RE in
                # parse_personregister_xi.py); a dateless entry like
                # this one has its lead-in text ("Grevinde") in
                # 09_description instead, so both fields are tried.
                # Exact-after-normalization only -- this must not guess
                # between multiple untitled entries under one surname.
                me_leadin_norm = strip_diacritics(
                    me["04_given_names"] or me["09_description"]
                ).lower().strip().rstrip(".")
                for i, xe in enumerate(xl_pool):
                    if xe[3] is None and xe[4] is None:
                        xe_given_norm = strip_diacritics(xe[1]).lower().strip()
                        # xlsx's given-names field may itself just be
                        # the lead word ("Nizza") with the rest of the
                        # sentence in its description -- compare against
                        # a prefix match too, not only full equality.
                        if xe_given_norm and (
                            xe_given_norm == me_leadin_norm
                            or me_leadin_norm.startswith(xe_given_norm + ",")
                            or me_leadin_norm.startswith(xe_given_norm + " ")
                        ):
                            match = xl_pool.pop(i)
                            break
            pairs.append((me, match))
        for xe in xl_pool:
            pairs.append((None, xe))

        for me, xe in pairs:
            if me is not None and xe is not None:
                # Both sides have this exact person (same surname
                # bucket, same signed birth+death year) -- this is a
                # confirmed match, not a divergence. Only keep it in
                # the review file if the description differs by more
                # than trivial typesetting noise (case, line-wrap
                # hyphenation, dash style), since a real wording/fact
                # difference (e.g. "J.A.Å." vs "J.A.A.") is still worth
                # a human's eyes even though the person itself matched.
                my_desc, xl_desc = me["09_description"], xe[2]
                trivial = (
                    my_desc.lower() == xl_desc.lower()
                    or strip_diacritics(my_desc).replace("-", "").replace(" ", "").lower()
                    == strip_diacritics(xl_desc).replace("–", "").replace(" ", "").lower()
                )
                if trivial:
                    continue
                status = "matchet_person_men_beskrivelse_afviger"
            else:
                status = "kun_min" if xe is None else "kun_xlsx"

            review_rows.append({
                "surname_norm": s,
                "min_entry_id": me["01_entry_id"] if me else "",
                "min_surname": me["03_surname"] if me else "",
                "min_given_names": me["04_given_names"] if me else "",
                "min_birth_year": me["06_birth_year"] if me else "",
                "min_death_year": me["07_death_year"] if me else "",
                "min_description": me["09_description"] if me else "",
                "min_references": me["11_references_parsed"] if me else "",
                "xlsx_surname": xe[0] if xe else "",
                "xlsx_given_names": xe[1] if xe else "",
                "xlsx_description": xe[2] if xe else "",
                "xlsx_birth_year": xe[3] if xe and xe[3] is not None else "",
                "xlsx_death_year": xe[4] if xe and xe[4] is not None else "",
                "status": status,
            })

    fieldnames = [
        "surname_norm", "status",
        "min_entry_id", "min_surname", "min_given_names", "min_birth_year", "min_death_year",
        "min_description", "min_references",
        "xlsx_surname", "xlsx_given_names", "xlsx_birth_year", "xlsx_death_year", "xlsx_description",
    ]
    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(review_rows)

    status_counts = Counter(r["status"] for r in review_rows)
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}  ({len(review_rows)} rækker, {len(affected_surnames)} berørte efternavne)")
    print("  status-fordeling:", dict(status_counts))


if __name__ == "__main__":
    main()
