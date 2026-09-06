# Pipeline

## The automated stages

`python scripts/run_pipeline.py` regenerates everything that is
deterministic from `data/raw/`. These are exactly the stages the
publication repository used to run as stages 1a–1e of its own
`build_all.py`, plus the two reconciliation passes that were run by hand
there.

| Stage | Script | Reads | Writes |
|---|---|---|---|
| 1a | `normalization/hca_xlsx_to_csv.py` | `HCA-Repository V0.82.xlsx` | `normalized/{entities,diary,references}.csv` |
| 1a′ | `normalization/hca_v092_to_csv.py` | `HCA REPOSITORY V0.92/*.xlsx` | `normalized_v092/{entities,diary,references}.csv` |
| 1b | `enrichment/parse_rejser_htm.py` | `Rejser_HCA_X.htm` | `normalized/rejser{,_journeys}.tsv` |
| 1c | `enrichment/reconcile_sv14_geo.py` | `SV14_places.xml`, `entities.csv`, `rejser.tsv` | `normalized/sv14_places_{reconciled,ambiguous}.csv` |
| 1d | `enrichment/detect_work_language.py` | `entities.csv` | `normalized/work_languages.csv` |
| 1e | `parsers/parse_person_ethnic_descriptors.py` | the V0.82 workbook, `curated/ethnic_adjectives_da.csv` | `normalized/person_ethnic_descriptors{,_review}.csv` |
| 1f | `parsers/parse_person_gender.py` | the V0.82 workbook, `curated/gender_markers_da.csv` | `normalized/person_gender{,_review}.csv` |
| 1g | `enrichment/build_kb_links.py` | `1-KBDiaryLinkData-PQ-links-active.xlsm` | `normalized/kb_diary_links.csv` |
| 1h | `enrichment/reconcile_steder_categories.py` | `Steder_i_dagboegerne_verificeret_udfyldt VER 1.0.xlsx`, `entities.csv` | `normalized/steder_verified_categories.csv` |
| 2 | `validation/check_indexes.py` | the registers | `curated/index_integrity_review.csv` — cross-reference and required-value findings, see [`index-integrity.md`](index-integrity.md) |

Stage 2 transforms nothing: it reports dangling cross-references and
kind-specific missing values across the registers, and writes the findings
to `data/curated/index_integrity_review.csv`. It is optional in the runner
so a run still completes with findings outstanding —
`tests/test_index_integrity.py` is what refuses to let them grow. The rules
and their reasoning: [`index-integrity.md`](index-integrity.md).

Stages after 1a are optional in the runner, mirroring how the publication
repo treated them: their outputs are committed, so a machine without
`lingua` leaves the previous extraction in place rather than emptying a
facet. `work_languages.csv` is sensitive to the installed `lingua`
version — the *language* assignments are stable, the confidence figures
drift by a few thousandths between versions. Regenerate it in a fixed
environment or leave the committed file alone.

## The stages that are deliberately not automated

`scripts/parsers/` holds two different kinds of thing.

**Register parsers** — `parse_music_register.py`,
`parse_novels_plays_tales.py`, `parse_non_fiction.py`,
`parse_personregister_xi.py` — slice the canonical workbook (or, for the
person register, the OCR PDF) by register section and emit
`data/parsed/*.tsv`. They are re-runnable, but their output is the *input*
to a long human-reviewed cleaning chain, so re-running one discards that
chain. Run them deliberately, then re-apply the chain.

**The cleaning chain** — the `suggest_*` / `apply_*` / `merge_*` /
`split_*` / `dedupe_*` / `refine_*` scripts — is the record of that
review. Each `suggest_*` script writes a review file to `data/curated/`, a
human reads it, and the paired `apply_*` script applies the approved
decisions to `data/parsed/personregister_xi_parsed.tsv`. They are one-shot
passes, already applied, kept for audit and for re-deriving the file from
an older snapshot. The order they were applied in, and the measurement
method used to check coverage against the independent transcription in
`data/raw/Personer _ HCA_tsv.txt`, are recorded in
[`docs/person-register-segmentation.md`](person-register-segmentation.md).

**Curation passes needing a built site** — `parse_person_role.py`,
`wikidata_lookup.py` and the `correspondence/match_collin_*` scripts read
the publication repo's built `*-extra.js` cards. Point
`HCA_MOCKUP_DATA_DIR` at a built `hca-open-repo/mockup/data` and run them
by hand. See [`interface.md`](interface.md).

## Cross-cutting constraints

Carried over from the publication repo's own pipeline documentation, and
still binding here:

- **UTF-8 throughout**, no BOM.
- **Original order is reconstructable.** Printed-index ordering carries
  editorial meaning; stages preserve row order or carry a sequence column.
- **Original data is never lost, only supplemented.** Cleaning adds
  columns; it does not overwrite the source. Every transformation must be
  reversible to the raw entry it came from.
- **Transformations are traceable.** Each parsed row keeps
  `RegistryTitelID` as its provenance pointer.
- **Ambiguity is escalated, not guessed.** A parenthetical or relation
  marker with more than one plausible reading is written to a review file,
  not resolved silently.
