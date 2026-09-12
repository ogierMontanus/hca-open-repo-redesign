# Superseded pipeline documentation

Three documents from `hca-open-repo`, kept because they record *why* the
architecture is what it is. **None of them describes a pipeline that runs.**
Read [`../architecture.md`](../architecture.md) for the one that does.

They are here rather than in the publication repository because what they
describe — ingest, parsing, normalisation — is this repository's concern now.

| File | Was | Why it is wrong now |
|---|---|---|
| `2026-pipeline-readme.md` | `docs/pipeline/README.md` | Points at `scripts/parsers/` and `scripts/normalization/` inside the publication repo. Both moved here. |
| `2026-pipeline-stages.md` | `docs/pipeline/stages.md` | Documents a six-stage model — slice → parse → OpenRefine → normalised CSV → Power Pivot star schema → optional Postgres. Stage 3 (OpenRefine) appears nowhere in the code. Stage 5 (Power Pivot) happens *upstream*, in the source workbooks, not downstream of the CSVs as drawn. Stage 6 points at a repository that has moved twice. |
| `2026-october-pipeline.md` | `docs/data-model/october-pipeline.md` | A third, different three-stage shape, and honest about its status: "this document records the proposal — it is not yet ratified." Its reasoning about *formats* — why CSV and JSON, why not SQLite or Parquet — is still sound and still the reason this repository ships CSV and TSV. |

## What is still worth reading in them

Not the stage lists. These:

- **The cross-cutting constraints** in `2026-pipeline-stages.md` — UTF-8 throughout, original order reconstructable, original data never overwritten only supplemented, transformations traceable to `RegistryTitelID`, ambiguity escalated rather than guessed. They survive intact and are restated in [`../architecture.md`](../architecture.md), because they are about the scholarly data rather than about any particular script.
- **The format argument** in `2026-october-pipeline.md` — the case against introducing SQLite, DuckDB or Parquet at this scale, and the observation that collaborators lose the double-click affordance when data stops being a spreadsheet. That argument still holds and still decides things here.
- **The Rejser geocoding account** in the same file — how 377 places came to have coordinates, and why the rest do not.

## The lesson worth carrying

Three pipeline documents accumulated in one repository, none matching the
code, each written when a different shape was intended. The check that caught
it was reading `build_all.py`'s stage list against them.

Documentation that describes intentions ages into documentation that misleads.
[`../architecture.md`](../architecture.md) therefore documents the conceptual
architecture and points at the runner for the stage list, rather than
duplicating a sequence that will drift again.
