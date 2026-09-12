# Equivalence run — 2026-09-12

The first verification that this repository can drive the publication repo's
build on its own. Plan steps 2 and 3.

**Result: 4,559 of 4,560 build artifacts byte-identical.** The single
difference is `web/data/manifest.json`'s `built_at` timestamp.

## What was compared

Two checkouts of `hca-open-repo` at `main` (`36b65f1`), built with
`PYTHONHASHSEED=0` and `PYTHONIOENCODING=utf-8`:

| | Prepared data came from |
|---|---|
| **baseline** | the publication repo's own committed `data/` |
| **from-B** | this repository, after `data/normalized/`, `data/normalized_v092/`, `data/parsed/` and `data/curated/` were **deleted** from the checkout and replaced by `python scripts/publish.py --into …` |

Deleting first is what makes the test mean anything: it proves the publication
repo needs nothing but the 23-file published interface.

Only the stages that consume prepared data were run — `2, 3a, 3b, 4a…4f`. See
"Why stages 1a–1e were skipped" below.

```
  missing from the second  0
  extra in the second      0
  differing                1
     differs: web/data/manifest.json   [expected — built_at timestamp]

  PASS — 4,559 of 4,560 byte-identical
```

Artifacts covered: 4,544 diary pages, 9 `mockup/data/*.js`, 7 `web/data/*.json`.

Reproduce with `scripts/validation/compare_build_output.py`.

## Interface check

```
python scripts/publish.py --check --into ../hca-open-repo
0 of 23 interface file(s) differ
```

Clean only *because* of the drift reconciliation in `36d4af3` — three of those
23 files differed before it.

## Findings

### 1. `source_xlsx` is still `null`, and that is correct for now

PR #1's commit message predicted the from-B build would name the workbook it
descends from. It does not — both manifests carry `"source_xlsx": null`.

Not a defect. `publish.py` writes `data/normalized/_source.json` correctly,
naming `HCA-Repository V0.82.xlsx` with its SHA-256. But the code that *reads*
it ships in the publication repo's paired commit (`10d059f`), which is plan
step 4 and is not applied here. A at `main` still scans `data/raw/` for a loose
`.xlsx` and finds none, because the workbook lives inside a release folder.

The provenance data is already published. The consumer arrives at step 4.

### 2. Two build stages cannot run on Windows

`build_cooccurrence.py` (stage 4e) and `build_nation_index.py` (stage 4f) both
print a `→` (U+2192) in their progress output. Under Windows' cp1252 console
default this raises `UnicodeEncodeError` and the stage dies.

Stage 4e fails loudly. **Stage 4f is marked optional in `build_all.py`, so it
fails silently** — `build_all.py` prints `[!] continuing (optional)` and moves
on, and `mockup/data/nation-index.js` is simply absent from the build. It was
missing from the first baseline run for exactly this reason, and only showed up
as an `extra in the second` line in the comparison.

This is a defect in the publication repo, not here. It does not affect CI,
which runs on Linux under UTF-8. It does mean a local Windows build silently
ships without the nationality facet data. Worth a one-line fix there
(`sys.stdout.reconfigure(encoding="utf-8")`, or an ASCII arrow); reported
rather than worked around, beyond forcing the encoding in this repo's tooling.

### 3. `work_languages.csv` is less reproducible than documented

Measured while reconciling the drift (see `36d4af3`). Across 1,084 rows:
0 differences in language assignment, but 9 in method, 776 in confidence, and
**16 row-membership differences each way** — the last undocumented and the most
consequential. Rows near `lingua`'s inclusion threshold cross it when the
library version changes.

Hence the rule now written into the harness: **never run stages 1a–1e to
establish a baseline.** They regenerate this file, which silently moves the
thing the baseline is meant to hold fixed.

## Why stages 1a–1e were skipped

They are the ingest and enrichment stages — the work that moved to this
repository. Running them in the publication repo would regenerate the prepared
data from raw sources, which is precisely what is no longer that repo's job,
and would have reintroduced the `lingua` drift above.

Skipping them is not a gap in the test. It is the test: the publication repo
built from prepared data alone, which is the whole point of the split.
