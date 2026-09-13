#!/usr/bin/env python3
"""
match_collin_places_to_register.py
-------------------------------------
Maps data/review/collin_letters_place_index.csv (see
extract_collin_place_index.py / docs/data-model/collin-place-index.md)
against this project's own PLACE-REGISTER (mockup/data/places-extra.js),
matching on normalized place name -- places have no birth-year-like
disambiguator, so name is the only simple key available; ambiguous
same-name matches (distinct real-world places sharing a name) are
surfaced, not silently resolved.

Two-tier normalization (see scripts/_lib/names.py for the full reasoning
and the measured aa/å, ø/ö numbers behind it):
  "exact"                       matched on the calibrated primary keys
  "exact_diacritic_edge_case"   no primary-key match, but exactly one
                                 candidate matches once EVERY diacritic
                                 is stripped uniformly (an uncalibrated,
                                 broader fallback -- ranked below "exact"
                                 on purpose, see scripts/_lib/names.py)

Run from the repo root:
  python scripts/correspondence/match_collin_places_to_register.py
"""

import csv
import json
import os

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _lib.names import primary_keys, edge_case_key

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COLLIN_CSV = os.path.join(ROOT, "data", "review", "collin_letters_place_index.csv")
# Built register cards from the publication repo (hca-open-repo). They are a
# BUILD artefact, so they live in the other repository; point
# HCA_MOCKUP_DATA_DIR at its mockup/data/ folder, or keep the two repos as
# siblings and the default below finds it.
MOCKUP_DATA_DIR = os.environ.get(
    "HCA_MOCKUP_DATA_DIR",
    os.path.join(ROOT, os.pardir, "hca-open-repo", "mockup", "data"),
)
PLACES_JS = os.path.join(MOCKUP_DATA_DIR, "places-extra.js")
OUT_CSV = os.path.join(ROOT, "data", "review", "collin_letters_place_match.csv")


def load_json_object(path):
    text = open(path, encoding="utf-8").read()
    start = text.index("{")
    depth, in_str, esc, end = 0, False, False, None
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
            continue
        if c == '"': in_str = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(text[start:end])


def main():
    print("Loading places-extra.js …")
    places = load_json_object(PLACES_JS)
    print(f"  {len(places)} register places loaded")

    by_primary, by_edge = {}, {}
    for reg_id, p in places.items():
        label = p.get("label")
        for key in primary_keys(label):
            if key:
                by_primary.setdefault(key, []).append((reg_id, label, p.get("country_da")))
        ekey = edge_case_key(label)
        if ekey:
            by_edge.setdefault(ekey, []).append((reg_id, label, p.get("country_da")))

    with open(COLLIN_CSV, encoding="utf-8") as f:
        collin_rows = list(csv.DictReader(f))
    print(f"  {len(collin_rows)} Collin place entries")

    out_rows = []
    tiers = {}
    for row in collin_rows:
        if row.get("see_also"):
            continue  # redirect rows carry no citation of their own to match
        name = row["place_name_clean"] or row["place_name_raw"]

        matches_by_id = {}
        for key in primary_keys(name):
            for m in by_primary.get(key, []):
                matches_by_id[m[0]] = m
        matches = list(matches_by_id.values())
        tier = "exact" if len(matches) == 1 else "ambiguous" if len(matches) > 1 else "none"

        if tier == "none":
            edge_matches = by_edge.get(edge_case_key(name), [])
            if len(edge_matches) == 1:
                matches, tier = edge_matches, "exact_diacritic_edge_case"
            elif len(edge_matches) > 1:
                matches, tier = edge_matches, "ambiguous_diacritic_edge_case"

        tiers[tier] = tiers.get(tier, 0) + 1
        out_rows.append({
            "collin_place_name": name,
            "match_tier": tier,
            "match_count": len(matches),
            "match_reg_ids": ";".join(m[0] for m in matches),
            "match_labels": " | ".join(m[1] for m in matches),
            "match_countries": " | ".join((m[2] or "") for m in matches),
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
