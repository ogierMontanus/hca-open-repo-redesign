#!/usr/bin/env python3
"""
build_person_crosswalk.py — bridge the segmented register to the live person ids.

The site's persons come from the V0.82 workbook and are identified by `Reg…`
ids, which its URLs cite (`persons.html?reg=Reg0030070`). The segmented
register — the better data, with ~15 % more page references — carries no
workbook identifier at all. Adopting it therefore needs a bridge, and this
builds one.

    data/parsed/personregister_xi_parsed.tsv   HCAP… (minted here)
                        ↕
    data/normalized/entities.csv               Reg…  (the live ids)

Method
------
The same one the coverage measurement uses, because it is the one that was
calibrated against this corpus (see `scripts/validation/compare_to_reference.py`):

  1. Fold the name — NFKD-strip diacritics, remove every year parenthesis,
     fold punctuation, upper-case.
  2. Match folded name to folded label. Where that is unique, done.
  3. Where it is not — the register is full of repeated surnames — use the
     full `(vol, page)` reference signature to choose between candidates.
     Two entries that cite exactly the same pages are the same person.
  4. Where the name matches nothing, try the signature alone: a person whose
     name was re-segmented still cites the same pages.

Every row is emitted with the tier that matched it, so a consumer can decide
how much to trust each one rather than being handed an undifferentiated
"match". Nothing is guessed: a candidate set that neither the name nor the
signature resolves is written out as `ambiguous`, not picked from.

Outputs
-------
  data/curated/person_id_crosswalk.csv    HCAP ↔ Reg, with tier and evidence
  data/review/person_crosswalk_review.csv the unmatched and the ambiguous

The crosswalk is curated, not generated: once a human resolves an ambiguity
the answer belongs in the committed file, and re-running must not discard it.
So existing rows are carried unless `--refresh` is passed.

Usage:
    python scripts/segmentation/build_person_crosswalk.py
    python scripts/segmentation/build_person_crosswalk.py --refresh
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validation"))
from compare_to_reference import fold_name, parse_our_refs  # noqa: E402

MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
ENTITIES = ROOT / "data" / "normalized" / "entities.csv"
REFERENCES = ROOT / "data" / "normalized" / "references.csv"
OUT = ROOT / "data" / "curated" / "person_id_crosswalk.csv"
REVIEW = ROOT / "data" / "review" / "person_crosswalk_review.csv"

FIELDS = ["person_id", "reg_id", "tier", "register_name", "live_label",
          "shared_pages", "note"]


def load_master():
    with MASTER.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    out = []
    for r in rows:
        if r.get("02_entry_type") == "krydshenvisning":
            continue
        surname = (r.get("03_surname") or "").strip()
        given = (r.get("04_given_names") or "").strip()
        name = f"{surname}, {given}".strip(", ") if given else surname
        out.append({
            "id": r.get("00_person_id", ""),
            "name": name,
            "core": fold_name(name),
            "sig": parse_our_refs(r.get("11_references_parsed", "")),
        })
    return out


def load_live():
    persons = {}
    with ENTITIES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("entity_type") != "person":
                continue
            persons[r["entity_id"]] = {
                "id": r["entity_id"], "label": r.get("label", ""),
                "core": fold_name(r.get("label", "")), "sig": set(),
            }
    with REFERENCES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            p = persons.get(r["entity_id"])
            if p is not None:
                p["sig"].add((r["vol"], r["page"]))
    for p in persons.values():
        p["sig"] = frozenset(p["sig"])
    return persons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--refresh", action="store_true",
                    help="rebuild every row, discarding human resolutions")
    args = ap.parse_args()

    master = load_master()
    live = load_live()
    if not any(m["id"] for m in master):
        sys.exit("master has no 00_person_id — run mint_person_ids.py first")

    by_core = defaultdict(list)
    by_sig = defaultdict(list)
    for p in live.values():
        by_core[p["core"]].append(p)
        if p["sig"]:
            by_sig[p["sig"]].append(p)

    kept = {}
    if OUT.exists() and not args.refresh:
        with OUT.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("note") == "human":
                    kept[r["person_id"]] = r

    rows, review = [], []
    tiers = defaultdict(int)
    for m in master:
        if m["id"] in kept:
            rows.append(kept[m["id"]]); tiers["human (carried)"] += 1
            continue

        cands = by_core.get(m["core"], [])
        tier = reg = label = None
        shared = 0

        if len(cands) == 1:
            tier, reg, label = "exact_name", cands[0]["id"], cands[0]["label"]
            shared = len(m["sig"] & cands[0]["sig"])
        elif len(cands) > 1:
            exact = [c for c in cands if m["sig"] and c["sig"] == m["sig"]]
            if len(exact) == 1:
                tier, reg, label = "name_and_signature", exact[0]["id"], exact[0]["label"]
                shared = len(m["sig"])
            else:
                best = max(cands, key=lambda c: len(m["sig"] & c["sig"]))
                overlap = len(m["sig"] & best["sig"])
                if overlap and sum(1 for c in cands
                                   if len(m["sig"] & c["sig"]) == overlap) == 1:
                    tier, reg, label = "name_and_overlap", best["id"], best["label"]
                    shared = overlap
                else:
                    tier = "ambiguous"
        else:
            sig_hits = by_sig.get(m["sig"], []) if m["sig"] else []
            if len(sig_hits) == 1:
                tier, reg = "signature_only", sig_hits[0]["id"]
                label, shared = sig_hits[0]["label"], len(m["sig"])
            else:
                tier = "none"

        row = {"person_id": m["id"], "reg_id": reg or "", "tier": tier,
               "register_name": m["name"], "live_label": label or "",
               "shared_pages": shared, "note": ""}
        rows.append(row)
        tiers[tier] += 1
        if tier in ("ambiguous", "none"):
            review.append({**row, "note": f"{len(cands)} name candidate(s)"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(review)

    total = len(rows)
    resolved = sum(v for k, v in tiers.items() if k not in ("ambiguous", "none"))
    print(f"  master person entries {total:,}   live person entries {len(live):,}")
    for t, n in sorted(tiers.items(), key=lambda kv: -kv[1]):
        print(f"     {t:<22} {n:>6,}  ({n/total*100:4.1f} %)")
    print(f"  resolved {resolved:,} / {total:,}  ({resolved/total*100:.1f} %)")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    print(f"  wrote {REVIEW.relative_to(ROOT)}  ({len(review):,} to review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
