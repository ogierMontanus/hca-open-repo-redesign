> **Archived copy — not current.** Verbatim from `docs/pipeline/README.md` in
> [hca-open-repo](https://github.com/ogierMontanus/hca-open-repo), kept for its
> reasoning. Superseded by ../architecture.md and ../pipeline.md.
>
> Relative links below point at files in *that* repository and do not resolve
> here. See [`README.md`](README.md) for why these are kept.

# Conversion pipeline

How a digitised printed register becomes a normalised row in `data/normalized/entities.csv`.

The platform's data model is documented in [`docs/data-model/`](../data-model/). This folder describes the **process** that produces that data: the stages, their inputs and outputs, the constraints that every stage must respect, and where each implementation lives.

## Documents

| File | Purpose |
|---|---|
| [`stages.md`](stages.md) | Six-stage pipeline: slice → parse → OpenRefine → normalized CSV → star-schema model (Power Query / Power Pivot MVP) → optional Postgres warehouse. Inputs, outputs, scripts, and constraints per stage |

The target data model that Stage 5 builds and Stage 6 promotes into a database is documented separately in [`docs/data-model/star-schema.md`](../data-model/star-schema.md).

## Where things live

- **Canonical source** — `raw/HCA-Repository V[X.YY].xlsx`. A single consolidated workbook; the version in brackets increments over time. Always use the highest version available.
- **Parsers** — `scripts/parsers/`. Each parser reads a slice of the canonical workbook (filtered by `RegistryCategory` / `WorkGenre` / `RegistryForm`) and produces a structured TSV.
- **Normalisation** — `scripts/normalization/hca_xlsx_to_csv.py`. Folds parsed TSVs into the entity-centric CSVs.
- **Outputs** — `data/normalized/entities.csv`, `data/normalized/diary.csv`, `data/normalized/references.csv`.
