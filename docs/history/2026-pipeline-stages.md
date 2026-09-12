> **Archived copy — not current.** Verbatim from `docs/pipeline/stages.md` in
> [hca-open-repo](https://github.com/ogierMontanus/hca-open-repo), kept for its
> reasoning. Superseded by ../architecture.md. Its cross-cutting constraints survive there; its six-stage model never ran.
>
> Relative links below point at files in *that* repository and do not resolve
> here. See [`README.md`](README.md) for why these are kept.

# Pipeline stages

Five stages take a printed register from `raw/` to the normalised CSVs in `data/normalized/`. Each stage has an explicit input, an explicit output, and a small set of constraints that hold across the whole pipeline.

## Cross-cutting constraints

These apply at every stage:

- **UTF-8 throughout.** Source workbooks, intermediate TSVs, and final CSVs are all UTF-8 (no BOM).
- **Original order is reconstructable.** The printed-index ordering carries editorial meaning. Stages either preserve row order or carry a `sequence` / `BookSeqNo` column that lets it be restored.
- **Original data is never lost, only supplemented.** Cleaning produces new columns; it does not overwrite the source. Every transformation must be reversible to the raw entry it came from.
- **Transformations are traceable.** Each parsed row keeps `RegistryTitelID` (`PKRegistryTitelID` in the workbook) as its provenance pointer.
- **Ambiguity is escalated, not guessed.** When a parenthetical or relation marker has more than one plausible classification, parsers flag the row for review.
- **Data quality before interface.** A weak grounding cannot be rescued by a smart frontend or a chatbot. Reference fields (volume, page, date) must be reliable before any analytic or presentation layer is built on top.
- **Narrow dimensions, rich facts.** Stable, universally-present attributes live in dimension rows. Combinations and relations (work × person × date × place × page) live in fact rows. Avoid early over-modelling on the dimension side.

## Stage 1 — Slice

**Input:** `raw/HCA-Repository V*.xlsx` (highest available version).

**Output:** an in-memory 2-column list — `(RegistryTitle, PKRegistryTitelID)` — filtered to one register section.

The canonical workbook contains every register in a single `Registry` sheet, classified by `RegistryCategory (H1)` / `WorRegSubCat.WorkGenre (H2)` / `WorRegSubCat.RegistryForm (H3)` / `WorRegSubCat.WorkSubForm (H4)`. Stage 1 selects the slice that matches a particular parser's register type (music, novels-plays-tales, non-fiction, etc.).

Implementation: `resolve_ground_truth_xlsx()` and `load_registry_slice()` in `scripts/parsers/_common.py`.

## Stage 2 — Parse

**Input:** the 2-column slice from Stage 1.

**Output:** a structured TSV with register-specific columns, written to a path of the caller's choosing (typically next to the parser).

Each parser is genre-specific because the parenthetical conventions and relevant fields differ:

| Parser | Slice | Output columns (highlights) |
|---|---|---|
| `parse_music_register.py` | `MUSIK / Vokal- og Instrumentalmusik` | main_title, incipit, original_title, creator, opus, part_of, Krydshenvisning_til, Note |
| `parse_novels_plays_tales.py` | `ANDRE FORFATTERE / Romaner, Noveller, Eventyr` | main_title, original_title, creator, part_of, Se_ogsaa, Krydshenvisning_til, cited_directly, Note |
| `parse_non_fiction.py` | `ANDRE FORFATTERE / Faglitteratur` | main_title, pseudonym, creator, translator, source, Se_ogsaa, Krydshenvisning_til, uncertain_citation, Note |

The parsing logic (parenthetical extraction, classification, cross-reference detection) is preserved from the earlier `data-cleaning` workshop; the I/O layer has been refactored to read directly from the canonical workbook.

See [`docs/data-model/source-data-characteristics.md`](../data-model/source-data-characteristics.md) for the parenthetical conventions every parser respects.

## Stage 3 — OpenRefine review (optional, manual)

**Input:** TSV from Stage 2.

**Output:** the same TSV with cleaning history applied.

OpenRefine is the curation tool for human-in-the-loop normalisation: clustering near-duplicates, reconciling person names against VIAF / Wikidata, splitting compound fields that the parser left atomic, fixing rows the parser flagged as ambiguous. Every original column is duplicated before transformation so the raw value survives.

This stage is optional: simple registers may go straight from Stage 2 to Stage 4. It is recorded here because it is part of the documented workflow for entries that need authority reconciliation.

## Stage 4 — Normalize to entity-centric CSVs

**Input:** one or more parsed/curated TSVs.

**Output:** `data/normalized/entities.csv`, `data/normalized/diary.csv`, `data/normalized/references.csv`.

`scripts/normalization/hca_xlsx_to_csv.py` consumes the canonical workbook plus parsed register slices and produces the three CSVs that the rest of the platform consumes. The output schema is documented in [`ai-context/coding_agent_plan.md`](../../ai-context/coding_agent_plan.md) §4.

This is the canonical handoff between the pipeline and the application: anything downstream (frontend, backend API, search index, graph build) reads from these files. These CSVs are the early, hand-shaped form of the star-schema model that Stage 5 promotes them into.

## Stage 5 — Star-schema model (Power Query / Power Pivot MVP)

**Input:** the normalised CSVs from Stage 4 (and, for the in-Excel MVP, the canonical workbook directly).

**Output:** a Power Pivot data model — explicit dimension and fact tables connected by relationships — exposed through pivot tables, slicers, and optionally a Copilot/chat layer.

This stage is where the data model documented in [`docs/data-model/star-schema.md`](../data-model/star-schema.md) takes physical shape:

- **Power Query** loads the workbook, splits the parent Registry into Work / Person / Place sub-types, and joins Sørens auxiliary registers (Artist, Sted, Almanak).
- **Power Pivot** holds the dimensions (Calendar, Diary, Work-Registry, Person-Registry, Location-Registry, Sørens registers) and facts (References-In-Diary-Page as the spine, plus finer-grained section/date/place facts) as a star schema.
- **Pivot tables and slicers** are the demonstration surface for the first round. They double as a laboratory for the standard queries that any later web UI will need to support.

This is the "Excel-MVP" referenced throughout the meeting notes — a prototype platform, not the endpoint. Its purpose is to validate the model at full data scale and give collaborators a clickable surface before any web-stack investment.

## Stage 6 — Optional Postgres warehouse

**Input:** the validated dimensions and facts from Stage 5.

**Output:** a PostgreSQL star schema, with the alias / see_also / relation tables alongside for graph traversal.

Schema in [`docs/data-model/wemi-and-relations.md`](../data-model/wemi-and-relations.md) (entity + relation layer) and [`docs/data-model/star-schema.md`](../data-model/star-schema.md) (dimensions + facts). The database is a derived artifact: it supports full-text search and multi-hop traversal beyond what the Excel MVP can deliver, but the Power Pivot model remains the authoritative model definition until the web back-end exists.

The concrete PostgreSQL OLTP schema draft for this stage is being continued in [`nosql-hca-open-repo`](https://github.com/ogiermontanus/nosql-hca-open-repo) — see [`docs/data-model/postgresql-migration.md`](../data-model/postgresql-migration.md) for the signpost.

## Stage extension: language tagging

`scripts/parsers/add_language_column.py` runs on any Stage-2 output and appends `probable_language` (ISO 639-1) and `language_confidence` columns. It uses `lingua-language-detector`, which is designed for short texts like titles. The language column drives downstream OPAC routing (REX/KB, DNB, BnF, BL, Libris, etc.).

The detector is restricted to the languages that appear in the registers: da, de, fr, en, sv, nl, it, la, es, pt, nb (the last is remapped to da; written Bokmål and Danish are near-identical for cataloguing purposes). Rows with `language_confidence < 0.35` are flagged for manual review.
