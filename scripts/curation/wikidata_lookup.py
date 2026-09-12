#!/usr/bin/env python3
"""
wikidata_lookup.py
-------------------
Proposes Wikidata Q-numbers and Commons hero-image filenames for works in
the register, by artist. It is a PROPOSAL tool, not an auto-writer: it
never edits work data directly, and nothing it outputs is treated as fact
until a human confirms it.

Why a review step, not a straight write: CLAUDE.md's Faktakontrol rule
exists because an earlier session shipped 6 wrong Wikidata Q-numbers out of
8 on pure memory-based guesses. This script doesn't guess from memory
either — it queries Wikidata live — but a live query can still return the
WRONG right-shaped answer: an artist painted the same subject more than
once (Murillo alone has 10+ "Immaculate Conception" canvases in different
collections), so a title-similarity match can land on a real Wikidata item
that just isn't the specific painting this register's title refers to. See
docs/data-model/billedkunst-artist-extraction.md for the general shape of
this problem in this register's titles. Confirm every row against its
wikidata_url — specifically the collection/location — before trusting it.

What it does:
  1. Resolves a creator name to a Wikidata Q-id (wbsearchentities), or
     accepts one directly via --creator-qid.
  2. Fetches every Wikidata item with that creator (P170) via the Wikidata
     Query Service, with its Commons image (P18) and collection (P195)
     when present.
  3. Loads this register's own works whose WORKS_EXTRA.author matches
     --author-match, and token-overlap-scores each against every Wikidata
     candidate's label.
  4. Writes one row per local work to a review CSV: its best-scoring
     candidate (if any), the Wikidata URL to go check, and the collection
     name — specifically so a mismatched collection (this register says
     "Academia, Sevilla", Wikidata says "Prado") is visible at a glance
     without opening every link.

What it deliberately does NOT do: write to data/curated/works_wikidata.csv
itself. Promote a row there — by hand, after checking the URL — only once
you've confirmed it's the right painting. build_works_extra.py picks up
that file automatically on the next build.

Network: talks to www.wikidata.org and query.wikidata.org directly, using
only the standard library (no new dependency). This project's own
development sandbox blocks both hosts at the network-egress layer — if
this script hangs or raises a URLError there, that's why; run it from a
machine with a normal, unrestricted internet connection instead (falling
back to manual WebSearch-based verification, domain-filtered to
wikidata.org, is what CLAUDE.md's Wikidata-lookup procedure documents for
that case).

Usage:
    python scripts/curation/wikidata_lookup.py "Bartolomé Esteban Murillo" \\
        --author-match Murillo --out review_murillo.csv

    python scripts/curation/wikidata_lookup.py --creator-qid Q192062 \\
        --author-match Murillo --out review_murillo.csv --min-score 0.2
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built register cards from the publication repo (hca-open-repo). They are a
# BUILD artefact, so they live in the other repository; point
# HCA_MOCKUP_DATA_DIR at its mockup/data/ folder, or keep the two repos as
# siblings and the default below finds it.
MOCKUP_DATA_DIR = Path(
    os.environ.get("HCA_MOCKUP_DATA_DIR", ROOT.parent / "hca-open-repo" / "mockup" / "data")
)
WORKS_EXTRA_JS = MOCKUP_DATA_DIR / "works-extra.js"

USER_AGENT = (
    "HCA-Open-Repository/0.1 "
    "(https://github.com/ogierMontanus/hca-open-repo; enrichment script)"
)
WD_API = "https://www.wikidata.org/w/api.php"
WDQS_SPARQL = "https://query.wikidata.org/sparql"

PAINTING_SPARQL = """
SELECT ?item ?itemLabel ?image ?collectionLabel WHERE {{
  ?item wdt:P170 wd:{qid}.
  OPTIONAL {{ ?item wdt:P18 ?image. }}
  OPTIONAL {{ ?item wdt:P195 ?collection. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,da,es". }}
}}
"""


def _http_get_json(url, params, accept):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}", headers={"User-Agent": USER_AGENT, "Accept": accept}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_creator_qid(name):
    """wbsearchentities lookup for a creator name. Returns the top hit's
    Q-id plus the full candidate list — printed by the caller rather than
    trusted silently, since a common name can resolve to the wrong person
    (a namesake, a Wikidata item for a painting rather than the painter)."""
    data = _http_get_json(
        WD_API,
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "type": "item",
            "limit": 8,
            "format": "json",
        },
        "application/json",
    )
    hits = data.get("search", [])
    if not hits:
        return None, []
    return hits[0]["id"], hits


def fetch_works_by_creator(qid):
    """Every Wikidata item with creator (P170) = qid, with its Commons
    image filename and collection label when present. One SPARQL call —
    even a prolific painter's catalogue is a few hundred rows, well within
    a single query's limits."""
    query = PAINTING_SPARQL.format(qid=qid)
    data = _http_get_json(
        WDQS_SPARQL, {"query": query, "format": "json"}, "application/sparql-results+json"
    )
    out = []
    for row in data["results"]["bindings"]:
        item_qid = row["item"]["value"].rsplit("/", 1)[-1]
        label = row.get("itemLabel", {}).get("value", "")
        image = row.get("image", {}).get("value", "")
        collection = row.get("collectionLabel", {}).get("value", "")
        filename = urllib.parse.unquote(image.rsplit("/", 1)[-1]) if image else ""
        out.append(
            {"qid": item_qid, "label": label, "image_filename": filename, "collection": collection}
        )
    return out


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def load_local_titles(author_match):
    """Titles from WORKS_EXTRA whose author field contains author_match
    (case-insensitive substring — 'Murillo' matches this register's short
    form of a name Wikidata may record in full)."""
    if not WORKS_EXTRA_JS.exists():
        sys.exit(
            f"{WORKS_EXTRA_JS} not found — run "
            "scripts/build_mockup/build_works_extra.py first."
        )
    text = WORKS_EXTRA_JS.read_text(encoding="utf-8")
    data = json.loads(text.split("const WORKS_EXTRA = ", 1)[1].rstrip("\n").rstrip(";"))
    needle = author_match.lower()
    return [
        (rid, w.get("title", ""))
        for rid, w in data.items()
        if needle in (w.get("author") or "").lower()
    ]


def score(local_title, wd_label):
    """Token-overlap score (Jaccard on word sets) — a coarse pre-filter for
    a human to look at, not a decision function. Local titles are Danish
    paraphrases or subject descriptions ("Den gode Hyrde"); Wikidata labels
    are usually the English or Spanish canonical title ("The Good
    Shepherd"/"El Buen Pastor") — the two vocabularies barely overlap even
    for a correct match, so a low score is expected and not itself a
    rejection signal. It only orders candidates within one local title."""
    a, b = set(_norm(local_title).split()), set(_norm(wd_label).split())
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("creator_name", nargs="?", help="Creator name to search Wikidata for")
    ap.add_argument("--creator-qid", help="Skip the name search, use this Q-id directly")
    ap.add_argument(
        "--author-match", required=True, help="Substring to match against WORKS_EXTRA.author"
    )
    ap.add_argument("--out", required=True, help="Review CSV to write")
    ap.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Only propose a candidate when its score is at least this (0 keeps every "
        "local work in the output, matched or not, for a complete review list)",
    )
    args = ap.parse_args()

    try:
        if args.creator_qid:
            qid = args.creator_qid
        else:
            if not args.creator_name:
                sys.exit("Provide a creator name or --creator-qid")
            qid, candidates = find_creator_qid(args.creator_name)
            if not qid:
                sys.exit(f"No Wikidata match for {args.creator_name!r}")
            print(f"Creator search for {args.creator_name!r} -> using {qid} ({candidates[0].get('label','')}).")
            if len(candidates) > 1:
                print("Other candidates, in case this is the wrong person:")
                for c in candidates[1:]:
                    print(f"  {c['id']}  {c.get('label','')} — {c.get('description','')}")

        print(f"Fetching works with creator={qid} from the Wikidata Query Service…")
        wd_works = fetch_works_by_creator(qid)
        print(f"  {len(wd_works)} items found ({sum(1 for w in wd_works if w['image_filename'])} with an image)")
    except urllib.error.URLError as e:
        sys.exit(
            f"Network request failed ({e}). This script needs a direct connection to "
            "www.wikidata.org / query.wikidata.org — see the module docstring if you're "
            "running inside this project's sandboxed dev environment."
        )

    local = load_local_titles(args.author_match)
    print(f"Local register: {len(local)} works with author matching {args.author_match!r}")

    rows = []
    for rid, title in local:
        best = None
        for w in wd_works:
            if not w["image_filename"]:
                continue
            s = score(title, w["label"])
            if best is None or s > best[0]:
                best = (s, w)
        if best and best[0] >= args.min_score:
            s, w = best
            rows.append(
                {
                    "rid": rid,
                    "local_title": title,
                    "score": round(s, 2),
                    "wd_qid": w["qid"],
                    "wd_label": w["label"],
                    "collection": w["collection"],
                    "image_filename": w["image_filename"],
                    "wikidata_url": f"https://www.wikidata.org/wiki/{w['qid']}",
                }
            )
        else:
            rows.append(
                {
                    "rid": rid,
                    "local_title": title,
                    "score": "",
                    "wd_qid": "",
                    "wd_label": "",
                    "collection": "",
                    "image_filename": "",
                    "wikidata_url": "",
                }
            )

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rid", "local_title", "score", "wd_qid", "wd_label",
                "collection", "image_filename", "wikidata_url",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for r in rows if r["wd_qid"])
    print(f"Wrote {out_path} — {matched}/{len(rows)} candidate matches.")
    print(
        "\nThis is a PROPOSAL list, not a verified one. For each row worth keeping: open "
        "wikidata_url, confirm the collection matches this register's title (not just the "
        "subject), and confirm the image is the actual painting — not a sketch, detail crop, "
        "or a later copy misattributed to the same creator. Only then add rid/wd/"
        "image_filename to data/curated/works_wikidata.csv, with a one-line note on how you "
        "confirmed it (see the existing rows there for the expected format)."
    )


if __name__ == "__main__":
    main()
