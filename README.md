# HCA Diary — data cleaning & preparation

Cleaning, preprocessing, segmentation and preparation of the source data
behind **[HCA Open Repository](https://github.com/ogierMontanus/hca-open-repo)**
(*Andersen's Hvem Hvad Hvor*).

This repository owns everything between the raw sources and the prepared
data. The publication repository owns the build and the website.

```
data/raw/  →  [this repo]  →  prepared data  →  hca-open-repo  →  mockup/ + web/
   sources     clean, parse,      dist/           build HTML/JS/JSON
               segment, enrich
```

The division of labour is: **nothing here renders anything, and nothing in
hca-open-repo re-derives anything.** A build in the publication repo reads
the files this repo publishes and nothing else.

That claim is checked, not asserted: with the prepared data deleted from a
publication-repo checkout and replaced by `publish.py --into`, its build
produced **4,559 of 4,560 artifacts byte-identical** to one built from its own
committed data — the single difference being a build timestamp.
[`docs/equivalence-2026-09-12.md`](docs/equivalence-2026-09-12.md).

**New here? Read [`docs/architecture.md`](docs/architecture.md) first.** It
covers where the data comes from, what is authoritative, what each stage does,
what is generated, and what must never be hand-edited.

## Layout

| Path | Contents |
|---|---|
| `data/raw/` | The source materials: three generations of register workbook (V0.82, V0.92, V0.94), the geocoded Rejser table, the SV14 TEI place-list, the KB link workbook, the verified-places workbook, the independent person transcription, the register OCR PDF |
| `data/normalized/` | Star-shaped CSVs and the enrichment layers derived from them |
| `data/parsed/` | Register segmentation output — one row per register entry |
| `data/curated/` | Hand-curated authority tables and the review artefacts the curation passes produced |
| `scripts/normalization/` | Workbook ingesters (V0.82 flat, V0.92 multi-file) |
| `scripts/enrichment/` | Reconciliation and derivation passes over the normalised CSVs |
| `scripts/parsers/` | Register parsers and the person-register segmentation/cleaning passes |
| `scripts/place_typology/` | Place classification work |
| `scripts/correspondence/` | Collin-letter index extraction and register matching |
| `scripts/migration/` | Tidstavle (timeline) migration from EPUB/SQL |
| `scripts/validation/` | Register integrity checks, and the build-equivalence harness |
| `dist/` | The published package — assembled by `scripts/publish.py`, gitignored |

### Three source generations, none complete

No single release covers every entity, so ingest is parameterised **per entity
type** rather than by one global version switch:

| Release | Authoritative for | Missing |
|---|---|---|
| **V0.82** | the live site: persons, diary text, references with ordering | — |
| **V0.92** | nothing in production; kept as a verification surface | its person slice covers volumes VI–VII only |
| **V0.94** | works, places, the ten-volume page list, the calendar — **not yet ingested** | **no person register**; coordinates and cross-references provisioned but empty |

[`docs/architecture.md`](docs/architecture.md) §2 explains what is
authoritative for which field, and why the newest file does not automatically
win.

## Running the pipeline

```
python -m pip install -r requirements.txt
python scripts/run_pipeline.py          # regenerate data/normalized/ from data/raw/
python scripts/publish.py --into ../hca-open-repo
```

`run_pipeline.py --list` shows the stages. Everything it runs is
deterministic from the raw sources; the human-in-the-loop cleaning passes
under `scripts/parsers/` are deliberately *not* in it, because their
results were reviewed and are committed as data. See
[`docs/pipeline.md`](docs/pipeline.md).

## The interface to hca-open-repo

`scripts/publish.py` assembles exactly the files the publication repo's
build reads — see [`docs/interface.md`](docs/interface.md) for the list and
what each one feeds. `--check` reports drift without changing anything:

```
python scripts/publish.py --check --into ../hca-open-repo
```

Alongside the data it writes `data/normalized/_source.json`, recording the
raw sources (filename + SHA-256) the package was derived from, so the
publication repo can state its provenance without holding the workbooks.

## Integrity checks

```
python scripts/validation/check_indexes.py
```

Reports cross-references that lead nowhere, and fields that are empty when
their kind of row requires them — written per index and per entry kind,
because a redirect stub and an ordinary entry have opposite requirements.
See [`docs/index-integrity.md`](docs/index-integrity.md).

## Proving a change did not alter the site

```
python scripts/validation/compare_build_output.py snapshot ../hca-open-repo before.json
# … make the change, publish, rebuild there …
python scripts/validation/compare_build_output.py compare before.json after.json
```

Hashes all 4,544 diary pages and the 16 generated data artifacts. Build with
`PYTHONHASHSEED=0`, and **do not run the ingest stages to make a baseline** —
they regenerate `data/normalized/`, and `work_languages.csv` is not
reproducible across `lingua` versions. The script's docstring has the details.

## Tests

```
python -m pytest tests/ -q      # 53 tests
```

These guard the *cleaning* output — register segmentation, the person
emendations, and the integrity rules above. The build-output tests live in
the publication repo.

## Documentation

| | |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | **Start here.** The conceptual shape: sources, stages, boundaries, what not to edit |
| [`docs/pipeline.md`](docs/pipeline.md) | The stages, in order, with inputs and outputs |
| [`docs/interface.md`](docs/interface.md) | The 23 files that cross to the publication repo, and what each feeds |
| [`docs/index-integrity.md`](docs/index-integrity.md) | What the integrity checker enforces, and why |
| [`docs/person-register-segmentation.md`](docs/person-register-segmentation.md) | How register XI was segmented, how good it is, known weaknesses |
| [`docs/migration-plan.md`](docs/migration-plan.md) | Why the architecture is shaped this way, and what changes next |
| [`docs/equivalence-2026-09-12.md`](docs/equivalence-2026-09-12.md) | The first equivalence run, and three findings from it |
| [`docs/history/`](docs/history/) | Superseded pipeline documents, kept for their reasoning |

## Licence

CC BY 4.0, as the publication repository. See its `LICENSE`.
