#!/usr/bin/env python3
"""
reconcile_sv14_geo.py
----------------------
Reconciles A) data/raw/SV14_places.xml (TEI place-list for diary volume 14,
English/endonym spelling, geocoded) against B) the Danish STED-REGISTER
(data/normalized/entities.csv, entity_type == 'place') to fill in
coordinates for B entries that do not already have them.

Entries in B that already resolve to coordinates via the existing
rejser.tsv gazetteer (see build_places_extra.py) are left untouched —
this script only targets the remaining gap.

Matching strategy, in order:
  1. Direct match — fold both B's label and every placeName variant in A
     (main/sort/variant) to a diacritic- and case-insensitive key and look
     for an exact hit.
  2. Alias match — B's label is translated via the Destination_DA ->
     Destination_EN mapping already curated in data/normalized/rejser.tsv
     (e.g. København -> Copenhagen), then the translated name is matched
     against A the same way. This mainly helps the handful of DA/EN pairs
     that rejser.tsv knows about but that don't themselves carry
     coordinates.

A single fold-key in A that maps to two or more genuinely different
coordinate pairs (e.g. "Lilienstein" exists both in Saxony and, per a
GeoNames mis-tag, in South Africa) is ambiguous and is never auto-applied;
it is written to the ambiguous-review CSV instead so a human decides.

Writes:
  data/normalized/sv14_places_reconciled.csv  — entity_id -> matched geo,
                                                 consumed by
                                                 build_places_extra.py
  data/normalized/sv14_places_ambiguous.csv   — same-name/different-coords
                                                 collisions, for manual review

Stdlib only.
"""

import csv
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SV14_XML  = os.path.join(ROOT, "data", "raw", "SV14_places.xml")
ENTITIES  = os.path.join(ROOT, "data", "normalized", "entities.csv")
REJSER    = os.path.join(ROOT, "data", "normalized", "rejser.tsv")
OUT       = os.path.join(ROOT, "data", "normalized", "sv14_places_reconciled.csv")
AMBIGUOUS = os.path.join(ROOT, "data", "normalized", "sv14_places_ambiguous.csv")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def foldkey(s: str) -> str:
    """Diacritic- and case-insensitive match key. 'Deià' / 'Deya' /
    'DEYA' all fold to the same key; æ/ø/å pass through unchanged since
    they have no NFD decomposition."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\s+", " ", s.strip())
    return s.casefold()


def load_sv14_index(path: str):
    """Returns (name_index, resolved) where name_index[key] is every
    (name, lat, lon, xml_id) seen under that fold-key, and resolved[key]
    is the single (name, lat, lon, xml_id) tuple to use — or None if the
    key is ambiguous (genuinely different coordinates under one name)."""
    if not os.path.exists(path):
        return {}, {}
    tree = ET.parse(path)
    root = tree.getroot()
    name_index = defaultdict(list)
    for place in root.findall(".//tei:listPlace/tei:place", TEI_NS):
        geo_el = place.find(".//tei:location/tei:geo", TEI_NS)
        if geo_el is None or not (geo_el.text or "").strip():
            continue
        try:
            lat_s, lon_s = geo_el.text.strip().split()
            lat, lon = round(float(lat_s), 5), round(float(lon_s), 5)
        except ValueError:
            continue
        xml_id = place.get(XML_ID) or ""
        geonames_url = ""
        wiki_url = ""
        for ptr in place.findall("tei:ptr", TEI_NS):
            target = ptr.get("target") or ""
            if ptr.get("type") == "geonames":
                geonames_url = target
            elif ptr.get("type") == "info" and "wikipedia" in target:
                wiki_url = target
        names = {(pn.text or "").strip() for pn in place.findall("tei:placeName", TEI_NS)}
        for name in names:
            if not name:
                continue
            name_index[foldkey(name)].append((name, lat, lon, xml_id, geonames_url, wiki_url))

    resolved = {}
    for key, entries in name_index.items():
        distinct_coords = {(e[1], e[2]) for e in entries}
        resolved[key] = entries[0] if len(distinct_coords) == 1 else None
    return name_index, resolved


def load_rejser_da_en(path: str):
    """Returns (da_to_en, existing_keys). da_to_en maps a casefolded Danish
    destination name to its English counterpart (first occurrence wins).
    existing_keys is every casefolded Destination_DA/EN/ORG value that
    already carries coordinates in rejser.tsv — these B entries are out
    of scope here (build_places_extra.py already geocodes them)."""
    da_to_en = {}
    existing_keys = set()
    if not os.path.exists(path):
        return da_to_en, existing_keys
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                float(row.get("Latitude") or "")
                float(row.get("Longitude") or "")
            except ValueError:
                continue
            da = (row.get("Destination_DA") or "").strip()
            en = (row.get("Destination_EN") or "").strip()
            org = (row.get("Destination_ORG") or "").strip()
            if da and da.casefold() not in da_to_en:
                da_to_en[da.casefold()] = en
            for v in (da, en, org):
                if v:
                    existing_keys.add(v.casefold())
    return da_to_en, existing_keys


def load_b_places(path: str):
    if not os.path.exists(path):
        sys.exit(f"Missing {path}")
    with open(path, encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["entity_type"] == "place"]


def main() -> None:
    print(f"Loading {os.path.relpath(SV14_XML, ROOT)}…")
    name_index, resolved = load_sv14_index(SV14_XML)
    ambiguous_keys = {k for k, v in resolved.items() if v is None}
    print(f"  {len(name_index):,} distinct place names, "
          f"{len(ambiguous_keys):,} ambiguous (name reused with different coordinates)")

    print(f"Loading {os.path.relpath(REJSER, ROOT)} for DA->EN aliases…")
    da_to_en, existing_geo_keys = load_rejser_da_en(REJSER)
    print(f"  {len(da_to_en):,} DA->EN pairs, {len(existing_geo_keys):,} labels already geocoded")

    print(f"Loading {os.path.relpath(ENTITIES, ROOT)}…")
    b_places = load_b_places(ENTITIES)
    print(f"  {len(b_places):,} places in STED-REGISTER")

    matched = []
    ambiguous_hits = []
    already_had_coords = 0
    unmatched = 0

    for r in b_places:
        entity_id = r["entity_id"]
        label = (r.get("label") or "").strip()
        if not label:
            continue
        if label.casefold() in existing_geo_keys:
            already_had_coords += 1
            continue

        key = foldkey(label)
        method = "direct"
        hit_key = key if key in resolved else None

        if hit_key is None:
            alias_en = da_to_en.get(label.casefold())
            if alias_en:
                alias_key = foldkey(alias_en)
                if alias_key in resolved:
                    hit_key = alias_key
                    method = "via_rejser_alias"

        if hit_key is None:
            unmatched += 1
            continue

        if resolved[hit_key] is None:
            ambiguous_hits.append((entity_id, label, name_index[hit_key]))
            continue

        name, lat, lon, xml_id, geonames_url, wiki_url = resolved[hit_key]
        matched.append({
            "entity_id": entity_id,
            "label_da": label,
            "matched_name_en": name,
            "match_method": method,
            "lat": lat,
            "lon": lon,
            "sv14_xml_id": xml_id,
            "geonames_url": geonames_url,
            "wiki_url": wiki_url,
        })

    print(f"  already had coordinates (skipped): {already_had_coords:,}")
    print(f"  matched via SV14: {len(matched):,} "
          f"(direct: {sum(1 for m in matched if m['match_method'] == 'direct'):,}, "
          f"via alias: {sum(1 for m in matched if m['match_method'] == 'via_rejser_alias'):,})")
    print(f"  ambiguous (left for manual review, not applied): {len(ambiguous_hits):,}")
    print(f"  still unmatched: {unmatched:,}")

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "entity_id", "label_da", "matched_name_en", "match_method",
            "lat", "lon", "sv14_xml_id", "geonames_url", "wiki_url",
        ])
        w.writeheader()
        w.writerows(matched)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")

    with open(AMBIGUOUS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "label_da", "candidates"])
        for entity_id, label, entries in ambiguous_hits:
            candidates = " | ".join(
                f"{name} ({lat}, {lon}) [{xml_id}]" for name, lat, lon, xml_id, _, _ in entries
            )
            w.writerow([entity_id, label, candidates])
    print(f"  wrote {os.path.relpath(AMBIGUOUS, ROOT)}")


if __name__ == "__main__":
    main()
