# Pipeline

The stages, in order, with their inputs and outputs. For *why* the pipeline is
shaped this way — the boundary rule, what is authoritative, what must not be
hand-edited — read [`architecture.md`](architecture.md) first.

The authoritative stage list is `python scripts/run_pipeline.py --list`, which
is generated from the code. The table below explains what each stage is for;
if the two ever disagree, the runner is right and this file is stale.

## Running it safely

Two environment rules, both learned by being bitten:

- **`PYTHONIOENCODING=utf-8` on Windows.** Several scripts print `→` or `⚠`,
  which the cp1252 console default cannot encode. `build_cooccurrence.py` and
  `build_nation_index.py` died on it in the publication repo, the latter
  *silently* because its stage is optional; `build_kb_links.py` had never
  completed on Windows at all, because its warning branch fires on every run.
  The scripts here reconfigure stdout themselves now, but the habit is worth
  keeping for anything new.
- **`PYTHONHASHSEED=0` when producing a build for comparison**, and **never
  run stages 1a–1h to establish a baseline** — they regenerate
  `data/normalized/`, and `work_languages.csv` is not reproducible across
  `lingua` versions (see below).

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
| 1e | `enrichment/parse_person_ethnic_descriptors.py` | the V0.82 workbook, `curated/ethnic_adjectives_da.csv` | `normalized/person_ethnic_descriptors{,_review}.csv` |
| 1f | `enrichment/parse_person_gender.py` | the V0.82 workbook, `curated/gender_markers_da.csv` | `normalized/person_gender{,_review}.csv` |
| 1g | `enrichment/build_kb_links.py` | `1-KBDiaryLinkData-PQ-links-active.xlsm` | `normalized/kb_diary_links.csv` |
| 1h | `enrichment/reconcile_steder_categories.py` | `Steder_i_dagboegerne_verificeret_udfyldt VER 1.0.xlsx`, `entities.csv` | `normalized/steder_verified_categories.csv` |
| 2 | `validation/check_indexes.py` | the registers | `curated/index_integrity_review.csv` — cross-reference and required-value findings, see [`index-integrity.md`](index-integrity.md) |

Stage 2 transforms nothing: it reports dangling cross-references and
kind-specific missing values across the registers, and writes the findings
to `data/review/index_integrity_review.csv`. It is optional in the runner
so a run still completes with findings outstanding —
`tests/test_index_integrity.py` is what refuses to let them grow. The rules
and their reasoning: [`index-integrity.md`](index-integrity.md).

Stages after 1a are optional in the runner, mirroring how the publication
repo treated them: their outputs are committed, so a machine without
`lingua` leaves the previous extraction in place rather than emptying a
facet.

### `work_languages.csv` is committed data, not reproducible output

This was measured across two `lingua` versions, 1,084 rows each, and it is
less stable than earlier drafts of this file claimed:

| Field | Differences |
|---|---:|
| language assignment | **0** |
| method (`detector` / `detector_cue`) | 9 |
| confidence | 776 |
| **row membership** | **16 ids each way** |

All three instabilities are one effect: rows sitting near the inclusion
threshold cross it when the library version changes, which also flips which
method label wins. The language assignments never move — and the language is
what the facet displays.

So: regenerate only in a pinned environment, exclude the file from any
byte-equality comparison, and do not let stage 1d run as a side effect of
taking a baseline.

### V0.94 is not yet ingested

`data/raw/HCA REPOSITORY V0.94/` is present but no stage reads it. It is a
different structure from V0.92, not a version bump — five renamed registries,
a different ID scheme, and references re-encoded as key lists inside the
dimension rows. It brings a complete works register and no person register at
all. The plan is to ingest it read-only into a parallel
`data/normalized_v094/` and publish a structural diff before any stage depends
on it: [`migration-plan.md`](migration-plan.md) §0.4 and §I.

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
