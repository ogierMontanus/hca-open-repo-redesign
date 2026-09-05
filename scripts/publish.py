#!/usr/bin/env python3
"""
publish.py — assemble the prepared-data package that hca-open-repo builds from.

This is the contract between the two repositories. Everything listed in
INTERFACE below is a file the publication repo's build stages read; nothing
else in this repository crosses the boundary. Adding a file here (and to
docs/interface.md) is the deliberate act that widens the contract.

    python scripts/publish.py                 # write dist/
    python scripts/publish.py --into ../hca-open-repo
                                              # also copy dist/ into a
                                              # publication-repo checkout
    python scripts/publish.py --check --into ../hca-open-repo
                                              # report drift, change nothing

`_source.json` is written alongside the data: it records the raw sources this
package was derived from (filename + SHA-256), so the publication repo can
state its provenance without holding the raw workbooks itself.
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

# (path relative to repo root, required?)
INTERFACE = [
    # ── star-shaped core, from the canonical workbook (stage 1a) ──────────
    ("data/normalized/entities.csv", True),
    ("data/normalized/diary.csv", True),
    ("data/normalized/references.csv", True),
    # ── geocoded travel add-on (stage 1b) ────────────────────────────────
    ("data/normalized/rejser.tsv", False),
    ("data/normalized/rejser_journeys.tsv", False),
    # ── enrichment layers (stages 1c–1h) ─────────────────────────────────
    ("data/normalized/sv14_places_reconciled.csv", False),
    ("data/normalized/work_languages.csv", False),
    ("data/normalized/person_ethnic_descriptors.csv", False),
    ("data/normalized/person_gender.csv", False),
    ("data/normalized/person_role.csv", False),
    ("data/normalized/kb_diary_links.csv", False),
    ("data/normalized/steder_verified_categories.csv", False),
    # ── timeline source for the Tidslinje view ───────────────────────────
    ("data/normalized_v092/timeline.csv", False),
    # ── register segmentation (human-reviewed, committed as data) ────────
    ("data/parsed/music_register_parsed.tsv", False),
    ("data/parsed/non_fiction_parsed.tsv", False),
    ("data/parsed/novels_plays_tales_parsed.tsv", False),
    # ── curated authority files the build reads directly ─────────────────
    ("data/curated/works_wikidata.csv", False),
    ("data/curated/persons_wikidata.csv", False),
    ("data/curated/person_entity_types.tsv", False),
    ("data/curated/breve_person_crosswalk.csv", False),
    ("data/curated/ethnic_adjectives_da.csv", False),
    ("data/curated/nation_place_labels_da.csv", False),
    ("data/curated/nation_umbrellas_da.csv", False),
    ("data/curated/steder_country_to_nation_da.csv", False),
]

# Raw sources recorded in _source.json so the publication repo keeps its
# provenance without shipping the workbooks.
PROVENANCE = [
    ("source_xlsx", "data/raw/HCA REPOSITORY V0.82/HCA-Repository V0.82.xlsx"),
    ("source_rejser_htm", "data/raw/Rejser_HCA_X.htm"),
    ("source_sv14_xml", "data/raw/SV14_places.xml"),
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_source_json() -> dict:
    payload = {
        "prepared_by": "HCA-Diary-data-cleaning",
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {},
    }
    for key, rel in PROVENANCE:
        p = ROOT / rel
        if p.exists():
            payload["sources"][key] = {"name": p.name, "sha256": sha256_of(p)}
        else:
            payload["sources"][key] = None
    return payload


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--into", metavar="REPO",
                    help="publication-repo checkout to copy dist/ into")
    ap.add_argument("--check", action="store_true",
                    help="report differences against --into, change nothing")
    args = ap.parse_args()

    missing = []
    files = []
    for rel, required in INTERFACE:
        if (ROOT / rel).exists():
            files.append(rel)
        elif required:
            missing.append(rel)
        else:
            print(f"  [skip] {rel} (optional, not present)")
    if missing:
        sys.exit("Missing required interface file(s):\n  " + "\n  ".join(missing))

    if args.check:
        if not args.into:
            sys.exit("--check needs --into")
        target = Path(args.into).resolve()
        drift = 0
        for rel in files:
            a, b = ROOT / rel, target / rel
            if not b.exists():
                print(f"  [absent]  {rel}")
                drift += 1
            elif a.read_bytes().replace(b"\r\n", b"\n") != b.read_bytes().replace(b"\r\n", b"\n"):
                print(f"  [differs] {rel}")
                drift += 1
        print(f"\n{drift} of {len(files)} interface file(s) differ in {target}.")
        return

    if DIST.exists():
        shutil.rmtree(DIST)
    for rel in files:
        dst = DIST / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    src_json = DIST / "data" / "normalized" / "_source.json"
    src_json.write_text(json.dumps(build_source_json(), indent=2) + "\n",
                        encoding="utf-8")
    total = sum((DIST / rel).stat().st_size for rel in files)
    print(f"Wrote dist/ — {len(files)} interface file(s), {total / 1e6:.1f} MB, "
          f"plus data/normalized/_source.json")

    if args.into:
        target = Path(args.into).resolve()
        if not (target / "scripts").is_dir():
            sys.exit(f"--into does not look like a repo checkout: {target}")
        for rel in files + ["data/normalized/_source.json"]:
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DIST / rel, dst)
        print(f"Copied into {target}")


if __name__ == "__main__":
    main()
