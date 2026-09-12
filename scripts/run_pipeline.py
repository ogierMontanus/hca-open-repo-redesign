#!/usr/bin/env python3
"""
run_pipeline.py — run the data-preparation pipeline end to end.

This repository owns everything between the raw sources and the prepared
data that the publication repository (hca-open-repo) builds its website
from:

    data/raw/  →  [this pipeline]  →  data/normalized/ + data/parsed/
                                       + data/curated/
                                   →  scripts/publish.py  →  dist/
                                   →  hca-open-repo build

Stages
------
The automated stages below are the ones that regenerate deterministically
from the raw sources on every run. They are the stages the publication
repo used to run itself, as stages 1a–1e of its own build_all.py.

  1a  ingest   normalization/hca_xlsx_to_csv.py     canonical workbook →
                                                    entities/diary/references
  1a' ingest   normalization/hca_v092_to_csv.py     the V0.92 nine-workbook
                                                    release (optional; its
                                                    output feeds the timeline
                                                    view only)
  1b  ingest   enrichment/parse_rejser_htm.py       geocoded travel table
  1c  reconcile enrichment/reconcile_sv14_geo.py    TEI place-list → coords
  1d  enrich   enrichment/detect_work_language.py   probable work language
  1e  enrich   parsers/parse_person_ethnic_descriptors.py  nationality adjectives
  1f  enrich   parsers/parse_person_gender.py       gender facet
  1g  ingest   enrichment/build_kb_links.py         Det Kgl. Bibliotek page links
  1h  reconcile enrichment/reconcile_steder_categories.py  verified place categories

Stages NOT run here
-------------------
The register parsers and the person-register segmentation scripts under
scripts/parsers/ are *not* part of this automated run. They are
one-shot, human-in-the-loop cleaning passes whose results were reviewed
and are committed as data (data/parsed/*.tsv, data/curated/*). Re-running
them blindly would overwrite reviewed decisions. See docs/pipeline.md for
the order they were applied in and how to re-derive a file deliberately.

Two scripts (parsers/parse_person_role.py and the correspondence matchers)
read the publication repo's built *-extra.js cards, so they need a built
hca-open-repo checkout; point HCA_MOCKUP_DATA_DIR at its mockup/data/.
They are likewise excluded from the automated run.

Usage
-----
    python scripts/run_pipeline.py                # all automated stages
    python scripts/run_pipeline.py --only 1d      # one stage
    python scripts/run_pipeline.py --list         # show stages
    python scripts/run_pipeline.py --skip-v092    # skip the slow V0.92 ingest

Optional stages mirror the publication repo's continue-on-error steps:
their outputs are committed, so a machine missing `lingua` still leaves
the previous extraction in place instead of emptying a facet.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (id, label, script relative to repo root, argv tail, optional?)
STAGES = [
    ("1a", "canonical workbook -> normalised CSVs",
     "scripts/normalization/hca_xlsx_to_csv.py",
     ["--input", "data/raw/HCA REPOSITORY V0.82"], False),
    ("1a'", "V0.92 release -> normalised CSVs (timeline source)",
     "scripts/normalization/hca_v092_to_csv.py", [], True),
    # Read-only verification surface, exactly as 1a' is. Nothing downstream
    # reads data/normalized_v094/ -- it exists so adopting V0.94 can be argued
    # from measurements rather than from its release notes. The report it
    # writes is the point of the stage. See docs/v094-structural-diff.md.
    ("1a''", "V0.94 release -> normalised CSVs + structural diff (verification only)",
     "scripts/normalization/hca_v094_to_csv.py",
     ["--report", "docs/v094-structural-diff.md"], True),
    ("1b", "Rejser HTM -> travel TSVs (geocodes)",
     "scripts/enrichment/parse_rejser_htm.py", [], True),
    ("1c", "SV14 TEI place-list -> reconciled coordinates",
     "scripts/enrichment/reconcile_sv14_geo.py", [], True),
    ("1d", "work titles -> probable language",
     "scripts/enrichment/detect_work_language.py", [], True),
    ("1e", "person descriptions -> ethnic/national adjectives",
     "scripts/parsers/parse_person_ethnic_descriptors.py", [], True),
    ("1f", "person descriptions -> gender facet",
     "scripts/parsers/parse_person_gender.py", [], True),
    ("1g", "KB link workbook -> diary page permalinks",
     "scripts/enrichment/build_kb_links.py", [], True),
    ("1h", "verified place workbook -> categories/countries",
     "scripts/enrichment/reconcile_steder_categories.py", [], True),
    # Not a transformation: reports dangling cross-references and
    # kind-specific missing values across the registers. Optional so a run
    # still completes with findings outstanding -- tests/test_index_integrity.py
    # is what refuses to let them grow. See docs/index-integrity.md.
    ("2", "check register integrity (cross-references, required values)",
     "scripts/validation/check_indexes.py", ["--write"], True),
]


def run(stage_id, label, script, tail, optional):
    print(f"\n=== Stage {stage_id} - {label} " + "=" * max(0, 50 - len(label)))
    t0 = time.time()
    rc = subprocess.call([sys.executable, str(ROOT / script)] + tail, cwd=ROOT)
    dt = time.time() - t0
    if rc != 0:
        if optional:
            print(f"  [!] stage {stage_id} failed (rc={rc}) - continuing (optional)  [{dt:.1f}s]")
            return True
        print(f"  [x] stage {stage_id} failed (rc={rc})  [{dt:.1f}s]")
        return False
    print(f"  [ok] stage {stage_id} done  [{dt:.1f}s]")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--only", metavar="ID", help="run only the stage with this id (e.g. 1d)")
    ap.add_argument("--skip-v092", action="store_true",
                    help="skip stage 1a' (the slow nine-workbook V0.92 ingest)")
    ap.add_argument("--list", action="store_true", help="list stages and exit")
    args = ap.parse_args()

    if args.list:
        for sid, label, script, _tail, opt in STAGES:
            print(f"  {sid:4s} {'(optional) ' if opt else '           '}{label:52s} {script}")
        return

    stages = STAGES
    if args.only:
        stages = [s for s in STAGES if s[0] == args.only]
        if not stages:
            sys.exit(f"unknown stage id: {args.only}  "
                     f"(known: {', '.join(s[0] for s in STAGES)})")
    elif args.skip_v092:
        stages = [s for s in STAGES if s[0] != "1a'"]

    t0 = time.time()
    for stage in stages:
        if not run(*stage):
            sys.exit(1)
    print(f"\nAll done in {time.time() - t0:.1f}s.")
    print("Next: python scripts/publish.py   (assembles dist/ for hca-open-repo)")


if __name__ == "__main__":
    main()
