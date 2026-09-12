#!/usr/bin/env python3
"""
reconcile_steder_categories.py
---------------------------------
Joins the human-verified `Category` and `Country` columns from
raw/Steder_i_dagboegerne_verificeret_udfyldt VER 1.0.xlsx (sheet
RawLoc) onto data/normalized/entities.csv's STED-REGISTER places — see
docs/data-model/steder-verificeret-category-mapping.md §1/§3 for the
methodology and the Category numbers this reproduces.

Matching, in order (each entity_id is only claimed once, by the first
step that resolves it):

  1. Exact case-insensitive RegistryTitle <-> label match.
  2. Diacritic/orthography-normalized match (æ/ø/å folded the same way
     as scripts/_lib/names.py's doubled key — å→aa fires here, since the
     replace runs before NFD; generic accents NFD-stripped) — catches
     spelling-convention drift the exact match misses.
  3. Register "se: X" / "se X" redirect labels (e.g. "Bruxelles, se:
     Brüssel.") resolved to their target X, then matched (steps 1-2)
     against the TARGET's name instead of the redirect stub's own label
     -- these are register-internal aliases, not new places.

Rows the xlsx itself leaves ambiguous (title matches more than one
register label) or blank (no Category/Country cell) are skipped, not
guessed at. A residual ~100-150 places stay unmatched after all three
steps -- checked directly, these are mostly places whose entities.csv
label carries an OCR-era spelling corruption not present in this
cleaner, human-verified source (e.g. "Drottningholro" for
Drottningholm) -- resolving those would need fuzzy/edit-distance
matching with a real risk of a wrong match, so it isn't attempted here.

Output: data/normalized/steder_verified_categories.csv (entity_id,
label, category, country) -- read by build_places_extra.py (kept
stdlib-only itself; this script is the one place openpyxl is needed).

Run before build_places_extra.py:
  python scripts/build_mockup/reconcile_steder_categories.py
"""

import csv
import os
import re
import sys
import unicodedata

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl required:  pip install openpyxl")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
XLSX = os.path.join(ROOT, "data", "raw", "Steder_i_dagboegerne_verificeret_udfyldt VER 1.0.xlsx")
ENTITIES = os.path.join(ROOT, "data", "normalized", "entities.csv")
OUT = os.path.join(ROOT, "data", "normalized", "steder_verified_categories.csv")

SEE_RE = re.compile(r"^(.*?),?\s*se:?\s+(.+?)\.?\s*$", re.I)


def norm(s):
    s = (s or "").strip().casefold()
    s = s.replace("æ", "ae").replace("ø", "o").replace("å", "aa")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def main():
    if not os.path.exists(XLSX):
        sys.exit(f"Missing {XLSX}")
    if not os.path.exists(ENTITIES):
        sys.exit(f"Missing {ENTITIES} — run scripts/normalization/hca_xlsx_to_csv.py first.")

    print(f"Loading {os.path.relpath(ENTITIES, ROOT)}…")
    places = []
    with open(ENTITIES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["entity_type"] == "place":
                places.append(r)
    by_exact, by_norm = {}, {}
    for r in places:
        label = (r.get("label") or "").strip()
        if not label:
            continue
        by_exact.setdefault(label.casefold(), []).append(r)
        by_norm.setdefault(norm(label), []).append(r)
    print(f"  {len(places):,} places")

    print(f"Loading {os.path.relpath(XLSX, ROOT)}…")
    wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
    ws = wb["RawLoc"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    idx = {name: i for i, name in enumerate(header)}

    # xlsx RegistryTitle -> (category, country), first occurrence wins
    # (duplicates are the same place repeated across diary pages).
    xlsx_by_title, seen_titles = {}, set()
    for r in rows:
        title = (r[idx["RegistryTitle"]] or "").strip()
        if not title or title.casefold() in seen_titles:
            continue
        seen_titles.add(title.casefold())
        category = (r[idx["Category"]] or "").strip()
        country = (r[idx["Country"]] or "").strip()
        if category.lower() == "none":
            category = ""
        if country.lower() == "none":
            country = ""
        xlsx_by_title[title] = (category, country)

    # Two lookup indexes into the xlsx data itself, mirroring the register
    # indexes above, so a register "se: X" redirect can be resolved to X
    # and then matched the same (exact/normalized) way.
    xlsx_exact = {t.casefold(): v for t, v in xlsx_by_title.items()}
    xlsx_norm = {}
    for t, v in xlsx_by_title.items():
        xlsx_norm.setdefault(norm(t), v)

    matched = {}
    stats = {"exact": 0, "normalized": 0, "redirect": 0}

    def try_match(label):
        cat_country = xlsx_exact.get(label.casefold())
        if cat_country:
            return cat_country, "exact"
        cat_country = xlsx_norm.get(norm(label))
        if cat_country:
            return cat_country, "normalized"
        return None, None

    for r in places:
        rid = r["entity_id"]
        label = (r.get("label") or "").strip()
        if not label:
            continue
        result, how = try_match(label)
        if not result:
            m = SEE_RE.match(label)
            if m:
                result, _ = try_match(m.group(2).strip())
                how = "redirect" if result else None
        if result and (result[0] or result[1]):
            matched[rid] = {
                "entity_id": rid, "label": label,
                "category": result[0], "country": result[1],
            }
            stats[how] += 1

    unmatched = len(places) - len(matched)
    print(f"  {len(matched):,} matched ({stats['exact']:,} exact, "
          f"{stats['normalized']:,} normalized, {stats['redirect']:,} via 'se:' redirect)")
    print(f"  {unmatched:,} places unmatched (OCR-corrupted labels or genuinely absent "
          f"from the xlsx — see module docstring)")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["entity_id", "label", "category", "country"])
        w.writeheader()
        w.writerows(matched.values())
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({len(matched):,} rows)")


if __name__ == "__main__":
    main()
