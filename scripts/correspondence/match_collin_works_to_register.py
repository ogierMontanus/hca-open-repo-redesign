#!/usr/bin/env python3
"""
match_collin_works_to_register.py
------------------------------------
Maps data/review/collin_letters_work_index.csv against this project's
own WORK-REGISTER (mockup/data/works-extra.js), matching on normalized
title -- works-extra.js titles already embed a publication year in the
same "(YYYY)" convention as the printed edition (e.g. "Aus Herz und
Welt (1860)"), so title match doubles as a year check for most entries.

Title normalization is two-tier, same as the place/person matchers (see
_lib/names.py): primary_keys() applies the calibrated folds (æ->ae,
ø->o always; å tried both bare and doubled). This matcher previously had
NO diacritic handling at all -- ø/æ/ä/é all appear in this index's
titles, and ø in particular has no shared NFD decomposition with "o", so
without an explicit rule it was silently deleted as non-alphanumeric
rather than folded (e.g. "Ole Lukøie" normalized to two words with the
ø gone, "ole lukie", rather than "ole lukoie"). edge_case_key() is the
broader, uncalibrated fallback -- tried only when the calibrated keys
find nothing, tagged with its own tier.

Rows the extractor already tagged issue_type (omnibus_collection,
serial_installment, possible_fragment) or see_also (a redirect) are NOT
run through matching at all -- they have no 1:1 target on the site by
construction, not because matching failed. Their tier is set directly
from that tag so they stay visibly distinct from a genuine "none" miss,
ready for a later human pass rather than looking like unexplained gaps.

Match attempts, in order, for everything else:
  1. exact title+year (primary keys, then edge-case key)
  2. exact title only, year stripped from both sides (primary, then edge)
  3. title with a trailing non-year parenthetical also stripped from the
     SITE side (e.g. "Ole Lukøie (Eventyr)" -> "Ole Lukøie") -- catches
     genre-disambiguated site titles the printed index cites bare.
     Multiple site works collapsing to the same stripped key (a title
     shared by two different works, e.g. a tale AND a play of the same
     name) are flagged "ambiguous_genre", never auto-picked.
  4. fuzzy (difflib, cutoff 0.88) against the title-only index -- catches
     spelling-convention drift (e.g. "De røde Sko" vs. site's "De røde
     Skoe"). Flagged with its own tier so a fuzzy hit is never silently
     indistinguishable from an exact one.

Run from the repo root:
  python scripts/correspondence/match_collin_works_to_register.py
"""

import csv
import difflib
import json
import os
import re

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _lib.names import primary_keys, edge_case_key

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COLLIN_CSV = os.path.join(ROOT, "data", "review", "collin_letters_work_index.csv")
# Built register cards from the publication repo (hca-open-repo). They are a
# BUILD artefact, so they live in the other repository; point
# HCA_MOCKUP_DATA_DIR at its mockup/data/ folder, or keep the two repos as
# siblings and the default below finds it.
MOCKUP_DATA_DIR = os.environ.get(
    "HCA_MOCKUP_DATA_DIR",
    os.path.join(ROOT, os.pardir, "hca-open-repo", "mockup", "data"),
)
WORKS_JS = os.path.join(MOCKUP_DATA_DIR, "works-extra.js")
OUT_CSV = os.path.join(ROOT, "data", "review", "collin_letters_work_match.csv")

FUZZY_CUTOFF = 0.88


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


def strip_year(s):
    return re.sub(r"\s*\(\d{4}[^)]*\)\s*", " ", s or "").strip()


def strip_trailing_paren(s):
    """Strip ONE trailing non-year parenthetical, e.g. "Ole Lukøie
    (Eventyr)" -> "Ole Lukøie". Only trailing (end-of-string) parens --
    never touches a parenthetical mid-title, which is more likely to be
    load-bearing (a place, a qualifier) than a bare genre tag."""
    return re.sub(r"\s*\([^)0-9][^)]*\)\s*$", "", s or "").strip()


def title_keys(s):
    return primary_keys(s, keep_spaces=True)


def title_edge_key(s):
    return edge_case_key(s, keep_spaces=True)


def add_all(index, keys, record):
    for key in keys:
        if key:
            index.setdefault(key, []).append(record)


def build_indexes(works):
    idx = {name: {} for name in ("primary", "primary_noyear", "primary_genre",
                                  "edge", "edge_noyear")}
    for reg_id, w in works.items():
        title = w.get("title")
        rec = (reg_id, title)
        add_all(idx["primary"], title_keys(title), rec)
        no_year = strip_year(title)
        add_all(idx["primary_noyear"], title_keys(no_year), rec)
        add_all(idx["primary_genre"], title_keys(strip_trailing_paren(no_year)), rec)
        ek = title_edge_key(title)
        if ek:
            idx["edge"].setdefault(ek, []).append(rec)
        ek2 = title_edge_key(no_year)
        if ek2:
            idx["edge_noyear"].setdefault(ek2, []).append(rec)
    return idx


def lookup_all(index, keys):
    seen, out = set(), []
    for key in keys:
        for rec in index.get(key, []):
            if rec[0] not in seen:
                seen.add(rec[0])
                out.append(rec)
    return out


def main():
    print("Loading works-extra.js …")
    works = load_json_object(WORKS_JS)
    print(f"  {len(works)} register works loaded")
    idx = build_indexes(works)

    with open(COLLIN_CSV, encoding="utf-8") as f:
        collin_rows = list(csv.DictReader(f))
    print(f"  {len(collin_rows)} Collin work entries")

    out_rows = []
    tiers = {}
    for row in collin_rows:
        title, year = row["title"], row["year"]
        issue_type = row.get("issue_type", "")
        see_also = row.get("see_also", "")

        if see_also:
            tier, matches, matched_on = "redirect", [], ""
        elif issue_type:
            tier, matches, matched_on = issue_type, [], ""
        else:
            matches, matched_on = [], ""
            if year:
                matches = lookup_all(idx["primary"], title_keys(f"{title} ({year})"))
                matched_on = "title+year" if matches else ""
            if not matches:
                matches = lookup_all(idx["primary_noyear"], title_keys(title))
                matched_on = "title_only" if matches else matched_on
            if not matches:
                matches = lookup_all(idx["primary_genre"], title_keys(strip_trailing_paren(title)))
                matched_on = "genre_stripped" if matches else matched_on
            if not matches:
                key2 = list(title_keys(title))[0]
                close = difflib.get_close_matches(key2, list(idx["primary_noyear"].keys()), n=2, cutoff=FUZZY_CUTOFF)
                if len(close) == 1:
                    matches = idx["primary_noyear"][close[0]]
                    matched_on = "fuzzy"
            # Edge-case fallback: only if the calibrated keys found nothing.
            if not matches:
                ek = title_edge_key(f"{title} ({year})" if year else title)
                matches = idx["edge"].get(ek, [])
                if not matches:
                    matches = idx["edge_noyear"].get(title_edge_key(title), [])
                if matches:
                    matched_on = "diacritic_edge_case"

            if matched_on == "genre_stripped":
                tier = "ambiguous_genre" if len(matches) > 1 else "exact" if len(matches) == 1 else "none"
            elif matched_on == "fuzzy":
                tier = "fuzzy" if len(matches) == 1 else "ambiguous"
            elif matched_on == "diacritic_edge_case":
                tier = "exact_diacritic_edge_case" if len(matches) == 1 else "ambiguous_diacritic_edge_case"
            else:
                tier = "exact" if len(matches) == 1 else "ambiguous" if len(matches) > 1 else "none"

        tiers[tier] = tiers.get(tier, 0) + 1
        out_rows.append({
            "collin_title": row["title"],
            "collin_year": row["year"],
            "collin_category": row["category"],
            "see_also": see_also,
            "match_tier": tier,
            "match_count": len(matches),
            "matched_on": matched_on,
            "match_reg_ids": ";".join(m[0] for m in matches),
            "match_titles": " | ".join(m[1] for m in matches),
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
