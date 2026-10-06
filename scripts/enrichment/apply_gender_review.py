#!/usr/bin/env python3
"""
apply_gender_review.py — stage 1f'
----------------------------------
Lægger det gennemsete køn (data/curated/person_gender_reviewed.csv) over
parserens output i data/normalized/person_gender.csv. Skal køre efter
parse_person_gender.py (stage 1f), som ellers overskriver resultatet.

    Mandlig / Kvindelig / Endnu ubestemt   erstatter parserens værdi
    Irrelevant, krydshenvisning            rækken udelades: uden række får
                                           posten intet køn, og Køn-facetten
                                           springer den over
    Irrelevant, øvrige                     »Andet (især firmaer/slægter/
                                           øvrige grupper)«: firma, slægt,
                                           ægtepar, familie, gruppe, dyr

Personer, som gennemsynet ikke dækker (findes på hjemmesiden, men ikke i den
rettede segmentering), beholder parserens værdi.

Skemaet er uændret, så publikationsrepoets build_persons_extra.py læser
filen som før. »indikatorer« får metoden fra gennemsynet foran parserens
indikatorer; »forklaring« får gennemsynets grundlag.

Kør:
    python scripts/enrichment/apply_gender_review.py
"""

import csv
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENDER = os.path.join(ROOT, "data", "normalized", "person_gender.csv")
REVIEWED = os.path.join(ROOT, "data", "curated", "person_gender_reviewed.csv")

OTHER = "Andet (især firmaer/slægter/øvrige grupper)"


def is_cross_ref(rv):
    return rv["grundlag"].startswith("krydshenvisning")


def main():
    with open(GENDER, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())
    with open(REVIEWED, encoding="utf-8", newline="") as f:
        reviewed = {r["entity_id"]: r for r in csv.DictReader(f)}

    before = Counter(r["koen"] for r in rows)
    out, changed, dropped = [], 0, 0
    for r in rows:
        rv = reviewed.get(r["entity_id"])
        if rv is None:
            out.append(r)
            continue
        if rv["koen"] == "Irrelevant" and is_cross_ref(rv):
            dropped += 1
            continue
        koen = OTHER if rv["koen"] == "Irrelevant" else rv["koen"]
        if koen != r["koen"]:
            changed += 1
        r = dict(r)
        r["koen"] = koen
        if rv["confidence"]:
            r["confidence"] = rv["confidence"]
        parser_inds = r["indikatorer"].split(" | ", 1)[1] if r["indikatorer"].startswith(
            "gennemsyn:") and " | " in r["indikatorer"] else (
            "" if r["indikatorer"].startswith("gennemsyn:") else r["indikatorer"])
        r["indikatorer"] = " | ".join(x for x in (f"gennemsyn: {rv['metode']}", parser_inds) if x)
        r["forklaring"] = rv["grundlag"] or r["forklaring"]
        out.append(r)

    with open(GENDER, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    after = Counter(r["koen"] for r in out)
    print(f"  {len(reviewed):,} gennemsete personer; {changed:,} fik nyt køn, "
          f"{dropped:,} krydshenvisninger udeladt")
    for k in ("Mandlig", "Kvindelig", "Endnu ubestemt", OTHER):
        print(f"  {k:16s} {before[k]:6,} → {after[k]:6,}")
    print(f"  skrev {os.path.relpath(GENDER, ROOT)} ({len(out):,} rækker)")


if __name__ == "__main__":
    main()
