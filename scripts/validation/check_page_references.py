#!/usr/bin/env python3
"""
check_page_references.py — do the registers cite pages that exist?

Every register entry cites diary pages, and until now nothing could check
those citations, because no source listed the diaries' actual extent. V0.82's
`diary.csv` holds volumes VI and VII only, so a reference to `IX:454` had
nothing to be wrong against.

V0.94's `3-DIARY-PAGES` changed that: 4,413 pages across all ten volumes. This
validates both sides of the person adoption against it —

  data/normalized/references.csv                the live site's references
  data/parsed/personregister_xi_parsed.tsv      the segmentation's own

— and it finds problems on both, which is the point. A reference to a page
that does not exist is a dead link on the site and a parse error in the data,
and neither was visible before.

Kinds of failure
----------------
  missing      no volume, no page, or a non-numeric page — a malformed row
  out of range page number beyond the last page of that volume. Almost always
               digits that ran together: "I:1841" is a year, "IX:222123" is
               two page numbers concatenated, "V:2456" is "245" and "6"
  unknown vol  a volume outside I-X

Note what this does *not* do: it never repairs. A citation is evidence about a
printed book, and guessing which digits to drop from "IX:222123" would invent
a claim about what Andersen's diary says on a page nobody has checked. The
findings go to a review file for a human, which is the same rule the rest of
this pipeline follows for ambiguity.

Usage:
    python scripts/validation/check_page_references.py
    python scripts/validation/check_page_references.py --write
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "data" / "normalized_v094" / "diary_pages.csv"
LIVE_REFS = ROOT / "data" / "normalized" / "references.csv"
LIVE_ENTS = ROOT / "data" / "normalized" / "entities.csv"
MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
OUT = ROOT / "data" / "review" / "page_reference_problems.csv"

FIELDS = ["side", "entity_id", "label", "vol", "page", "kind", "volume_max"]


def load_pages():
    if not PAGES.exists():
        sys.exit(f"missing {PAGES}\n  run scripts/normalization/hca_v094_to_csv.py first")
    pages, vmax = set(), defaultdict(int)
    with PAGES.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            v, p = r["vol"].strip(), int(r["page"])
            pages.add((v, p))
            vmax[v] = max(vmax[v], p)
    return pages, vmax


def classify(vol, page, pages, vmax):
    """None when the citation is good, else the kind of failure."""
    if not vol or not page or not str(page).isdigit():
        return "missing"
    if vol not in vmax:
        return "unknown vol"
    if (vol, int(page)) in pages:
        return None
    return "out of range" if int(page) > vmax[vol] else "gap in page list"


def check_live(pages, vmax):
    ents = {}
    with LIVE_ENTS.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            ents[r["entity_id"]] = (r.get("entity_type", ""), r.get("label", ""))
    rows, total = [], 0
    with LIVE_REFS.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            total += 1
            vol, page = r["vol"].strip(), r["page"].strip()
            kind = classify(vol, page, pages, vmax)
            if kind:
                etype, label = ents.get(r["entity_id"], ("?", ""))
                rows.append({"side": f"live/{etype}", "entity_id": r["entity_id"],
                             "label": label[:60], "vol": vol, "page": page,
                             "kind": kind, "volume_max": vmax.get(vol, "")})
    return rows, total


def check_master(pages, vmax):
    rows, total = [], 0
    with MASTER.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            for tok in (r.get("11_references_parsed") or "").split(";"):
                tok = tok.strip()
                if not tok:
                    continue
                total += 1
                vol, _, page = tok.rpartition(":")
                vol, page = vol.strip(), page.strip()
                kind = classify(vol, page, pages, vmax)
                if kind:
                    name = f"{r.get('03_surname','')}, {r.get('04_given_names','')}".strip(", ")
                    rows.append({"side": "segmentation", "entity_id": r.get("00_person_id", ""),
                                 "label": name[:60], "vol": vol, "page": page,
                                 "kind": kind, "volume_max": vmax.get(vol, "")})
    return rows, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true",
                    help=f"write findings to {OUT.relative_to(ROOT)}")
    args = ap.parse_args()

    pages, vmax = load_pages()
    print(f"  page list: {len(pages):,} pages, volumes "
          f"{', '.join(sorted(vmax, key=lambda v: vmax[v], reverse=True)[:1])}…"
          f" ({len(vmax)} volumes)")

    live, live_total = check_live(pages, vmax)
    master, master_total = check_master(pages, vmax)

    for label, bad, total in (("live references.csv", live, live_total),
                              ("segmentation register", master, master_total)):
        pct = len(bad) / total * 100 if total else 0
        print(f"\n  {label}: {total:,} citations, {len(bad):,} invalid ({pct:.2f} %)")
        for kind, n in Counter(r["kind"] for r in bad).most_common():
            print(f"     {kind:<18} {n:,}")
        worst = Counter((r["vol"], r["page"]) for r in bad
                        if r["kind"] == "out of range").most_common(4)
        for (v, p), n in worst:
            print(f"       {v}:{p:<9} cited {n}×   (volume ends at {vmax.get(v)})")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(live + master)
        print(f"\n  wrote {OUT.relative_to(ROOT)}  ({len(live) + len(master):,} rows)")

    print("\n  Nothing was repaired. A citation points at a printed page; "
          "guessing\n  which digits to drop would invent a claim about the book.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
