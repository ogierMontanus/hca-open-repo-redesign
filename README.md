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

## Layout

| Path | Contents |
|---|---|
| `data/raw/` | The source materials: the canonical Repository workbook, the V0.92 nine-workbook release, the geocoded Rejser table, the SV14 TEI place-list, the KB link workbook, the verified-places workbook, the register OCR PDF |
| `data/normalized/` | Star-shaped CSVs and the enrichment layers derived from them |
| `data/parsed/` | Register segmentation output — one row per register entry |
| `data/curated/` | Hand-curated authority tables and the review artefacts the curation passes produced |
| `scripts/normalization/` | Workbook ingesters (V0.82 flat, V0.92 multi-file) |
| `scripts/enrichment/` | Reconciliation and derivation passes over the normalised CSVs |
| `scripts/parsers/` | Register parsers and the person-register segmentation/cleaning passes |
| `scripts/place_typology/` | Place classification work |
| `scripts/correspondence/` | Collin-letter index extraction and register matching |
| `scripts/migration/` | Tidstavle (timeline) migration from EPUB/SQL |
| `dist/` | The published package — assembled by `scripts/publish.py`, gitignored |

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

## Tests

```
python -m pytest tests/ -q
```

These guard the *cleaning* output — register segmentation, the person
emendations, and the integrity rules above. The build-output tests live in
the publication repo.

## Licence

CC BY 4.0, as the publication repository. See its `LICENSE`.
