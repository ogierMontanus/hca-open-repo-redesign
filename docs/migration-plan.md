# Migration plan — data pipeline from `hca-open-repo` into this repository

Investigation phase only. Nothing is migrated or deleted by this document.

| | |
|---|---|
| **Repository A** | [`ogierMontanus/hca-open-repo`](https://github.com/ogierMontanus/hca-open-repo) — website + full pipeline, `main` @ `36b65f1` |
| **Repository B** | [`ogierMontanus/hca-open-repo-redesign`](https://github.com/ogierMontanus/hca-open-repo-redesign) — **this repository, currently empty (zero commits)** |
| **Repository C** | [`ogierMontanus/HCA-Diary-data-cleaning`](https://github.com/ogierMontanus/HCA-Diary-data-cleaning) — a third repo holding an already-built, already-validated version of this migration on an unmerged branch (PR #1) |
| Date | 2026-09-12 |
| Revision | 2026-09-12 — **V0.94 source release added** (`new input/HCA REPOSITORY V0.94`); §0.4, §C, §E.1, §E.4, §F, §H, §I and §K revised accordingly |
| Decision | 2026-09-12 — **persons will come from the cleaning repo's segmentation output**, not from the V0.82 workbook. §E.3 resolved; §D, §H, §I.10 and §J.6 revised. |
| Decision | 2026-09-12 — **V0.92 rejected as a person source** (§E.3a). **V0.82 remains the person spine until the crosswalk validates**; the segmentation output is adopted additively, not as a cutover. §I.10 restaged. |

---

## 0. Three corrections to the brief

The task instructions rest on three premises that the repositories contradict.
Each changes the work, so they are stated before the analysis.

### 0.1 Repository A's pipeline is Python, not JavaScript

The brief refers throughout to "Repository A's historical chain of JavaScript
transformations" and asks whether "several JavaScripts can become one build
operation". There is no chain of JavaScript transformations.

A's `scripts/` tree is **80 Python files and nothing else** (plus three
READMEs and a `requirements.txt`). The JavaScript in A is of two other kinds,
neither of which transforms data:

- `mockup/data/*.js` — eight **generated output** files (~12 MB total), each a
  JSON payload wrapped in a `const` assignment so it loads over `file://`
  without a fetch. These are the pipeline's products, not its stages.
- `mockup/js/*.js` — thirteen **frontend** files (facet engine, search,
  rendering). Presentation, explicitly out of scope per §9 of the brief.

Consequences: §7 ("existing JavaScript may be replaced completely") and §16's
"do not assume JavaScript is necessarily the correct technology" are already
satisfied — the pipeline never was JavaScript. The genuine technology question
is a different one, addressed in §F below: **how much of the transformation
already happens in PowerQuery/PowerPivot and is then redone in Python.**

### 0.2 Repository B is empty

`hca-open-repo-redesign` has zero commits and no remote refs. Several
instructions are therefore unanswerable as written:

- §3, "replaced by an existing operation in B" — there are none.
- §5, "Do not reproduce Repository A's architecture inside B" — nothing exists
  to reproduce into.
- §10, "existing tooling in B already makes some scripts in A redundant" — no
  tooling exists.

### 0.3 The migration has already been done once, in a third repository

This is the substantive finding.

`ogierMontanus/HCA-Diary-data-cleaning` exists. Its `main` is an empty initial
commit, but branch `claude/hca-preprocessing-separation-iobj59` — **open as
PR #1, never merged** — contains a complete, working, validated version of
precisely what the brief asks for:

```
74 Python scripts     scripts/{normalization,parsers,enrichment,place_typology,
                               correspondence,migration,validation}/
all raw sources       data/raw/ + the legacy workbooks
prepared data         data/{normalized,normalized_v092,parsed,curated}/
a stage runner        scripts/run_pipeline.py     (10 declared stages)
an interface contract scripts/publish.py          (explicit file list, --check drift)
an integrity checker  scripts/validation/check_indexes.py
documentation         docs/{pipeline,interface,index-integrity,
                            person-register-segmentation}.md
```

The matching commit in A (`10d059f`, branch
`claude/hca-preprocessing-separation-iobj59`) strips the moved code out of the
publication repo and reduces `build_all.py` to build stages only.

It was validated properly. With `PYTHONHASHSEED` fixed, all **4,544 generated
diary HTML pages, all 8 `mockup/data/*.js` files and 6 of 7 `web/data/*.json`
files are byte-identical** before and after. The single difference is
`web/data/manifest.json`: its timestamp, and `source_xlsx`, which was `null`
before and now names the workbook — the old provenance scan only looked for a
loose `.xlsx` in `data/raw/` and never saw the one inside its release folder.
That is a **bug fix**, not a regression. The build was additionally verified
with `data/raw/` and `raw/` moved aside entirely, proving the publication repo
no longer depends on raw sources.

**Per the decision taken in planning, this work is the seed for Repository B.**
Discarding it and starting fresh would throw away a byte-identical validation
that is expensive to reproduce; adopting the third repo as B instead would
leave the instruction's named repository stranded. The plan below imports it
into `hca-open-repo-redesign` and then goes further than it did.

### 0.4 A fourth source generation, V0.94, has since been added

`new input/HCA REPOSITORY V0.94` — five renamed, numbered workbooks — landed in
this repository after the analysis below was first written. It is **not a
version bump of V0.92**. It is a different data structure, a different ID
scheme, a different reference encoding, and it comes with a specification for a
JSON format consumed by a **second, separately built website**.

It changes four conclusions of this plan, and it is analysed in full in §F.1–F.3:

| | |
|---|---|
| **The gate moved** | V0.92 had Persons and no Works. V0.94 has **Works** (3,590 rows, the deliverable §H was waiting on) and **no Persons at all**. The blocking dependency is now the person register, not the work register. |
| **The star schema was withdrawn** | V0.92's `FactDiaPerPag` / `FactDiaLocPag` / `FactDiaLocPerPag` fact tables are gone. V0.94 encodes references as space-separated key lists inside dimension rows. The co-occurrence simplification in §E.1 has no V0.94 successor. |
| **An ID crosswalk arrived, half-complete** | `OLDWorkID` resolves **3,590 of 3,590** into A's `entities.csv`. `OLDLocationID` resolves **0 of 2,433** — it carries V0.92's `LOC…` scheme, not the live `Reg…` ids. |
| **The release under-delivers against its own spec** | `1-SITES.xlsx` documents eight tables including a person register and three bridge tables. Five workbooks arrived, with none of them. Read its figures as intent, not as data on hand. |

---

## A. Repository A analysis

### What A is

A single repository carrying four different concerns that have no reason to
share a git history:

1. **Raw sources** — printed-register OCR, scanned PDFs, Word transcriptions,
   nine PowerQuery/PowerPivot workbooks, a scraped travel table, a TEI
   place-list.
2. **Cleaning and preparation** — ingesters, register parsers, a long
   human-reviewed segmentation chain, enrichment passes.
3. **Build** — the stages that turn prepared CSV/TSV into the site's data
   artifacts.
4. **The website** — `mockup/` (the live site, 30 HTML pages in two languages)
   and `web/` (an earlier Places demo).

### What actually runs

`scripts/build_all.py` declares 15 stages. Six are optional and mirror CI's
`continue-on-error`:

| Stage | Script | Reads | Writes | Optional |
|---|---|---|---|---|
| 1a | `normalization/hca_xlsx_to_csv.py` *or* `hca_v092_to_csv.py` | the chosen `data/raw/HCA REPOSITORY V*` folder | `normalized/{entities,diary,references}.csv` | no |
| 1b | `build_web/parse_rejser_htm.py` | `Rejser_HCA_X.htm` | `normalized/rejser{,_journeys}.tsv` | yes |
| 1c | `build_mockup/reconcile_sv14_geo.py` | `SV14_places.xml`, entities, rejser | `normalized/sv14_places_{reconciled,ambiguous}.csv` | yes |
| 1d | `build_mockup/detect_work_language.py` | entities | `normalized/work_languages.csv` | yes |
| 1e | `parsers/parse_person_ethnic_descriptors.py` | V0.82 workbook, `curated/ethnic_adjectives_da.csv` | `normalized/person_ethnic_descriptors{,_review}.csv` | yes |
| 2 | `build_web/build_web_data.py` | `normalized/*.csv` | `web/data/*.json` (7 files) | no |
| 3a | `build_mockup/build_diary_pages.py` | diary, references, entities, kb_diary_links | `mockup/diary-pages/*.html` (4,544) | no |
| 3b | `build_mockup/build_diary_index.py` | diary, references | `mockup/data/diary-index.js`, `diary-refs.js` | no |
| 4a | `build_mockup/build_works_extra.py` | entities, refs, `parsed/*.tsv`, work_languages, works_wikidata | `mockup/data/works-extra.js` | no |
| 4b | `build_mockup/build_persons_extra.py` | entities, refs, gender, role, ethnic, entity_types, crosswalk | `mockup/data/persons-extra.js` | no |
| 4c | `build_mockup/build_places_extra.py` | entities, refs, rejser, sv14, steder_verified | `mockup/data/places-extra.js` | no |
| 4d | `build_mockup/build_search_index.py` | the extras | `mockup/data/search-index.js` (16,444 entries) | no |
| 4e | `build_mockup/build_cooccurrence.py` | entities, references | `mockup/data/cooccurrence.js` | no |
| 4f | `build_mockup/build_nation_index.py` | ethnic, work_languages, nation tables | `mockup/data/nation-index.js` | yes |

Three stages exist but are **not in `build_all.py`**: `build_kb_links.py`,
`reconcile_steder_categories.py` (both run by hand; their committed output is
read by 3a and 4c) and `build_timeline_index.py` (wired in only on the
`roadmap-preprocessing-handover` branch).

### What does not run

`scripts/parsers/` holds 46 files. Seven are **register parsers** (music,
novels/plays/tales, non-fiction, personregister XI, gender, role, ethnic
descriptors) that are genuinely re-runnable. The other ~39 are the
**segmentation cleaning chain**: paired `suggest_*` → `apply_*` passes, plus
`split_*`, `merge_*`, `dedupe_*`, `refine_*`, `fix_*`, `link_*`, `import_*`,
`harvest_*`, `calibrate_*`, `clean_*`, `compare_*`. Every one is a **one-shot
pass that has already been applied** to `data/parsed/personregister_xi_parsed.tsv`.
They are kept for audit. Re-running a register parser discards the entire
chain.

`scripts/correspondence/` (9 scripts, Collin-letter indexing) and
`scripts/place_typology/` (4 scripts) are likewise occasional curation passes
whose output is committed.

### Documentation drift

`docs/pipeline/stages.md` documents a **six-stage model** — slice → parse →
OpenRefine → normalised CSV → Power Pivot star schema → optional Postgres.
This is not what `build_all.py` runs. Stage 3 (OpenRefine) is not used
anywhere in the code; Stage 5 (Power Pivot) happens *upstream* in the
spreadsheets, not downstream of the CSVs as drawn; Stage 6 (Postgres) points
at a repo that has moved twice. `docs/data-model/october-pipeline.md` documents
a third, different three-stage shape and says of itself "this document records
the proposal — it is not yet ratified".

Per §1 of the brief — verify documentation against code — **none of the three
pipeline documents describes the pipeline that runs.** This matters for the
migration: they cannot be used as the specification.

### Tests

19 tests on `main`, of which two guard cleaning output
(`test_personregister_xi_parsed.py`, `test_person_emendations.py`) and the
rest guard build output and stale references. **There is no test comparing the
pipeline's output to its input, and no test of record counts, join integrity,
or duplicate freedom** — the segmentation record explicitly notes "ingen
automatiseret regressionstest for dublet-frihed" and that its coverage
measurement used an ad-hoc method with "ingen færdig scriptfil".

---

## B. Repository B analysis

Empty. Its intended role, from the brief and from the planning decision: the
authoritative home for everything between raw sources and prepared data —
ingest, clean, segment, normalise, enrich, validate, and publish a defined
package that `hca-open-repo` builds the website from.

Two properties follow from the third-repo finding and should be designed in
from the first commit:

- **B publishes an explicit interface, not a folder.** PR #1's
  `scripts/publish.py` already models this: a hard-coded `INTERFACE` list of
  25 files, `--into` to copy, `--check` to report drift without changing
  anything. Keep it.
- **B is the only place that derives facts.** The boundary rule from `10d059f`
  is sound and survives: *a stage stays in the publication repo if it shapes
  prepared data into a presentation artifact; it moves here if it derives a
  fact about the data.*

---

## C. Complete transformation map

### Sources

| Source | Kind | Feeds |
|---|---|---|
| `HCA REPOSITORY V0.82/HCA-Repository V0.82.xlsx` | one flat workbook, one `Registry` sheet, H1–H4 classification columns | **the live site** — entities, diary, references |
| `HCA REPOSITORY V0.92/*.xlsx` (9 files) | 5 PowerQuery extracts + 4 PowerPivot star schemas | `normalized_v092/` — persons, places, diary VI–VII, references, timeline. **No works register.** |
| `HCA REPOSITORY V0.94/*.xlsx` (5 files) | renamed, numbered flat registries + a spec workbook | **Not yet ingested.** Works, places, 10-volume page list, calendar, controlled vocabularies, an Excel→JSON mapping. **No persons register.** See §F.1. |
| `Rejser_HCA_X.htm` | scraped from rejser.hcax.dk | 377 geocoded places, journeys |
| `SV14_places.xml` | TEI place-list | coordinates for places Rejser misses |
| `Personer _ HCA_tsv.txt` | independent pre-segmented transcription, 10,228 rows | **ground truth** for person-register segmentation coverage |
| `1-KBDiaryLinkData-PQ-links-active.xlsm` | PowerQuery workbook | KB facsimile permalink per diary page |
| `Steder_i_dagboegerne_verificeret_udfyldt VER 1.0.xlsx` | human-verified | place category + country |
| `andersen-hc_dagboeger_11.pdf` + OCR variants | Rønlev scans | personregister XI segmentation |
| `raw/DiaryVol6–10.docx`, `DiaryVol6/7 V0.8.xlsx` | legacy | **nothing — no script reads them** |

### Flow

```
V0.82 workbook ──1a──▶ entities.csv ─┬─────────────────────────────────┐
                       diary.csv     │                                 │
                       references.csv│                                 │
                                     │                                 │
V0.92 (9 books) ─1a'─▶ normalized_v092/  ── timeline.csv ──────┐       │
                       (entities/refs UNUSED by the site)      │       │
                                     │                         │       │
Rejser.htm ─────1b──▶ rejser.tsv ────┤                         │       │
SV14.xml ───────1c──▶ sv14_reconciled┤                         │       │
(entities) ─────1d──▶ work_languages ┤                         │       │
V0.82 ──────────1e──▶ ethnic_descr.  ┤                         │       │
V0.82 ──────────1f──▶ person_gender  ┤   ENRICHMENT            │       │
KB .xlsm ───────1g──▶ kb_diary_links ┤   (facts about data)    │       │
Steder .xlsx ───1h──▶ steder_verified┤                         │       │
                                     │                         │       │
OCR PDF ──parse──▶ personregister_xi_parsed.tsv                │       │
                    │  ~39 one-shot cleaning passes            │       │
                    └──▶ 10,136 rows ── NOT CONSUMED BY THE BUILD ✗    │
                                     │                         │       │
register slices ──parse──▶ parsed/{music,non_fiction,          │       │
                                   novels_plays_tales}.tsv ─┐  │       │
                                     │                      │  │       │
        ═══════════ prepared-data boundary ═════════════════╪══╪═══════╪══
                                     │                      │  │       │
                     ┌───────────────┴──────────────────────┴──┴───────┘
                     ▼
  stage 2  ─▶ web/data/*.json          (7 files, the Places demo)
  stage 3a ─▶ mockup/diary-pages/*.html (4,544 pages)
  stage 3b ─▶ diary-index.js, diary-refs.js
  stage 4a ─▶ works-extra.js      4d ─▶ search-index.js
  stage 4b ─▶ persons-extra.js    4e ─▶ cooccurrence.js
  stage 4c ─▶ places-extra.js     4f ─▶ nation-index.js
                     ▼
              mockup/ — the live site
```

### Classification demanded by §2 of the brief

| Class | Members |
|---|---|
| **Essential data preparation** | 1a ingest; the register parsers; 1b–1h enrichment; the person-register segmentation |
| **Website-specific preparation** | 2, 3a, 3b, 4a–4f — every one shapes a presentation artifact and would have to be recomputed for any new view |
| **Historical processing** | the ~39 applied one-shot cleaning passes; `scripts/migration/` (Tidstavle from EPUB/SQL, done); `web/` (the October Places demo, superseded by `mockup/`) |
| **Duplicated processing** | `build_cooccurrence.py` vs V0.92 `FactDiaLocPerPag`; country derivation in three places; name normalisation in two |
| **Obsolete processing** | `raw/` legacy docx/xlsx/PDF that no script reads; `data/normalized_v092/{entities,references,diary}.csv` (produced, never consumed) |

---

## D. Migration inventory

| Component | Current function | Destination in B | Action | Reason |
|---|---|---|---|---|
| `normalization/hca_xlsx_to_csv.py` | V0.82 workbook → 3 core CSVs | `scripts/normalization/` | **migrate unchanged** | The pipeline's spine; validated byte-identical. |
| `normalization/hca_v092_to_csv.py` | V0.92 release → parallel CSVs | `scripts/normalization/` | **migrate, then gate** | Keep; make it the target source once a `WorkData-PQ` workbook ships (§H). |
| — | *(new)* V0.94 ingester | `scripts/normalization/hca_v094_to_csv.py` | **build new** | §F.1. Emits to `data/normalized_v094/` for verification first, per step 5b. |
| `new input/HCA REPOSITORY V0.94/` | the newest source release | `data/raw/HCA REPOSITORY V0.94/` | **rehome** | It currently sits outside `data/raw/`, where no convention reaches it. Move it before writing the ingester. |
| `parsers/parse_{music_register,novels_plays_tales,non_fiction}.py` | slice workbook by register → TSV | `scripts/parsers/` | **migrate unchanged** | Re-runnable; output is in the published interface. |
| `parsers/parse_personregister_xi.py` | OCR PDF → segmented TSV | `scripts/segmentation/` | **migrate + rehome** | Head of the segmentation chain; deserves its own namespace. |
| `parsers/` ~39 `suggest_*`/`apply_*`/`split_*`/`merge_*`/`dedupe_*`/`refine_*`/`fix_*` | one-shot passes, already applied | `scripts/segmentation/passes/` + one runner | **consolidate** | See §E.2. The decisions become data; the scripts become one replayable stage. |
| `parsers/parse_person_{gender,role,ethnic_descriptors}.py` | derive facet columns | `scripts/enrichment/` | **migrate + rehome** | These derive facts from descriptions — enrichment, not parsing. Their placement in `parsers/` is historical. |
| `parsers/add_language_column.py` | language tag on any stage-2 TSV | `scripts/enrichment/` | **consolidate** with `detect_work_language.py` | Two implementations of one operation over `lingua`. |
| `parsers/ner_page_grounding.py` | NER page grounding | `scripts/enrichment/` | **migrate, mark dormant** | Output (`ner_page_grounding.csv`, 1 MB) is committed but read by no build stage. Decide in phase 2. |
| `parsers/wikidata_lookup.py` | QIDs + hero images | `scripts/curation/` | **migrate + rehome** | Reads the publication repo's *built* cards. Human-driven, not a pipeline stage — isolate it so that cross-repo read is visible. |
| `parsers/merge_manual_corrections.py` | fold reviewed corrections back in | `scripts/segmentation/` | **migrate — NOT in PR #1** | Added to A's `main` on 2026-09-06, after the split branch. See §I.0. |
| `parsers/_common.py`, `xlsx_to_tsv.py`, `build_review_workbook.py`, `compare_to_xlsx.py` | shared I/O helpers | `scripts/_lib/` | **consolidate** | Shared plumbing; one home. |
| `build_mockup/reconcile_sv14_geo.py` | TEI → coordinates | `scripts/enrichment/` | **migrate unchanged** | Derives a fact. Already reclassified in PR #1. |
| `build_mockup/detect_work_language.py` | title → probable language | `scripts/enrichment/` | **migrate unchanged** | Same. |
| `build_mockup/build_kb_links.py` | `.xlsm` → permalinks | `scripts/enrichment/` | **migrate unchanged** | Same. Also: add to the runner — it was hand-run in A. |
| `build_mockup/reconcile_steder_categories.py` | verified workbook → categories | `scripts/enrichment/` | **migrate unchanged** | Same. Also add to the runner. |
| `build_web/parse_rejser_htm.py` | scraped HTML → travel TSVs | `scripts/enrichment/` | **migrate unchanged** | Same. |
| `place_typology/*` (4) | place classification | `scripts/place_typology/` | **migrate unchanged** | Curation; output committed. |
| `correspondence/*` (9) | Collin-letter indexes + matching | `scripts/correspondence/` | **migrate unchanged** | Curation; three read built cards — flag as cross-repo. |
| `correspondence/name_normalize.py` | name normalisation | `scripts/_lib/names.py` | **consolidate** | The segmentation record's measurement method reimplements this ad hoc; unify. |
| `migration/migrate_tidstavle_{epub,sql}.py` | Tidstavle → CSV | `scripts/migration/` | **migrate, freeze** | Done once; output committed. Keep for provenance, exclude from the runner. |
| — | *(new)* declared stage runner | `scripts/run_pipeline.py` | **adopt from PR #1** | Replaces `build_all.py`'s ingest half. |
| — | *(new)* interface contract | `scripts/publish.py` | **adopt from PR #1** | The A↔B contract, with `--check` drift reporting. |
| — | *(new)* index integrity checks | `scripts/validation/check_indexes.py` | **adopt from PR #1** | Dangling cross-refs + kind-specific required values. |
| — | *(new)* equivalence harness | `scripts/validation/compare_to_reference.py` | **build new** | §J. The segmentation coverage measurement has never been a script. |
| `build_mockup/build_{works,persons,places}_extra.py` | prepared data → JS cards | — | **leave in A** | Presentation artifacts. |
| `build_mockup/build_{diary_pages,diary_index,search_index,cooccurrence,nation_index,timeline_index}.py` | → HTML / JS | — | **leave in A** | Same. |
| `build_web/build_web_data.py` | → `web/data/*.json` | — | **leave in A, then retire** | The October Places demo, superseded by `mockup/`. Retiring it is A's call, not B's. |
| `build_mockup/build_cooccurrence.py` | recompute co-occurrence from references | — | **leave in A; revisit at V0.92 cutover** | V0.92 ships this as a fact table (§E.1). |
| `design_sync/apply_component.py` | Claude Design → CSS | — | **leave in A** | Frontend tooling. |
| `tests/test_personregister_xi_parsed.py`, `test_person_emendations.py` | guard cleaning output | `tests/` | **migrate unchanged** | They test what moves. |
| `tests/` (17 others) | guard build output | — | **leave in A** | They test what stays. |
| `data/raw/*` | all sources | `data/raw/` | **migrate** | B owns the sources; A proved it needs none of them. |
| `raw/*` (legacy docx, PDFs, V0.8 xlsx) | — | `data/raw/legacy/` | **migrate, quarantine** | No script reads them; purpose not established. Keep for reference, exclude from the pipeline (§K). |
| `data/curated/*` — 8 authority tables | vocabularies the build reads | `data/curated/` | **migrate unchanged** | Part of the published interface. |
| `data/curated/*` — ~30 review artefacts | process residue of the cleaning chain | `data/review/` | **migrate + rehome** | Separate the 8 live inputs from the 30 audit files; today they sit in one folder. |
| `data/parsed/personregister_xi_parsed.tsv` | 10,079 segmented person entries + 45,293 references | `data/parsed/` | **migrate + promote to the interface** | **Decided: this becomes the person source** (§E.3). Must be added to `publish.py`'s `INTERFACE`, which currently excludes it. |
| `data/curated/person_entity_types.tsv` | the gate keeping families, firms and the register's dog out of the person facets | `data/curated/` | **migrate + re-key** | Keyed on `Reg…` ids today; must be re-keyed to `PerXI…` with the crosswalk from §I.10. |
| `docs/pipeline/{README,stages}.md` | describes a pipeline that does not run | `docs/` | **replace** | §0 / §A. Rewrite conceptually, per brief §15. |
| `docs/data-model/october-pipeline.md` | unratified 3-stage proposal | `docs/history/` | **archive** | Superseded; keep for reasoning provenance. |
| `docs/data-model/*` (40 files) | data-model documentation | split | **split by concern** | Model docs that describe *sources and cleaning* belong in B; those that describe *views* stay in A. |

---

## E. Redundancy analysis

**E.1 — Co-occurrence is computed in Python from data that already ships as a
fact table.** `build_cooccurrence.py` reads `entities.csv` + `references.csv`
and counts page-level entity pairs. The V0.92 release ships
`FactDiaLocPerPag` — **92,307 rows** — which is that join, computed in
PowerPivot. Two implementations of one operation.

**Revised after V0.94 (§F.2): this simplification is no longer available.**
V0.94 withdrew the fact tables; it has no `FactDiaLocPerPag` and encodes
references as text lists instead. So `build_cooccurrence.py` stays, and the
cutover no longer deletes it. If the co-occurrence table is wanted upstream,
it has to be asked for — it is now a request to the spreadsheet side, not a
migration step (§K).

**E.2 — ~39 one-shot cleaning scripts encode decisions that should be data.**
Each `suggest_*` wrote a review file, a human approved it, the paired
`apply_*` mutated `personregister_xi_parsed.tsv`. The scripts are now
archaeology: they cannot be re-run in place, they cannot be run out of order,
and the order they *were* run in survives only as prose in
`person-register-segmentation.md`. The information worth keeping is the
**approved decisions** (which rows were split, merged, imported, renamed, and
why), not the code that applied them. One replayable segmentation stage reading
a decision table would reproduce the file from the parser output, make the
chain testable, and make the ~39 scripts an archive rather than a dependency.
This is the largest single simplification available.

**E.3 — The largest cleaning product is not consumed.**
`data/parsed/personregister_xi_parsed.tsv` — 10,136 rows, 3 MB, the output of
that entire chain — is read by **no build stage**. Verified directly: no
script under `scripts/build_mockup/` or `scripts/build_web/` mentions it, and
PR #1's interface document states it outright. The site's persons come from
`entities.csv`, i.e. from the V0.82 workbook. So the project maintains two
independent person registers, and the better-segmented one is invisible to
users.

### E.3 resolved — the segmentation output becomes the person source

**Decision (2026-09-12): persons come from the cleaning repo's segmentation
output.** `data/parsed/personregister_xi_parsed.tsv` is promoted from an
unused by-product to the authoritative person register, and V0.82's person
rows in `entities.csv` are demoted to a crosswalk and fallback.

This is the right call on the evidence, and it is a bigger change than it
looks. What the file actually contains, measured directly:

| | |
|---|---:|
| Rows | **10,079** — 9,652 standard entries, 410 cross-references, 17 sub-entries |
| Person→page reference pairs | **45,293**, over 4,366 distinct `(vol, page)` |
| Birth year populated | 7,669 |
| `see_also` populated | 444 |
| Rows with no references | 593 |

Against what the site consumes today — A's `references.csv` carries **39,361**
person reference rows over 4,373 distinct pages:

| Comparison | Result |
|---|---|
| Reference pairs | parsed **45,293** vs live **39,361** — the segmentation carries **~15 % more** person references |
| Distinct pages | 4,366 vs 4,373; **4,246 shared**, 120 parsed-only, 127 live-only |
| Join key | both express references as `(vol, page)` — and so does V0.94's `DiaryPagID` (`I-1`). All three converge on the same key. |

So the segmentation output does not merely restate the person data: it is
**richer than what the site shows**, and it can supply the person half of
`references.csv` on its own, without needing to join to it.

**But it has no `Reg…` identifier.** Its id space is its own —
`PerXI00001`, `PerXI00002`, … — with no column carrying the workbook's
`RegistryTitelID`. That is the whole cost of this decision, and §I.10 is
where it gets paid.

**And its reference parsing has demonstrable noise.** Among the 120
parsed-only pages is `('I', '1841')` — a year captured as a page number.
Before this file drives the site, `11_references_parsed` needs a validation
pass against the diary page list (§J.6). A page number that does not exist in
`3-DIARY-PAGES` is a parse error, and V0.94 now makes that check possible for
all ten volumes.

**One discrepancy to note:** the segmentation record documents 10,136 rows
(9,725 / 394 / 17); the file now holds 10,079 (9,652 / 410 / 17). The file has
moved since the record was written. Re-measure against the reference
transcription (§J.3) before trusting either figure.

### E.3a — Why not V0.92 for persons, and what to do about readiness

A reasonable reaction to §I.10's cost is to reach for V0.92's person dimension
instead: it is a real workbook, it was ingested and verified, and it does not
need a derived crosswalk. **Measured, it is strictly worse than either
alternative, and it does not avoid the problem it appears to avoid.**

| | V0.82 (live today) | V0.92 | Segmentation output |
|---|---:|---:|---:|
| Persons | 10,228 | **8,917** | 10,079 |
| Person→page references | 39,361 | **24,845** | 45,293 |
| Distinct pages referenced | 4,373 | **738** | 4,366 |
| Diary volumes covered | **I–X** | **VI–VII only** | **I–X** |
| Crosswalk to the live `Reg…` ids | *is* the live ids | **none** | none (derivable) |

Three findings, each independently disqualifying:

1. **V0.92's person references cover two volumes out of ten.** All 24,845 of
   them fall in VI and VII — 12,441 and 12,404 — across 738 distinct pages.
   Adopting it would drop person references on **8 of the 10 diary volumes**,
   an 83 % loss of referenced-page coverage. This is not a subtle regression;
   it is most of the site's person navigation.
2. **It has 1,311 fewer persons than the live site** and 1,162 fewer than the
   segmentation output.
3. **It has no `Reg…` crosswalk either.** Its ids are `P{PerID:05d}`, a
   deliberately separate space chosen "so the two CSV sets never collide if
   joined". So V0.92 carries the *same* identifier problem as the segmentation
   output — with none of the compensating gain.

V0.92's person dimension is a two-volume slice built to prove a modelling
approach, not a replacement register. It stays what it already is: a
verification surface.

**But the readiness concern behind the question is correct**, and it points at
a different answer. The segmentation output is not yet coordinated with the
other indices: it is keyed on `PerXI…`, while `person_entity_types.tsv`, the
gender / role / ethnic facets, `breve_person_crosswalk.csv` and every person
URL on the site are keyed on `Reg…`.

What makes that tractable is that **cross-index coordination in this project
runs through diary pages, not through direct entity links.** Persons are
related to works and places only by appearing on the same page — that is what
`references.csv` encodes and what `build_cooccurrence.py` counts. The
segmentation output already carries 45,293 `(vol, page)` pairs in exactly that
shape. So it is not structurally uncoordinated; it is missing one bridge —
the `PerXI… ↔ Reg…` crosswalk — and that bridge is derivable by a method the
project has already used and documented.

**So: keep V0.82 as the person spine, and adopt the segmentation output
additively rather than as a cutover.** That is the change to §I.10 below. It
gets the 45,293 references and the 444 `see_also` edges in front of users
without betting the person register on an unvalidated id mapping, and every
stage of it is reversible.

**E.4 — Country is derived three times.** A 33-country European bounding-box
gazetteer is inlined in `build_web_data.py`; `steder_verified_categories.csv`
carries human-verified countries; `steder_country_to_nation_da.csv` maps
country → nation bucket. Three sources of one attribute, with no documented
precedence.

**V0.94 makes this worse before it makes it better**: `4-LOCATION-Registry`
carries `Country` on 2,430 of 2,433 places, a *fourth* source. It is the best
of them — maintained by the people who verify it — so the resolution is to
make it authoritative and reduce the other three to fallbacks, not to leave
four in place.

**E.5 — Language detection exists twice.** `parsers/add_language_column.py`
and `build_mockup/detect_work_language.py` both wrap `lingua` over title
strings with the same language restriction list.

**E.6 — Name normalisation exists twice, one of them unwritten.**
`correspondence/name_normalize.py` is a real module; the segmentation
coverage measurement used an equivalent normalisation that the record
describes step by step and then notes has "ingen færdig scriptfil". The
second one is exactly what §J needs, and it does not exist.

**E.7 — Two parallel source generations are both ingested; one is discarded.**
`normalized_v092/{entities,diary,references}.csv` are produced on every full
run and consumed by nothing (only `timeline.csv` from that folder is used).

**E.8 — `data/curated/` mixes 8 live inputs with ~30 audit artefacts.** The
build reads eight vocabularies from it; the other thirty are `*_review.tsv`
suggestion files, manual-correction workbooks and snapshots. One folder, two
lifecycles.

**E.9 — Three pipeline documents, none describing the pipeline.** See §A.

---

## F. Spreadsheet analysis

The brief's §4 asks which spreadsheet variant is authoritative and whether
JavaScript repeats what PowerQuery already did. The answer reframes the whole
migration.

### F.1 The V0.94 release — what actually arrived

Five workbooks, renamed and numbered. The naming convention of V0.92
(`-PQ-` for PowerQuery extracts, `-PP-` for PowerPivot models) is gone; these
are flat, single-sheet registries plus one specification workbook.

| File | Sheet | Data rows | Columns |
|---|---|---:|---|
| `1-SITES.xlsx` | `Kontrollister`, `JSON-mapping`, `Vejledning` | — | controlled vocabularies; an Excel→JSON field map; a load-order and quality spec |
| `2-CALENDAR.xlsx` | `Calendar` | 36,889 | `DateID`, `PrecisionDecade`, `PrecisionYear`, `PrecisionMonth`, `DayNumber1800`, `Year`, `MonthNo`, `MonthDayNo`, `MonthText`, `DayText`, `Quarter`, `Week`, `ISOWeek` |
| `3-DIARY-PAGES.xlsx` | `DiaryPages` | 4,413 | `DiaryPagID` (`I-1`), `Volumen`, `Page`, `Year`, `Month`, `Day`, `AI-genSummary`, `HCACSummary`, `KBLinkString`, `SourceStatus` |
| `4-LOCATION-Registry.xlsx` | `Location` | 2,433 | `LocationID` (`LOC1000000`), `Location`, `TypeH1`, `Country`, `Category`, `Latitude`, `Longitude`, `SourceStatus`, `FKPageKeys`, `OLDLocationID` |
| `5-WORK-Registry.xlsx` | `Work` | 3,590 | `WorkID` (`WOR000000`), `WorkTittle`, `Sequense`, `TypeH1`, `GenreH2`, `FormH3`, `SubFormH4`, `See`, `See also`, `Artist`, `MuseumEtc`, `City`, `SourceStatus`, `FKDiaryPagIDs`, `OLDWorkID` |

Measured against A's current data — every figure below was checked against
`data/normalized/entities.csv` and `references.csv`, not read off the
documentation:

| Fact | Evidence |
|---|---|
| **Works register ships at last** | 3,590 rows, against A's 3,708 work entities. The H1–H4 taxonomy is carried as four real columns. |
| **Perfect work crosswalk** | `OLDWorkID` (`Reg001445`, …) resolves **3,590 / 3,590** into A's `entities.csv`. |
| **Broken place crosswalk** | `OLDLocationID` (`LOC000001`, …) resolves **0 / 2,433**. It carries V0.92's own scheme, not the live `Reg…` ids. |
| **Persons are absent** | No person workbook. V0.92 shipped 8,917; A holds 10,228. |
| **Full volume coverage, no text** | 4,413 pages across volumes I–X — against A's `diary.csv`, which holds 2,177 rows for volumes VI–VII only. But V0.94's pages carry no diary text. |
| **References re-encoded, not modelled** | `FKDiaryPagIDs` / `FKPageKeys` are space-separated `VOL-PAGE` lists in the dimension row. Spot-checked: `Reg001445` → `III-64 III-179 III-181 …`, exactly A's `references.csv` rows for that work. |
| **KB links now in the source** | `KBLinkString` filled on 4,413 / 4,413 pages. |
| **Place country and category now in the source** | `Country` on 2,430 / 2,433, `Category` on 2,429 / 2,433. |
| **Artist, museum and city now real columns** | `Artist` on 2,113, `MuseumEtc` on 576, `City` on 574 of 3,590 works. |
| **Date precision now explicit** | `PrecisionYear` / `PrecisionMonth` (`1825-XX`, `1825-09-XX`) and a `DateStatus` vocabulary of Exact / Month only / Year only. |
| **An editorial status column** | `SourceStatus` ∈ {Ready, Needs review, Exclude}. Places: 2,416 Ready / 17 Needs review. Works: **all 3,590 Needs review** — provisioned but not yet worked. |
| **Coordinates provisioned but empty** | `Latitude` / `Longitude` filled on **0 / 2,433**. |
| **Cross-references provisioned but empty** | `See` / `See also` filled on **0 / 3,590**. |

### F.2 What V0.94 changes structurally — and what it withdraws

**The gains are real and they retire work in B.** Four things A currently
derives are now given as source columns: KB permalinks (`build_kb_links.py`
plus the `.xlsm`), verified place country and category
(`steder_verified_categories.csv`, and the 33-country bounding-box gazetteer
inlined in `build_web_data.py`), the artist/museum/city fields A extracts by
regex from work-title parentheses, and date precision, which A handles ad hoc.
The 10-volume page list is a genuine expansion over A's two-volume `diary.csv`.

**But the star schema was withdrawn.** V0.92's central advantage — that
PowerPivot had already computed the joins — is gone:

| V0.92 | V0.94 |
|---|---|
| `FactDiaPerPag` — person × page | — |
| `FactDiaLocPag` — place × page | folded into `FKPageKeys` as a text list |
| `FactDiaLocPerPag` — **92,307 rows**, place × person × page | **absent** |
| `DiaryCalStarSchema-PP` — date-joined facts | folded into page `Year`/`Month`/`Day` text |

This matters for §E.1. The co-occurrence simplification — delete
`build_cooccurrence.py`, read `FactDiaLocPerPag` instead — **has no successor in
V0.94**. A space-separated key list inside a cell is a less useful form than
either a fact table or A's `references.csv`: it must be split, trimmed and
re-joined before it can be used, and it cannot express per-reference attributes
such as `seq`.

**The `1-SITES.xlsx` spec workbook explains the id problem.** Its `JSON-mapping`
sheet describes a **page-centric** model in which places and works are embedded
as positional tuples inside page rows, with ids specified as "deterministic ID
for unique 3-tuple / 5-tuple" — *derived from content, not carried from the
source*. That is the opposite of this plan's stable-identifier constraint, and
it is why `OLDLocationID` does not reach A's ids while `OLDWorkID` does.

**The delivered workbooks also do not match their own specification.** The
`Vejledning` load order names eight tabs — Dagbogssider, Kalender, **Personer,
PersonSide**, Steder, **StedSide**, Værker, **VærkSide** — and cites 9,520
persons and 81,520 relations. Delivered: no `Personer` tab at all, and the
three bridge tables exist only as denormalised text columns. The spec describes
a model the files do not yet contain, so read its figures as intent, not as
data on hand.

### F.3 Which is authoritative

| Workbook set | Status |
|---|---|
| `HCA-Repository V0.82.xlsx` | **Authoritative today.** One flat `Registry` sheet with `RegistryCategory (H1)` / `WorkGenre (H2)` / `RegistryForm (H3)` / `WorkSubForm (H4)`. Everything on the live site descends from it. |
| `HCA REPOSITORY V0.92/` (9 workbooks) | **Superseded, but still the only source of two things:** the person dimension and the star-schema fact tables. Keep it until V0.9x replaces both. |
| `HCA REPOSITORY V0.94/` (5 workbooks) | **The newest release and the authoritative source for works, places, pages and calendar** — but not for persons, references-with-`seq`, coordinates, or diary text. Not a drop-in replacement for either predecessor. |
| `raw/HCA-Repository V0.82.xlsx`, `raw/DiaryVol6/7 V0.8.xlsx` | Duplicates / predecessors. Intermediate. No script reads them. |
| `Steder_i_dagboegerne_verificeret VER 1.0.xlsx` | Authoritative for the human-verified place attributes only. |
| `1-KBDiaryLinkData-PQ-links-active.xlsm` | Authoritative for KB permalinks. PowerQuery-driven. |

### What already happens in PowerQuery / PowerPivot

The V0.92 release is not another export of the same flat sheet — it is a
**star schema built in Excel**. The naming says so: `-PQ-` files are
PowerQuery extracts, `-PP-` files are PowerPivot models.

| Workbook | What it already contains |
|---|---|
| `PersonData-PQ` | the person dimension — `PerID`, RegistryTitle, RegistryDescription, birth/death years, **already split into columns** |
| `LocationData-PQ` | the place dimension — LocID, title, country, region, lat/lon, plus a `Raw.See-Also` sheet structuring cross-references |
| `DiaryData-PQ` | the diary-page dimension — volume, page, date, heading, text lines |
| `CalendarData-PQ` | a proper calendar dimension |
| `DiaryFactDim-PQ` | the dimension keys |
| `DiaryPerStarSchema-PP` | `FactDiaPerPag` — person × page |
| `DiaryLocStarSchema-PP` | `FactDiaLocPag` — place × page |
| `DiaryLocPerStarSchema-PP` | **`FactDiaLocPerPag`, 92,307 rows — place × person × page** |
| `DiaryCalStarSchema-PP` | date-joined facts |

Compare against what A's Python does: `hca_xlsx_to_csv.py` splits the flat
`Registry` sheet into entity types, derives years from label parentheses,
and builds the entity × page join. **That is the same modelling work, done
twice, in two technologies, from two generations of the same source.** The
V0.82 Python path exists because V0.82 was flat; V0.92 is not flat.

Two specific duplications:

- The **entity × page join** is `references.csv` in Python and
  `FactDiaPerPag` + `FactDiaLocPag` in PowerPivot.
- **Co-occurrence** is `build_cooccurrence.py` in Python and
  `FactDiaLocPerPag` in PowerPivot (§E.1).

And one thing PowerQuery does *better*: `LocationData-PQ`'s `Raw.See-Also`
sheet holds place cross-references as structured rows. A's Python buries the
same information inside `RegistryTitle` strings and parses it back out with
regex. The V0.92 sheet is currently an unfinished export (`Metric` / `Value`
columns, 85 rows) — it needs a format decision from the spreadsheet side
before it can be loaded.

### Where each operation belongs

| Operation | Best location | Reason |
|---|---|---|
| Entity typing, H1–H4 classification | **upstream (V0.94)** | Four real columns on the work registry. Settled. |
| Fact joins (entity × page) | **B** — *revised* | V0.92 had them as fact tables; V0.94 withdrew them (§F.2). Until a bridge table returns, B splits `FK…` lists or keeps deriving `references.csv`. |
| Cross-reference structuring (`see` / `see also`) | **upstream** | V0.94 provisions both columns on works — but they are 0 % filled. Structured rows beat regex over label strings *once populated*; until then B keeps the regex. |
| Artist / museum / city on works | **upstream (V0.94)** | Now real columns (2,113 / 576 / 574). Retires the title-parenthesis regex in `billedkunst-artist-extraction.md`. |
| KB diary permalinks | **upstream (V0.94)** | `KBLinkString` on all 4,413 pages. Retires `build_kb_links.py` and the `.xlsm`. |
| Place country + category | **upstream (V0.94)** | 2,430 / 2,429 of 2,433 filled. Becomes authoritative over the other three sources (E.4). |
| Date precision (`YYYY-MM-XX`) | **upstream (V0.94)** | `PrecisionYear` / `PrecisionMonth` + a `DateStatus` vocabulary. Retires A's ad-hoc fallback handling. |
| Birth/death years, life-date parsing | **PowerQuery** where the source has them as columns; **B** otherwise | V0.92 has `YearOfBirth`/`YearOfDeath` as real columns; V0.94 has no person register at all. Until persons return, V0.82 + regex remains the only path. |
| Register segmentation (personregister XI from OCR) | **B** | Requires OCR handling, diff against an independent transcription, and a reviewed decision record. Not spreadsheet work. |
| Geocoding reconciliation (Rejser, SV14) | **B** | Reads HTML and TEI; joins on normalised strings. |
| Language detection | **B** | Needs `lingua`. |
| Gender / role / ethnic-descriptor facets | **B** | Derived from free-text descriptions by rule tables that live in `data/curated/`. |
| KB permalinks | **PowerQuery** (already) → **B** ingests | The `.xlsm` is already PowerQuery-driven; B just reads the result. |
| Verified place categories | **spreadsheet** (already) → **B** ingests | Human verification belongs in the tool the humans use. |
| Co-occurrence counting | **B** — *revised* | V0.94 withdrew `FactDiaLocPerPag`. Stays in A/B until a bridge table is requested and delivered (§K). |
| Geocoding (lat/lon) | **B** | V0.94 provisions the columns but fills none. Rejser + SV14 remain the only coordinate sources. |
| Person register, segmentation, facets | **B** | No person workbook in V0.94. Entirely B's for the foreseeable future. |
| Denormalised view shapes, cards, HTML, search index | **A (build-time)** | Presentation. |

**Conclusion for §4 of the brief, revised after V0.94:** the direction still
holds — move derivation upstream where the collaborators already maintain it,
and V0.94 delivers four such moves outright (KB links, place country/category,
artist/museum/city, date precision). But the *mechanism* the original analysis
recommended has been withdrawn: the upstream star schema is gone, so the joins
come back downstream. The upstream layer is now strongest at **attributes** and
weakest at **relations** — which is the opposite of V0.92, and is the single
most important thing to say back to the spreadsheet side.

---

## G. Target architectures

### Option A — Conservative port

Import PR #1's tree into B as-is. Reconcile the drift. Merge A's counterpart
commit. Stop.

*For:* fastest; already byte-identical-validated. *Against:* delivers a clean
boundary but **no simplification** — all 74 scripts survive, the ~39-script
chain stays, the three broken pipeline docs get replaced by one accurate one
and that is the whole gain. Does not satisfy brief §7 or §10.

### Option B — Port, then consolidate the cleaning chain

Option A, plus: the segmentation chain becomes one replayable stage driven by
a decision table; the enrichment passes are unified under one namespace and
one declared runner; the duplicated language/name/country derivations are
collapsed; `data/curated/` is split into live inputs and audit artefacts; the
coverage measurement becomes a real validation script.

*For:* removes the historical complexity the brief targets while keeping every
scholarly decision intact and auditable. Testable for the first time.
*Against:* the segmentation consolidation is real work and touches the most
delicate data in the project.

### Option C — Option B, plus a planned V0.92 cutover

Option B, plus: B is designed so that the source generation is a **parameter**,
not an architecture. The V0.92 star schema becomes the target input; V0.82
remains the active input until a `WorkData-PQ` workbook exists; the cutover is
a flag flip that deletes, rather than rewrites, the Python that re-derives what
PowerPivot already computed (`build_cooccurrence.py`, the label-parenthesis
year regex, parts of the entity split).

*For:* the only option that acts on §F's finding. Moves work upstream to where
the collaborators already do it (brief §3, §4). Each future workbook release
shortens the Python rather than lengthening it. *Against:* depends on a
deliverable from the spreadsheet side that has no date.

### Option D — Re-engineer

Replace the CSV-and-stdlib pipeline with a declarative stage runner over
DuckDB or Polars, with schema validation (pandera/Great Expectations) and
Parquet intermediates.

*For:* real typing and validation; joins in SQL instead of Python dicts.
*Against:* at this scale (~11k entities, ~39k references, ~92k facts) there is
no performance argument, and the October analysis already rejected these
formats for a reason that still holds — collaborators lose the double-click
affordance, and the project's maintainers are two citizen scientists and one
researcher, not a data-engineering team. Adding a framework contradicts brief
§16. **Not recommended.**

---

## H. Recommended architecture — Option C

### Shape

```
                     data/raw/                    ← B owns every source
                        │
        ┌───────────────┴────────────────┐
        │                                │
   [1] ingest                       [2] segment
   source generation is a               OCR/PDF → parsed register
   parameter, and now per-entity:       + replayable decision record
   works/places/pages ← V0.94           (was ~39 one-shot scripts)
   persons ← V0.82 (or V0.92)
        │                                │
        └───────────────┬────────────────┘
                        ▼
              data/normalized/  — the star-shaped core
                        │
                  [3] enrich          geocodes, languages, gender,
                        │             role, ethnicity, KB links,
                        │             verified place categories
                        ▼
                  [4] validate        index integrity, record counts,
                        │             join coverage, duplicate freedom,
                        │             equivalence vs. the previous run
                        ▼
                  [5] publish         scripts/publish.py — an explicit
                        │             file list + provenance manifest
                        ▼
        ══════════ the prepared-data interface ══════════
                        │
                  hca-open-repo  — builds HTML / JS cards / JSON
                        ▼
                     the website
```

Five stages, each a conceptual boundary that earns its place per brief §6:
ingest (source shape), segment (editorial decisions), enrich (derived facts),
validate (nothing crosses unchecked), publish (an explicit contract).

### The source parameter becomes per-entity — the one change V0.94 forces

The original recommendation was a single flag flipping the whole pipeline from
V0.82 to V0.92 once Works shipped. **V0.94 makes a whole-pipeline flip
impossible**, because no single release covers every entity:

| Entity | Best source today | Why not the newest |
|---|---|---|
| Works | **V0.94** | — ships 3,590 rows with a perfect `Reg…` crosswalk |
| Places | **V0.94** for attributes, V0.82 for identity | `OLDLocationID` resolves 0 / 2,433; coordinates 0 % filled |
| Diary pages | **V0.94** | — 4,413 pages, all ten volumes, KB links complete |
| Calendar | **V0.94** | — explicit precision columns |
| Diary text | **V0.82** | V0.94 carries no text |
| Work/place references | **V0.82** | V0.94's `FK…` lists cannot express per-reference order |
| **Persons** | **V0.82 today → the segmentation output once §I.10a validates** | V0.94 has no person register; **V0.92 is disqualified** — two volumes of references, 1,311 fewer persons, and no `Reg…` crosswalk either (§E.3a). The destination is `personregister_xi_parsed.tsv`; the route is additive, not a cutover. |
| **Person references** | **V0.82 + the segmentation output, merged** | Its `11_references_parsed` carries 45,293 `(vol, page)` pairs — ~15 % more than `references.csv` — keyed the way V0.94 keys pages. Folded in as extra rows at §I.10c, before any spine swap. |

So stage 1 ingests **per entity type**, each with a declared source and a
recorded provenance line in `_source.json`. That is a smaller, safer and more
honest mechanism than a global switch, and it is what lets V0.94's genuine
gains land now instead of waiting on a complete release that may never come.
It also makes the next release cheap: a new workbook changes one row of a
table, not the architecture.

### Why this one

- It keeps the boundary rule that was already validated byte-identical, so
  the riskiest part of the migration is a known quantity.
- It attacks the actual historical complexity — the ~39-script chain and the
  double-derivation against PowerQuery — rather than the JavaScript the brief
  expected to find and which does not exist.
- It moves transformation **upstream into the spreadsheets** where §F shows it
  already happens, instead of pulling more into Python. That is the direction
  brief §4 asks for and the one the project's staffing supports.
- It introduces no framework, no database, no new language.
- Every stage is build-time. Nothing moves to runtime.

### What stays in A, and why

The eight `build_mockup/` builders and `build_web_data.py`. Each turns
prepared data into a presentation artifact — an HTML page, a JS card, a
denormalised view shape — and each would have to be recomputed for any new
view. `build_cooccurrence.py` stays for now on the same test, and is
re-examined only at the V0.92 cutover, when it stops being a computation and
becomes a table read.

### Naming

`hca-open-repo-redesign` describes a moment, not a role. Once the migration
lands, rename it to something that says what it holds —
`hca-open-repo-data` or `hca-diary-data-prep`. GitHub redirects the old URL.
Worth doing before external links accumulate.

---

## I. Migration sequence

**Stage 0 — reconcile the drift first.** A's `main` moved on after the split
branch was cut (2026-09-05), and four things changed on the cleaning side of
the boundary that PR #1 does not have:

| | Drift |
|---|---|
| `scripts/parsers/merge_manual_corrections.py` | new on `main` (237 lines), absent from PR #1 |
| `data/curated/ethnic_adjectives_da.csv` | edited on `main` (`f10dd85`, `36b65f1` "crossborder buckets") — differs |
| `data/curated/nation_umbrellas_da.csv` | edited on `main` — differs |
| `data/normalized/work_languages.csv` | differs — `lingua` version drift, exactly as PR #1's docs predicted |

Nothing else on the cleaning side diverged; `entities.csv`, `references.csv`,
`diary.csv` and `person_ethnic_descriptors.csv` are byte-identical between
A's `main` and PR #1. Resolve these four before importing anything, or the
migration silently reverts a week of nationality-vocabulary work.

Then, in order — each step ends with the site rebuilding to byte-identical
output, so any step can be the last one:

1. **Seed B.** Import PR #1's tree into `hca-open-repo-redesign` with the four
   drift items applied. Keep the commit history from the branch if possible;
   otherwise record the source commit (`6a12052`) in the seed commit message.
2. **Freeze the reference.** Build A at `main` with `PYTHONHASHSEED=0`; store
   hashes of all 4,544 HTML pages, 8 `*.js` and 7 `*.json` artifacts. This is
   the equivalence baseline for every later step.
3. **Prove the interface.** `publish.py --check --into ../hca-open-repo`
   reports zero drift; build A from B's published package; compare to step 2.
   Expect byte-identical except `manifest.json`'s timestamp and the
   `source_xlsx` provenance fix.
4. **Land the A-side commit.** Merge A's `claude/hca-preprocessing-separation-iobj59`
   (rebased on current `main`) so A stops carrying preprocessing. Resolve the
   known three-file overlap with `claude/ui-declutter-fixes`, already
   auto-merge-clean per that branch's handover. Re-verify against step 2.
5. **Rewrite the documentation.** One accurate conceptual pipeline document in
   B; archive `october-pipeline.md` and `docs/pipeline/stages.md` under
   `docs/history/` rather than deleting them. Brief §15.
5b. **Ingest V0.94 read-only and publish a structural diff.** Before any stage
    depends on it, write `scripts/normalization/hca_v094_to_csv.py` to emit
    into a parallel `data/normalized_v094/`, and a report covering: row counts
    per registry against A; `OLDWorkID` / `OLDLocationID` crosswalk coverage;
    `FK…` list expansion against `references.csv`; fill rates per column; and
    the controlled vocabularies in `1-SITES.xlsx` against the values actually
    present. This is the same discipline `data/normalized_v092/` already
    follows — ingest, verify, do not consume — and it is what makes step 11
    a decision rather than a leap. It is cheap and it can run in parallel with
    steps 6–9.

6. **Build the validation harness** (§J) *before* touching the cleaning chain.
   This is the order that matters most: the segmentation consolidation is the
   riskiest step in the plan and must not be the first one that cannot be
   checked.
7. **Consolidate enrichment.** Unify the duplicated language detection (E.5),
   name normalisation (E.6) and country precedence (E.4). Rehome the
   `parse_person_*` facet scripts into `enrichment/`. Add the two hand-run
   stages (`build_kb_links`, `reconcile_steder_categories`) to the runner.
   Re-verify.
8. **Split `data/curated/`** into live authority tables and `data/review/`
   audit artefacts. Update `publish.py`'s `INTERFACE`. Re-verify.
9. **Consolidate the segmentation chain** (E.2). Extract the approved
   decisions from the ~39 applied passes into a decision table; write one
   replayable stage; prove it reproduces the committed
   `personregister_xi_parsed.tsv` **exactly** from the parser output. Move
   the ~39 scripts to `scripts/segmentation/archive/`. Do not delete them.
10. **Adopt the segmentation output for persons — additively** (E.3, E.3a).
    The destination is unchanged: it becomes the person source. The *route*
    changed after E.3a. **V0.82 stays the person spine, and its `Reg…` ids
    stay the site's identifiers, until the crosswalk has been built and
    validated.** Each sub-step is independently reversible, and the first
    three change nothing a user sees.

    Gate on 10a: **if crosswalk coverage is poor, stop after 10b.** The
    enrichment in 10c is worth having on its own, and nothing later depends on
    completing the cutover. Run it as five sub-steps, in this order:

    **10a — Build the `PerXI… ↔ Reg…` crosswalk.** The segmentation output
    carries no workbook identifier, so the bridge must be derived. Use the
    method already proven in §J.3: normalise the name (NFKD strip, remove all
    year parentheses, fold punctuation), then confirm each candidate pair by
    matching the full `(vol, page)` reference signature on both sides. Emit
    `data/curated/person_id_crosswalk.csv` with a confidence column, and a
    review file for everything that does not match cleanly. **This artefact is
    the deliverable of the step** — everything below depends on it, and it is
    what makes the change reversible.

    **10b — Clean the parsed references.** Validate every `(vol, page)` in
    `11_references_parsed` against the diary page list — V0.94's 4,413-row
    `3-DIARY-PAGES` now covers all ten volumes, so this check is finally
    possible end to end. `('I', '1841')` is a known failure; assume it is not
    alone. Pages that do not exist are parse errors, not new findings.

    **10c — Merge the extra references, additively.** This is where the value
    lands, and it does not require the cutover. For every person the crosswalk
    resolves, fold the segmentation's `(vol, page)` pairs into
    `references.csv` as *additional* rows, and its `12_see_also` edges (444)
    into the person cards. V0.82 remains the spine; the segmentation
    supplements it. Expect roughly the 39,361 → 45,293 difference, minus
    whatever 10b rejects and whatever falls outside the crosswalk. Persons
    gain references; none lose any. **Reversible by dropping the added rows.**

    **10d — Decide the public identifier, then swap the spine.** Only now is
    the register itself replaced. The site's person URLs are
    `persons.html?reg=Reg…` (`personHref()` in `mockup/js/entity-refs.js`).
    Two options: keep `Reg…` as the public id and carry `PerXI…` internally —
    existing links and citations keep working, at the cost of a permanent
    indirection; or move to `PerXI…` and break every existing person link.
    **Recommend the first.** The register is a citable scholarly resource and
    the project's own README already publishes a version URL; breaking person
    links to tidy an internal id space is a bad trade. Entries with no `Reg…`
    counterpart get a new id in a documented, non-colliding range. Re-key
    `person_entity_types.tsv` (the gate that keeps families, firms and the
    register's dog out of the person facets), `breve_person_crosswalk.csv`,
    and the gender / role / ethnic-descriptor outputs through 10a's crosswalk,
    reporting anything that fails to map.

    **10e — Rebuild and compare on substance, not bytes.** `persons-extra.js`,
    `search-index.js`, `cooccurrence.js` and the 4,544 diary pages all change,
    by design. §J.6 defines what "correct" means here.
11. **Adopt V0.94 per entity type.** Make the source a per-entity parameter
    (§H). Land the four unambiguous wins first — KB links, place country and
    category, artist/museum/city, date precision — each replacing a B stage
    or an A regex, each verified against the step-2 baseline. Then the works
    register, using the 3,590/3,590 `OLDWorkID` crosswalk. Leave persons,
    diary text and `references.seq` on V0.82. Document what each future
    release would have to contain to take over the remaining slots.
12. **Only then, removals** (§K), and only for things step 2's baseline has
    proven unnecessary.

Steps 1–5 are the migration. Steps 6–9 are the simplification. Steps 10–12 are
decisions and cleanup that can wait.

---

## J. Validation strategy

The migration cannot rest on visual inspection, and today the repository gives
it nothing else: 19 tests, none comparing output to input, and a coverage
measurement that was never written down as code.

### J.1 — Byte-equivalence harness (steps 2–3, then every step)

`scripts/validation/compare_build_output.py`: build A from A's own pipeline
and from B's published package with `PYTHONHASHSEED=0`, then compare all
4,544 HTML pages and 15 data artifacts by SHA-256. PR #1 did this by hand;
it becomes a script so every later step can repeat it in one command.

Expected non-identical: `web/data/manifest.json` (timestamp; `source_xlsx`
provenance fix). Anything else is a finding.

### J.2 — Data-level comparison

Per brief §12, for each of `entities.csv`, `references.csv`, `diary.csv` and
each enrichment layer:

| Check | Method |
|---|---|
| record counts | per file, per `entity_type`, per H1/H2 category |
| identifiers | set difference on `entity_id`; no id may appear or vanish |
| fields | column set and order; no silent addition or reordering |
| values | cell-level diff on a stable sort, classified (below) |
| joins | every `references.entity_id` resolves; every `page_id` resolves; orphan counts per side |
| relationships | `see` / `see_also` targets resolve — already implemented as `check_indexes.py` |
| dates | parse rate; `YYYY-MM-XX` fallback rate; no date moves volume |
| sorting | row order preserved, or the sequence column restores it (a cross-cutting constraint) |
| links | KB permalinks and external authority links resolve in shape |
| missing values | null rate per column, per entry kind — a redirect stub and an ordinary entry have opposite requirements |
| duplicates | groups sharing (surname, full page-reference signature) — **the check the segmentation record names as missing** |
| special characters | UTF-8 NFC round-trip; the æ/ø/å and diacritic set that `fix_diacritics_from_xlsx.py` was written for; the known C→G OCR class |
| generated indexes | `search-index.js` entry count (16,444) and key set |
| edge cases | the named cases in the segmentation record: Auchamp/Ohsson particle sorting, the dash-subentry parents, Drewsen Elisa, Puggaard C./G., Riegels H.C./H.G. |

### J.3 — Coverage against the independent transcription

`data/raw/Personer _ HCA_tsv.txt` is an independent, pre-segmented
transcription of the same register — 10,228 rows, 699 cross-references,
9,529 persons. The segmentation record measured against it and reached a net
surplus of ~10 entries, using a three-step method (NFKD diacritic strip,
remove **all** year parentheses, fold punctuation; set-difference on the
normalised core; confirm apparent surpluses by matching full `VOL:PAGE`
reference signatures across the two sides) that it states was never written
as a script.

**Write it as `scripts/validation/compare_to_reference.py`.** It is the single
most valuable missing artefact in the project: it is the only external check
on the register's completeness, it is the acceptance test for step 9's
consolidation, and it closes weakness #1 in the record ("dublet-jagten er
sandsynligvis ikke udtømt" — two duplicate classes were found reactively, a
third may exist). Extend it with the broader similarity scan that record
recommends.

### J.4 — Classification of differences

Every difference is labelled before the step is accepted:

| Class | Handling |
|---|---|
| identical / expected | recorded, no action |
| intentional improvement | named in the commit message with the reason — e.g. the `source_xlsx` provenance fix |
| formatting-only | proven formatting-only (line endings, float precision, `lingua` confidence drift) and recorded — **not** waved through as "just formatting" |
| unexplained | **blocks the step.** No step proceeds with an unexplained discrepancy outstanding. |

The `lingua` confidence drift in `work_languages.csv` is the current live
example: the *language assignments* are stable, the *confidence figures* move
by thousandths between library versions. Pin the version, or accept the file
as committed data and exclude it from byte comparison — decide and write it
down, rather than rediscovering it each run.

### J.6 — The person cutover, where byte-equality does not apply

Every other step in this plan is checked by proving the output did not change.
Step 10 is the exception: the whole point is that the person data gets better.
So it needs its own acceptance criteria, agreed **before** the step runs.

| Check | Criterion |
|---|---|
| Crosswalk coverage | Every one of the 9,652 standard entries either maps to a `Reg…` id or is listed, with a reason, in the review file. No silent drops. |
| Reference growth is explained | The jump from 39,361 to 45,293 person references must be attributable — sampled and classified as *new in the register*, *recovered by better segmentation*, or *parse error*. A number that cannot be explained is not an improvement. |
| Page validity | 100 % of `(vol, page)` pairs resolve against `3-DIARY-PAGES`. This is a hard gate, not a report. |
| No person loses references | For every crosswalked person, the new reference set is a **superset** of the old, or the difference is explained. A person who silently loses pages is a regression. |
| The 127 live-only pages | Each one either reappears or is explained. These are pages the current site shows and the segmentation does not. |
| Facet gates still hold | `person_entity_types.tsv` still excludes what it excluded; `test_persons_extra_gate.py` passes against the re-keyed data. |
| Counts are re-measured | Against the independent transcription (§J.3), not against the superseded figures in the segmentation record — the file has drifted from 10,136 to 10,079 rows since that record was written. |
| Links survive | Per 10d: a sample of existing `persons.html?reg=…` URLs still resolves. |

### J.5 — Tests that must exist afterwards

- segmentation reproduces `personregister_xi_parsed.tsv` exactly from parser
  output plus the decision table (step 9's acceptance test);
- no duplicate group by (surname, page-reference signature);
- index integrity has no *new* findings (`test_index_integrity.py`, adopted
  from PR #1, holds the line rather than demanding zero);
- the published interface is complete — every file in `INTERFACE` exists and
  is non-empty;
- `test_row_count_in_expected_range` keeps its deliberately loose bound
  (`9000 ≤ n ≤ 10800`) and is not tightened without re-measuring against §J.3.

---

## K. Proposed removals

**Nothing is deleted in this phase.** This is the candidate list for after
step 12, with the evidence each one needs.

### Safe once B holds the sources (evidence: PR #1 already proved this)

| Item | Evidence |
|---|---|
| `hca-open-repo/data/raw/**` | The build was run with `data/raw/` moved aside and produced byte-identical output. |
| `hca-open-repo/raw/**` | Same. Already removed on `claude/roadmap-preprocessing-handover-7me9kj` (`8d5e281`). |
| `hca-open-repo/scripts/{normalization,parsers,place_typology,correspondence,migration}/` | Moving to B. |
| 56 cleaning-only data files under `hca-open-repo/data/` | Enumerated in `10d059f`. |
| `openpyxl`, `lingua` from A's CI | A's build becomes stdlib-only. |

### Requires a decision, not just evidence

| Item | Decision needed |
|---|---|
| ~~`data/parsed/personregister_xi_parsed.tsv`~~ | **Resolved — it becomes the person source** (§E.3, §I.10). Not a removal candidate at all; it moves into the published interface. What *does* become a removal candidate, after step 10 validates, is V0.82's person half of `entities.csv` — demoted to crosswalk and fallback, not deleted. |
| `data/normalized_v092/{entities,diary,references}.csv` | Produced, never consumed. **Keep as a verification surface — they will not become primary.** §E.3a: the person slice covers volumes VI–VII only. V0.94 supersedes the place and page slices. |
| `scripts/build_mockup/build_cooccurrence.py` | Deleted at the V0.92 cutover, replaced by reading `FactDiaLocPerPag`. Not before. |
| `hca-open-repo/web/**` and `build_web_data.py` | The October Places demo, superseded by `mockup/`. Retiring it is A's call; note that `manifest.json` is currently the only consumer of the provenance file. |
| `scripts/parsers/ner_page_grounding.py` + its 1 MB output | Committed, read by no build stage. Establish whether it is dormant or abandoned. |
| `scripts/enrichment/build_kb_links.py` + `1-KBDiaryLinkData-PQ-links-active.xlsm` | **Superseded by V0.94's `KBLinkString`** (4,413/4,413). Remove once step 11 lands and the permalinks are verified equal. |
| `scripts/enrichment/reconcile_steder_categories.py` + `Steder_i_dagboegerne_verificeret VER 1.0.xlsx` | **Superseded by V0.94's `Country` / `Category`** (2,430 / 2,429 of 2,433). Same condition. |
| the bounding-box gazetteer inlined in `build_web_data.py` | Superseded by the same columns (E.4). Retire with the `web/` demo or sooner. |
| the title-parenthesis artist regex behind `billedkunst-artist-extraction.md` | **Superseded by V0.94's `Artist` / `MuseumEtc` / `City`.** Verify the 2,113 filled rows cover the 355 artists the regex finds before removing it. |

### Archive, do not delete

| Item | Why keep |
|---|---|
| the ~39 applied cleaning scripts | The audit trail for roughly 1,700 editorial decisions on scholarly data. Move to `scripts/segmentation/archive/` with a README stating they are applied history. |
| `data/curated/*_review.tsv`, the manual-correction workbooks | The record of what a human approved. Move to `data/review/`. |
| `raw/DiaryVol6–10.docx`, `DiaryVol6/7 V0.8.xlsx`, the OCR PDFs | No script reads them and their purpose is not established — which is a reason to ask, not a reason to delete. Quarantine under `data/raw/legacy/` with a note. |
| `docs/data-model/october-pipeline.md`, `docs/pipeline/stages.md` | Superseded, but they record why the architecture is what it is. `docs/history/`. |
| `scripts/migration/migrate_tidstavle_*.py` | One-shot, done, output committed. Keep out of the runner. |

### Open questions for the spreadsheet side

Not removals, but they gate §H and belong with the same people. Revised after
V0.94 — the first is answered, the rest are sharper or new.

1. ~~**When does `WorkData-PQ` ship?**~~ **Answered.** V0.94's
   `5-WORK-Registry.xlsx` is it: 3,590 rows, H1–H4 columns, and a work
   crosswalk that resolves completely into the live data.
2. **Where did the person register go, and when does it come back?** This is
   now *the* blocking dependency. V0.92 shipped 8,917 persons; V0.94 ships
   none, while its own `Vejledning` sheet cites 9,520. Persons are the
   largest entity on the site (10,228) and the subject of the project's
   biggest editorial effort. Until a person workbook exists, V0.82 cannot be
   retired.
3. **Was withdrawing the star schema deliberate?** V0.92's `FactDiaPerPag`,
   `FactDiaLocPag` and `FactDiaLocPerPag` (92,307 rows) are absent from V0.94,
   replaced by space-separated key lists inside dimension rows. If the
   PowerPivot model still exists behind the scenes, exporting the bridge
   tables as three CSVs would be the single most useful thing the spreadsheet
   side could add — it restores §E.1 and removes list-splitting from B.
4. **Can `OLDLocationID` carry the live `Reg…` ids?** `OLDWorkID` does, and it
   resolves 3,590/3,590. `OLDLocationID` carries V0.92's `LOC…` scheme instead
   and resolves 0/2,433, so places cannot be cut over without a separately
   built crosswalk. Fixing it upstream costs one column; fixing it downstream
   costs a fuzzy name-match pass and its error rate.
5. **Will `Latitude` / `Longitude` be populated?** The columns exist on all
   2,433 places and are 100 % empty. If they are going to be filled, B should
   not invest further in reconciling Rejser and SV14 coordinates; if they are
   not, they should be dropped so they stop reading as available data.
6. **Will `See` / `See also` be populated?** Same pattern: provisioned on all
   3,590 works, 0 % filled. This supersedes the old `Raw.See-Also` question —
   the format is now settled, only the content is missing. Is a person-side
   equivalent planned?
7. **Do the PowerQuery steps live anywhere outside the workbooks?** If the M
   code is only inside the `.xlsx` files, the upstream half of the pipeline
   has no version history and no review surface. Exporting the queries to
   `.pq` text files in B would put the whole pipeline under git — a cheap,
   high-value provenance win, and still the one piece of §F's recommendation
   B can deliver without waiting for anyone.
