# Register parsers

Register parsers (see [`docs/pipeline.md`](../../docs/pipeline.md), and
[`docs/architecture.md`](../../docs/architecture.md) for where they sit). Each parser reads the canonical workbook in `raw/`, filters the `Registry` sheet to one printed-register section, and writes a structured TSV.

## Setup

```bash
pip install -r scripts/parsers/requirements.txt
```

## Ground-truth resolution

All parsers locate the workbook by globbing `raw/HCA-Repository V*.xlsx` and selecting the highest-numbered version. When a new version (e.g. `V0.83.xlsx`) lands in `raw/`, no code change is needed — the next run picks it up automatically. The helper lives in `_common.py` as `resolve_ground_truth_xlsx()`.

## Parsers

| Parser | Default slice | Default output |
|---|---|---|
| `parse_music_register.py` | `VÆRK-REGISTER` / `MUSIK` / `Vokal- og Instrumentalmusik` | `data/parsed/music_register_parsed.tsv` |
| `parse_novels_plays_tales.py` | `VÆRK-REGISTER` / `ANDRE FORFATTERE` / `Romaner, Noveller, Eventyr` | `data/parsed/novels_plays_tales_parsed.tsv` |
| `parse_non_fiction.py` | `VÆRK-REGISTER` / `ANDRE FORFATTERE` / `Faglitteratur` | `data/parsed/non_fiction_parsed.tsv` |

Run any parser from the repo root with no arguments:

```bash
python scripts/parsers/parse_music_register.py
python scripts/parsers/parse_novels_plays_tales.py
python scripts/parsers/parse_non_fiction.py
```

Each accepts `--xlsx PATH` to point at a non-default workbook and `--output PATH` to redirect the TSV. `parse_novels_plays_tales.py` additionally accepts `--genre` and `--form` to retarget a different register section (e.g. `--form 'Skuespil'`).

## Supporting utilities

| Script | Purpose |
|---|---|
| `_common.py` | `resolve_ground_truth_xlsx()` + `load_registry_slice()` |
| `xlsx_to_tsv.py` | Generic Excel → TSV dump (any sheet, any file) |
| `add_language_column.py` | Appends `probable_language` + `language_confidence` to any parsed TSV. Shares its language set and Bokmål remap with `enrichment/detect_work_language.py` via `scripts/_lib/language.py`, but not its policy — this one is bare top-1, no guards. |

```bash
python scripts/parsers/add_language_column.py data/parsed/music_register_parsed.tsv
```

## Composition with `scripts/normalization/`

The parsed TSVs in `data/parsed/` are inputs to `scripts/normalization/hca_xlsx_to_csv.py`, which folds them into the entity-centric CSVs in `data/normalized/`.

## Output schemas and parsing rules

- Columns for each parser are documented in its module docstring.
- The parenthetical conventions and special tokens (`»...«`, `Ͻ:`, `[...]`, `se:`, `Se ogsaa:`) the parsers act on are described in [`source-data-characteristics.md`](https://github.com/ogierMontanus/hca-open-repo/blob/main/docs/data-model/source-data-characteristics.md) (in the publication repo).
- The WEMI / relation-table rationale behind `Se_ogsaa`, `Krydshenvisning_til`, and the alias-vs-relation split is in [`wemi-and-relations.md`](https://github.com/ogierMontanus/hca-open-repo/blob/main/docs/data-model/wemi-and-relations.md) (in the publication repo).

## Known follow-ups

- No automated tests yet. A snapshot test that pins parsed TSV bytes against a known workbook version would catch regressions when the parsers are extended.
- `parse_novels_plays_tales.py` is currently restricted to one `RegistryForm` per run; a future change could let it merge `Skuespil` + `Digte` + `Romaner, Noveller, Eventyr` in one pass if downstream wants a unified literary feed.
- After every parsing run, review the TSV for structural violations as described in `docs/data-model/source-data-characteristics.md` ("What 'review every parsing run' actually means").

## Moved out of this directory

Four scripts left `scripts/parsers/` because they were not parsers:

| Script | Now | Why |
|---|---|---|
| `parse_person_gender.py` | `scripts/enrichment/` | derives a facet from descriptions; it is runner stage 1f |
| `parse_person_ethnic_descriptors.py` | `scripts/enrichment/` | same, stage 1e |
| `parse_person_role.py` | `scripts/curation/` | reads the publication repo's **built** cards |
| `wikidata_lookup.py` | `scripts/curation/` | same |

`name_normalize.py` also left `scripts/correspondence/` for
`scripts/_lib/names.py`, so more than one directory can import it.

What remains here is the two kinds of thing described in
[`docs/pipeline.md`](../../docs/pipeline.md): the register parsers, and the
one-shot cleaning chain that has already been applied.
