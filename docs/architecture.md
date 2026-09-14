# Architecture

What this repository is for, how data moves through it, and where the
boundaries are. This is the conceptual document: it describes the *shape* of
the pipeline and the reasoning behind it. For the current stage list, run
`python scripts/run_pipeline.py --list` — that is generated from the code and
cannot drift. For the file-level contract with the publication repository, see
[`interface.md`](interface.md).

Three earlier pipeline documents described three different architectures, none
of them the one that ran. They are kept in [`history/`](history/) with an
account of how that happened.

---

## 1. The one-sentence version

Printed nineteenth-century registers become clean, joinable, well-identified
data here; a separate repository turns that data into a website.

```
   printed registers, OCR,          this repository            hca-open-repo
   spreadsheets, TEI, scraped   →   clean · segment ·      →   build HTML,
   tables                           enrich · validate          JS cards, JSON
                                          ↓
                                   23 published files
```

The rule that decides what belongs where, and the only one you need to
remember:

> **A stage belongs here if it derives a fact about the data. It belongs in
> the publication repository if it shapes prepared data into something a
> browser displays.**

A coordinate, a language, a nationality, a segmentation, a category, a
permalink — those are facts, and they are derived once, here. An HTML page, a
denormalised JS card, a search index, a co-occurrence count — those serve a
particular view, would have to be recomputed for any new view, and stay there.

---

## 2. Where the data comes from

Everything originates in `data/raw/`, and nothing in this repository writes
there. Four kinds of source:

**The register workbooks.** Maintained in Excel by the project's
collaborators, delivered as versioned releases. Three generations coexist, and
**no single one covers everything** — which is why ingest is parameterised per
entity type rather than by a global version switch:

| Release | Shape | Authoritative for |
|---|---|---|
| `HCA REPOSITORY V0.82` | one flat workbook, one `Registry` sheet with H1–H4 classification columns | the live site today: persons, diary text, references with ordering |
| `HCA REPOSITORY V0.92` | nine workbooks — PowerQuery extracts plus PowerPivot star schemas | nothing in production. Its person slice covers volumes VI–VII only. Kept as a verification surface |
| `HCA REPOSITORY V0.94` | five renamed, numbered registries plus a specification workbook | works, places, the ten-volume page list, the calendar. **Has no person register.** Ingested read-only by stage `1a''`; nothing consumes it |

**Persons are the exception to all of this.** No workbook is their
destination: V0.94 has no person register at all, and V0.92's covers two
volumes out of ten. The person register's future source is this repository's
own segmentation output, `data/parsed/personregister_xi_parsed.tsv` — richer
than what the site shows (45,293 page references against 39,361) and measured
against the independent transcription by
`scripts/validation/compare_to_reference.py`. V0.82 remains the spine until
the `PerXI… ↔ Reg…` crosswalk is built and validated. See
[`migration-plan.md`](migration-plan.md) §E.3 and §E.3a.

**Independent transcriptions and scans.** `Personer _ HCA_tsv.txt` is a
separately produced, pre-segmented transcription of the person register —
10,228 rows. It is not a source the pipeline reads; it is the **external check
on completeness**, and the only one that exists. The OCR PDFs behind register
XI are the raw material the segmentation works from.

**Geographic sources.** `Rejser_HCA_X.htm`, scraped from rejser.hcax.dk,
carries coordinates for 377 places. `SV14_places.xml` is a TEI place-list
covering some of the rest. Together they are the only source of coordinates —
V0.94 provisions `Latitude`/`Longitude` columns but leaves them empty.

**Human-verified overlays.** The KB link workbook and the verified-places
workbook are maintained by hand, in Excel, by the people who do the verifying.
That is where they should stay.

### What is authoritative

For any given field, the authoritative source is the one a human maintains
deliberately — not the newest file, and not the one easiest to parse. Where
V0.94 carries a curated column (place country and category, a work's artist
and museum, a page's KB permalink), it wins over anything this repository
derives by rule. Where it leaves a column empty, the derivation stands.

#### A place's country: four sources, one order

Country is the field most often derived twice, so its precedence is written
down rather than left to whichever stage runs last:

| Rank | Source | Kind |
|---|---|---|
| 1 | `4-LOCATION-Registry.xlsx` `Country` (V0.94) | curated by the people who verify it — ingested to `normalized_v094/`, **not yet consumed** |
| 2 | `data/normalized/steder_verified_categories.csv` | human-verified, from the verified-places workbook. **Authoritative today.** |
| 3 | `data/curated/steder_country_to_nation_da.csv` | a country → nation-bucket mapping, not a country source; applied *after* a country is known |
| 4 | the bounding-box gazetteer inlined in `build_web_data.py` | 33 European boxes over a coordinate, in the publication repo. A last resort, and the only one that can be wrong about a place it has never seen. |

Rank 4 lives in the publication repository and covers only the geocoded
subset. It is the one to retire first when V0.94's places are adopted, since
ranks 1 and 2 cover every place rather than the 377 with coordinates.

Note that `Country` in V0.94 uses a bare `0` as a "no value" placeholder in a
few cells — it is not an empty string, and a naive fill count reads it as
data. The ingester counts placeholders separately for this reason.

---

## 3. What happens here

Five stages, each a boundary that earns its place. Two of them are not
transformations at all, which is deliberate.

### Ingest
Workbook or source file → the star-shaped core: `entities.csv`, `diary.csv`,
`references.csv`. One row per register entry, one per diary page, one per
mention of an entity on a page. Everything downstream joins on these.

### Segment
The printed person register, via OCR, into one row per person — name, given
names, life dates, description, and its own page references. This is the
hardest and most valuable work in the project, and it is **not automated**:
see §5.

### Enrich
Passes that add a derived fact to the core without changing it: coordinates
reconciled from two geographic sources, probable language per work title,
gender and role and ethnic descriptors parsed from free-text descriptions,
KB permalinks, verified place categories. Each writes its own file. Each
degrades gracefully — a missing enrichment empties a facet, it does not break
a build.

### Validate
Transforms nothing. `scripts/validation/check_indexes.py` reports
cross-references that lead nowhere and fields that are empty when their kind
of row requires them — per index and per entry kind, because a redirect stub
and an ordinary entry have opposite requirements.
`scripts/validation/compare_build_output.py` proves that a change here did not
change what the site displays. See [`index-integrity.md`](index-integrity.md)
and [`equivalence-2026-09-12.md`](equivalence-2026-09-12.md).

### Publish
`scripts/publish.py` copies an explicit, hard-coded list of 23 files into a
publication-repo checkout, and writes `_source.json` alongside recording which
raw sources — by name and SHA-256 — the package descends from. `--check`
reports drift without changing anything.

The interface is a **list, not a folder**. Adding a file to `data/` does not
publish it; adding it to `INTERFACE` does. That is what keeps the boundary
honest.

---

## 4. What is generated, and what must never be edited

| Path | Status |
|---|---|
| `data/raw/**` | **Source.** Never edited here, by hand or by script. |
| `data/normalized/**` | **Generated** by the runner from `data/raw/`. Committed, because consumers need them without re-running. Do not hand-edit — the next run overwrites you. |
| `data/parsed/**` | **Generated once, then hand-corrected over many reviewed passes.** Re-running a parser discards that work. See §5. |
| `data/curated/**` | **Hand-maintained — 11 authority tables.** The nationality list, gender markers and given-name overrides, nation umbrellas, the entity-type gate, role terms, person emendations, Wikidata ids. Edit these deliberately; they are inputs. |
| `data/review/**` | **Generated — 39 artefacts.** Suggestion files a human approved, Collin-letter indexes and matches, integrity findings, reference-comparison reports. A person reads them and acts; the pipeline never reads them back. |
| `data/normalized_v092/**`, `data/normalized_v094/**` | **Generated verification surfaces.** Ingested so a source generation can be argued about with numbers. Nothing consumes them. |
| `dist/` | **Generated** by `publish.py`. Gitignored. |

Two exceptions worth knowing, because both have bitten:

**`data/normalized/work_languages.csv` is committed data, not reproducible
output.** Regenerating it with a different `lingua` version changes which rows
it contains — 16 ids moved each way between the two versions measured — as
well as the method labels and confidence figures. The language assignments
themselves are stable, and the language is what the facet displays. Regenerate
only in a pinned environment, and never as a side effect of establishing a
baseline.

**`data/parsed/personregister_xi_parsed.tsv` is the product of roughly 1,700
reviewed editorial decisions** applied by a long chain of one-shot scripts. It
cannot be regenerated from the parser alone.

---

## 5. Why the cleaning chain is not in the runner

`scripts/parsers/` holds two different kinds of thing, and conflating them
would destroy work.

**Register parsers** read a slice of a source and emit structured rows. They
are re-runnable.

**The cleaning chain** — the `suggest_*` / `apply_*` / `split_*` / `merge_*` /
`dedupe_*` / `refine_*` passes — is the record of a human review. Each
`suggest_*` wrote a review file, a person approved it, and the paired
`apply_*` edited the parsed register in place. They are one-shot, already
applied, and order-dependent. Running a parser again discards every one of
them.

So they are kept for audit, not for execution, and `run_pipeline.py`
deliberately does not call them. The order they were applied in, the
measurement method used to check coverage, and the known weaknesses are
recorded in [`person-register-segmentation.md`](person-register-segmentation.md).

This is honest but not good. The information worth keeping is the *approved
decisions*, not the code that applied them — a decision table and one
replayable stage would make the chain testable and reproducible. That is a
planned change, not the current state; see
[`migration-plan.md`](migration-plan.md) §E.2.

---

## 6. How the website consumes this

The publication repository reads the 23 published files and nothing else. Its
build turns them into 4,544 diary HTML pages, nine JS data cards, and seven
JSON view shapes. It re-derives nothing.

This was verified rather than assumed: with the prepared data **deleted** from
a publication-repo checkout and replaced by `publish.py --into`, the build
produced 4,559 of 4,560 artifacts byte-identical to one built from its own
committed data. The single difference was a build timestamp.
[`equivalence-2026-09-12.md`](equivalence-2026-09-12.md) has the method.

---

## 7. Reproducing and testing

```bash
python -m pip install -r requirements.txt

python scripts/run_pipeline.py --list      # what the stages are
python scripts/run_pipeline.py             # regenerate data/normalized/

python scripts/validation/check_indexes.py # register integrity
python -m pytest tests/ -q                 # 53 tests

python scripts/publish.py --check --into ../hca-open-repo   # drift, no writes
python scripts/publish.py --into ../hca-open-repo           # publish
```

To prove a change did not alter the site, snapshot a publication-repo build
before and after and compare:

```bash
python scripts/validation/compare_build_output.py snapshot ../hca-open-repo before.json
python scripts/validation/compare_build_output.py compare before.json after.json
```

**Three environment rules, each learned by being bitten:**

- **`PYTHONHASHSEED=0`** when producing a comparable build. Several builders
  iterate over sets whose order reaches the output.
- **`PYTHONIOENCODING=utf-8` on Windows.** Seven scripts printed `→`, `⚠`,
  `✓` or `≥`, which the cp1252 console default cannot encode, and died at the
  print *after* doing their work. One of them was stage 1a, so the pipeline
  could not complete at all; two sat on optional stages and so failed
  silently, reporting success while their artefact was absent. Every script
  here now reconfigures stdout itself, and any new one must — a
  `print` is not a safe place to put a non-ASCII character on this platform.
- **Never run the ingest stages to establish a baseline.** They regenerate
  `data/normalized/`, including the non-reproducible file in §4.

A third rule applies to anything that writes a committed file: **sort before
taking "the first" of a set or an unordered list.** `check_indexes.py` chose
among equally-scoring suggestions by set-iteration order, so its committed
findings file changed between interpreter runs. A validation tool that is not
reproducible is worse than an ordinary one: it is the thing other checks are
measured against.

---

## 8. Constraints that hold everywhere

Carried from the printed-register work, and binding on any new stage:

- **UTF-8 throughout**, no BOM.
- **Original order is reconstructable.** Printed-index ordering carries
  editorial meaning; stages preserve row order or carry a sequence column.
- **Original data is never lost, only supplemented.** Cleaning adds columns;
  it does not overwrite the source. Every transformation must be reversible to
  the raw entry it came from.
- **Transformations are traceable.** Each parsed row keeps its provenance
  pointer.
- **Ambiguity is escalated, not guessed.** A parenthetical or relation marker
  with more than one plausible reading goes to a review file, not to a silent
  resolution.
- **Identifiers are stable and carried, never derived from content.** A
  content-derived id changes when a typo is fixed, which breaks every citation
  to it. This is a live constraint, not a hypothetical: V0.94's place ids are
  content-derived and consequently do not reach the live register's ids at
  all, while its work ids are carried and match completely.

---

## 9. Where to read next

| Question | Document |
|---|---|
| What has actually been built, and what did implementing it turn up? | [`migration-plan.md`](migration-plan.md) — the Status section at the top |
| What exactly crosses to the publication repo? | [`interface.md`](interface.md) |
| What do the stages do, in order? | [`pipeline.md`](pipeline.md) |
| What does the integrity checker enforce? | [`index-integrity.md`](index-integrity.md) |
| How was the person register segmented, and how good is it? | [`person-register-segmentation.md`](person-register-segmentation.md) |
| What is wrong with the person-index input, and how was it checked? | [`person-index-data-quality.md`](person-index-data-quality.md) |
| Why is the architecture shaped this way, and what changes next? | [`migration-plan.md`](migration-plan.md) |
| How was equivalence proven? | [`equivalence-2026-09-12.md`](equivalence-2026-09-12.md) |
| What did the old documents claim? | [`history/`](history/) |
