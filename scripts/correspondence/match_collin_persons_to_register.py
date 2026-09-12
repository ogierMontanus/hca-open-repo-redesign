#!/usr/bin/env python3
"""
match_collin_persons_to_register.py
-------------------------------------
Maps data/curated/collin_letters_person_index.csv (digitized from the
printed IV. PERSON-REGISTER of H. C. Andersens Brevveksling med Edvard
og Henriette Collin -- see extract_collin_person_index.py) against this
project's own PERSON-REGISTER (mockup/data/persons-extra.js), matching
on (surname, birth year) as requested -- the most reliable simple key
available: given-name spelling/abbreviation varies far more between the
two sources than a surname + a specific birth year does.

Surname normalization is two-tier (see scripts/_lib/names.py for the full
reasoning and the measured numbers): primary_keys() applies the
calibrated folds (æ->ae, ø->o always; å tried both bare and doubled to
"aa"); edge_case_key() is a broader, uncalibrated fallback -- strips
every diacritic uniformly -- tried only when the primary keys find no
surname at all, and tagged with its own tier so it stays visible as
resting on a less-checked rule.

Match tiers (each has an "_edge_case" counterpart when only the
fallback surname key found the candidate(s)):
  exact       surname + birth year both match exactly one register entry
  ambiguous   surname + birth year match MORE THAN ONE register entry
  surname_only  surname matches but the register entry has no recorded
              birth year (`born` is null) -- plausible, not confirmed
  surname_year_mismatch  surname matches, but every candidate's
              recorded birth year differs
  none        no register entry shares the surname at all, under either
              the primary or the edge-case key

Nothing here is written back into entities.csv or persons-extra.js --
this only proposes matches for human verification, same shape as every
other cross-reference in this project (works_wikidata.csv,
breve_person_crosswalk.csv, collin_letters_place_index.csv, ...).

Output: data/curated/collin_letters_person_match.csv (all Collin entries
with a birth year, one row each, plus their match tier and candidate(s)).

Run from the repo root:
  python scripts/correspondence/match_collin_persons_to_register.py
"""

import csv
import json
import os

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _lib.names import primary_keys, edge_case_key

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COLLIN_CSV = os.path.join(ROOT, "data", "curated", "collin_letters_person_index.csv")
# Built register cards from the publication repo (hca-open-repo). They are a
# BUILD artefact, so they live in the other repository; point
# HCA_MOCKUP_DATA_DIR at its mockup/data/ folder, or keep the two repos as
# siblings and the default below finds it.
MOCKUP_DATA_DIR = os.environ.get(
    "HCA_MOCKUP_DATA_DIR",
    os.path.join(ROOT, os.pardir, "hca-open-repo", "mockup", "data"),
)
PERSONS_JS = os.path.join(MOCKUP_DATA_DIR, "persons-extra.js")
OUT_CSV = os.path.join(ROOT, "data", "curated", "collin_letters_person_match.csv")


def load_persons_extra():
    """Isolate the PERSONS_EXTRA object literal (the file has a second
    object -- a nationality-label lookup -- appended after it) via
    bracket counting, then parse it as JSON."""
    text = open(PERSONS_JS, encoding="utf-8").read()
    start = text.index("{")
    depth, in_str, esc, end = 0, False, False, None
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit("Could not find end of PERSONS_EXTRA object")
    return json.loads(text[start:end])


def surname_from_label(label):
    return (label or "").split(",")[0].strip()


def tier_for(candidates, birth_year):
    """Same tiering logic for either key source -- caller appends
    '_edge_case' when this was reached via the fallback key."""
    exact = [c for c in candidates if c[2] == birth_year]
    no_year_same_surname = [c for c in candidates if not c[2]]
    if len(exact) == 1:
        return "exact", exact
    if len(exact) > 1:
        return "ambiguous", exact
    if no_year_same_surname:
        return "surname_only", no_year_same_surname
    if candidates:
        return "surname_year_mismatch", candidates
    return "none", []


def main():
    print("Loading persons-extra.js …")
    persons = load_persons_extra()
    print(f"  {len(persons)} register persons loaded")

    by_primary, by_edge = {}, {}
    for reg_id, p in persons.items():
        surname = surname_from_label(p.get("label"))
        rec = (reg_id, p.get("label"), p.get("born"), p.get("died"))
        for key in primary_keys(surname):
            if key:
                by_primary.setdefault(key, []).append(rec)
        ekey = edge_case_key(surname)
        if ekey:
            by_edge.setdefault(ekey, []).append(rec)

    print("Loading Collin person index …")
    with open(COLLIN_CSV, encoding="utf-8") as f:
        collin_rows = list(csv.DictReader(f))
    print(f"  {len(collin_rows)} Collin entries")

    out_rows = []
    tiers = {}
    for row in collin_rows:
        if not row["birth_year"]:
            continue  # out of scope: no birth year to match on
        birth_year = row["birth_year"]

        candidates_by_id = {}
        for key in primary_keys(row["surname"]):
            for c in by_primary.get(key, []):
                candidates_by_id[c[0]] = c
        tier, matches = tier_for(list(candidates_by_id.values()), birth_year)

        if tier == "none":
            edge_candidates = by_edge.get(edge_case_key(row["surname"]), [])
            edge_tier, edge_matches = tier_for(edge_candidates, birth_year)
            if edge_tier != "none":
                tier, matches = f"{edge_tier}_edge_case", edge_matches

        tiers[tier] = tiers.get(tier, 0) + 1

        out_rows.append({
            "collin_surname": row["surname"],
            "collin_given_names": row["given_names"],
            "collin_birth_year": row["birth_year"],
            "collin_death_year": row["death_year"],
            "match_tier": tier,
            "match_count": len(matches),
            "match_reg_ids": ";".join(m[0] for m in matches),
            "match_labels": " | ".join(m[1] for m in matches),
        })

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"wrote {os.path.relpath(OUT_CSV, ROOT)}  ({len(out_rows)} rows)")
    print("Tiers:", tiers)


if __name__ == "__main__":
    main()
