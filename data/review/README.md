# Review artefacts

**Generated. Read by a human, acted on, and kept for audit. Nothing here is an
input to the pipeline, and nothing here crosses to the publication repo.**

Two kinds of file:

- **Suggestion files** written by a `suggest_*` / `check_*` pass, which a
  person read before the paired `apply_*` pass acted on their decisions. The
  decisions are already applied; these are the record of what was approved.
- **Intermediate and match output** from the Collin-letter work and the
  register comparisons — indexes extracted from a source, candidate matches,
  unmatched lists, duplicate candidates.

They were moved out of `data/curated/` because that folder held two things
with opposite lifecycles: eleven hand-maintained authority tables that are
*inputs*, and thirty-nine generated reports that are *outputs*. Mixing them
made it impossible to tell, from the folder alone, which files a person may
edit and which the next run overwrites.

## What you may edit

Nothing, except as the record of a human decision. If you want to change what
the pipeline *does*, edit the authority tables in
[`../curated/`](../curated/README.md) and re-run the pass.

Re-running a `suggest_*` pass overwrites its file here. That is safe — the
corresponding `apply_*` has already run — but it does not undo or redo
anything.

## The live ones

Most of these are frozen history. Three are regenerated on demand and worth
re-reading after any change to the registers:

| File | Written by |
|---|---|
| `index_integrity_review.csv` | `scripts/validation/check_indexes.py` — dangling cross-references and kind-specific missing values |
| `person_reference_unmatched_{ours,reference}.csv` | `scripts/validation/compare_to_reference.py` — entries on one side of the independent transcription and not the other, after spelling variants are discounted |
| `person_duplicate_candidates.csv` | the same script — entries sharing a surname, a page signature and a compatible given name |
