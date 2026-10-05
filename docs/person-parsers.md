# Person parsers — how the logic works

How this repository turns the printed *Personregister* and the V0.82 workbook
into the person data the site shows. It describes the rules **as the code
implements them**, and points to the script that owns each one. For the
history of how the register was cleaned, read
[`person-register-segmentation.md`](person-register-segmentation.md); for the
repository's overall shape, [`architecture.md`](architecture.md).

## Contents

1. [Two populations, three id spaces](#1-two-populations-three-id-spaces)
2. [The flow at a glance](#2-the-flow-at-a-glance)
3. [Stage 1 — OCR → one row per entry](#3-stage-1--ocr--one-row-per-entry)
4. [Stage 2 — the cleaning chain (archived)](#4-stage-2--the-cleaning-chain-archived)
5. [Stage 3 — detecting fused and duplicated rows](#5-stage-3--detecting-fused-and-duplicated-rows)
6. [Stage 4 — emendations](#6-stage-4--emendations)
7. [Stage 5 — identity: minting and crosswalk](#7-stage-5--identity-minting-and-crosswalk)
8. [Stage 6 — merging page references](#8-stage-6--merging-page-references)
9. [Validation](#9-validation)
10. [Enrichment parsers over the live persons](#10-enrichment-parsers-over-the-live-persons)
11. [Principles the parsers share](#11-principles-the-parsers-share)
12. [Sharp edges](#12-sharp-edges)
13. [File map](#13-file-map)

---

## 1. Two populations, three id spaces

"Person" means two different datasets here, and most confusion comes from
mixing them up.

| | **Live set** | **Segmented register** |
|---|---|---|
| Source | V0.82 workbook, sheet `Registry`, category `PERSON-REGISTER` | OCR of the printed *Personregister* (volume XI) |
| File | `data/normalized/entities.csv` (+ `references.csv`) | `data/parsed/personregister_xi_parsed.tsv` |
| Size | 10,228 persons | 10,079 rows: 9,652 `standardpost`, 410 `krydshenvisning`, 17 `underpost` |
| Identifier | `Reg0030070` — **cited by site URLs** | `HCAP00001` (stable) and `PerXI00001` (a row number) |
| Role | What the site shows today | The better data (≈15 % more page references), adopted **additively** |

Three identifiers, with different guarantees:

| Id | Assigned | Stable? | Use it for |
|---|---|---|---|
| `Reg…` | by the V0.82 workbook | yes — URLs depend on it | everything the site shows |
| `HCAP…` (`00_person_id`) | once, by `mint_person_ids.py`; **never re-derived** | yes | citing a register row; the crosswalk key |
| `PerXI…` (`01_entry_id`) | positionally, at parse time | **no — it renumbers on every insert** | nothing outside one working session |

`PerXI00001` is "Åberg" in a fresh parse and "Abbott" in the committed file.
Anything that cites a `PerXI…` id is citing a row position.

## 2. The flow at a glance

```
OCR PDF ──► parse_personregister_xi.py ──► parsed.tsv ──► [cleaning chain, archived]
                                                              │ (human-reviewed, not replayable)
                                                              ▼
                                             data/parsed/personregister_xi_parsed.tsv   ← the master
                                                              │
        ┌─────────────────────────┬───────────────────────────┼──────────────────────────┐
        ▼                         ▼                           ▼                          ▼
 suggest_row_corrections   apply_person_emendations   mint_person_ids → HCAP…    (read by tests)
 → annotate → add_warnings → resolved view (corrections        │
   (findings, never edits)    laid OVER the master)             ▼
                                                      build_person_crosswalk ──► person_id_crosswalk.csv
                                                                │                    (HCAP ↔ Reg)
                                                                ▼
                                                      merge_person_references ──► references.csv (+ rows)

V0.82 workbook ──► entities.csv ──► parse_person_ethnic_descriptors ─┐
                                    parse_person_gender  ◄───────────┤  nationality feeds the name statistics
                                    parse_person_role (curation/)    │
                                                                     ▼
                                              data/normalized/person_{ethnic_descriptors,gender,role}.csv
```

Two properties hold everywhere in this chain:

- **Findings and corrections are separate from the data.** Detectors write
  review files; emendations are laid *over* the master at read time; nothing
  silently rewrites it.
- **Anything that can be added instead of changed, is.** The reference merge
  appends rows; enrichments write their own files.

---

## 3. Stage 1 — OCR → one row per entry

`scripts/segmentation/parse_personregister_xi.py`

Input: the "test ABBYY" OCR layer of the scan (`data/raw/dagbog-bd-11-3408_Claus-OCR test ABBYY.pdf`),
0-indexed PDF pages 47–444. The genealogy fold-outs and front matter are out of
scope. The ABBYY layer is the only OCR source because it was measurably better
on register digits ([`data/raw/ocr-comparison-dagboeger-XI.md`](../data/raw/ocr-comparison-dagboeger-XI.md)).

### 3.1 Layout → one text stream

`flow_page()` keeps text blocks whose y-range lies between the running head
(y ≤ 55) and the printed column numbers (y ≥ 483), reads the **left column top
to bottom, then the right**, deletes soft hyphens (`\xad`) *before* collapsing
line breaks so a wrapped word rejoins, and collapses all whitespace. Header and
footer are navigation aids for someone flipping the physical book, not content.

### 3.2 Splitting entries — closer followed by opener

Line-start heuristics do not work: a capitalised place or institution in the
middle of a description ("…i Justitsministeriet, 1855 Lektor…") triggers a naive
"Capitalised word + comma starts an entry" rule hundreds of times. So the split
is **punctuation-anchored**: a split point is the *end of something that closes
an entry* immediately followed by *something that opens one*.

```
SPLIT_RE = (CITE_END | SEE_END | ")." | "?.")  followed by  (NAME_HEAD | DASH_SUBENTRY_HEAD)
```

| Part | Matches | Notes |
|---|---|---|
| `CITE_END` | a roman volume + column numbers ending in a period (`IV 141 148. `) | requires a real roman numeral, so a mid-description "2. Bataillonslæge" never splits |
| `SEE_END` | a `se:` / `se ogsaa:` cross-reference clause ending at the first period **followed by whitespace** | colon optional, `ogsaa` fuzzy (`og[as]{2}a`) because the source prints it without a colon and the OCR mangles it; the target must start with a capital; an inner dot ("A.N.de Saint-Aubain.") does not end the clause; `\b` before `se` stops "Jose-phine" matching |
| `)." ` / `?."` | a closing year parenthesis, or an uncertain year | |
| `NAME_HEAD` | `Surname, Given` — including **particle surnames** (`auf der Maur`, `von Arnim`), which this register alphabetises on the particle | |
| `NAME_HEAD_NOCOMMA` | single-name figures with no comma: `Absalon (ca. 1128-1201)`, `Sigurd Jorsalfarer (1089/90-1130)`, `Bernhard af Clairvaux (1090-1153)`, `Agrippina d.Æ. (død 33)`, `Lennel [saaledes …]` | anchored on a bare capitalised word followed directly by a year-paren, a roman citation, or a `[`. **Deliberately not** `Name (Alias)` — that shape is overwhelmingly a mid-entry alias ("Bajazet (Bajazid) I"); allowing it split 25 entries mid-name |
| `DASH_SUBENTRY_HEAD` | `— Hans/Hendes/Deres …` | continues the previous entry's surname |

A lone alphabet divider ("A.", "Å.") is stripped only when it is the very first
thing in an already-split segment — never mid-text, where it is
indistinguishable from a person's own initial.

What this catches that a year-anchored rule would not: entries with **no year
at all** ("Amiot, Bordeaux 23.8.1866. VII 175.") are common in this register.

### 3.3 Parsing one entry

`parse_entry()` decides, in this order:

1. **Sub-entry** — leading dash. Surname is *inherited* from the last
   non-sub-entry; with no `se:` clause the whole text is description + citation.
2. **Cross-reference** — `SEE_RE` matches and there is no citation block →
   `krydshenvisning`, with the target in `12_see_also`. The name part may itself
   contain commas, so the regex is greedy up to the *last* `se:`.
3. **Standard entry** — surname/rest, then year, then references.

**Surname** ends at the first comma, or — for no-comma figures — at the year
parenthesis, whichever comes first.

**Years** (`YEAR_RE`) are searched in at most **260 characters** of lead-in after
the surname comma. Titles and noble styling can precede the year ("Ahlefeldt,
Charlotte Elisabeth Sophie Wilhelmine von, Grevinde, f. von Seebach (1781-1849)"),
but the longest genuine lead-in measured in the register is ~250 characters, so
an unbounded search would mistake a citation's own parenthesis for a life span.
Whatever lies between surname and the parenthesis becomes `04_given_names`.

| Printed | Result |
|---|---|
| `(1818-80)` | 1818 / 1880 — a death year shorter than the birth year is expanded from it (same rule as column ranges) |
| `(1818-?)` | birth only; `08_year_note` = "dødsår usikkert (?)" |
| `(død 1873)` / `(d. 1873)` | death only |
| `(1871)` | birth only, noted "enkeltårstal, usikkert om fødsel/død" |
| `(… f. Chr.)` | noted "f. Kr. (BC)" |
| no parenthesis | **given names stay empty** and the whole remainder is description — the lead-in is not reliably splittable without the year anchor |

**References** — the trailing run of volume markers is the citation block
(`REF_BLOCK_RE`); everything before it is description. `10_references_raw` keeps
it as printed; `11_references_parsed` expands it to atomic `VOL:COLUMN` pairs.
The expansion is not a naive range fill: in `398-99` the second number is the
**abbreviated final digits of the first** (398–399), and `106-07` is 106–107.
If abbreviating would produce a smaller number, the pair is kept as printed
rather than guessed. A stray space around the hyphen (`283- 85`) is a line-wrap
artefact, not two citations.

### 3.4 What it writes

`data/parsed/personregister_xi_parsed.tsv` — 13 columns:

```
01_entry_id  02_entry_type  03_surname  04_given_names  05_sort_key
06_birth_year  07_death_year  08_year_note  09_description
10_references_raw  11_references_parsed  12_see_also  13_raw_text
```

(`00_person_id` is prepended later, see §7.) `13_raw_text` keeps the segment as
split, so any later decision can be checked against what the parser saw.

`data/review/personregister_xi_review.tsv` lists rows with a **plausibility
problem** — checks that need no ground truth:

| Check | Why it works |
|---|---|
| no references and no `se:` target | nothing to cross-check |
| `se:` target is not a surname in the register | dangling cross-reference |
| a column number outside **1–796** | the register's printed range; catches a dropped space fusing two numbers (`V 2456`) |
| death year before birth year (not BC) | usually a 0/9 OCR confusion |
| a **falling column series within one volume** | the register prints columns in increasing order, so a drop is an OCR defect |

> ⚠ **Do not run this script casually.** `OUT_TSV` is the committed master. A
> fresh parse yields 9,338 rows against the committed 10,079 and **replaces**
> the reviewed file with something substantially worse. See §4.

---

## 4. Stage 2 — the cleaning chain (archived)

`scripts/segmentation/archive/` — 30 one-shot passes, applied in order during a
human-reviewed session. **They cannot be re-run**: each consumed a review file
from `data/review/` that later passes overwrote. What survives is the outcome
(the committed TSV) and the reasoning.

The passes fall into a few kinds, all of which the live detectors in §5 still
reason about:

| Kind | What it did |
|---|---|
| **Fusion splits** | A description that swallowed the next person (after a roman+arabic citation, or after a dash + surname initial) was split; 46 + 132 rows. A "Surname, Given (year)," buried mid-description was split out. |
| **Reference harvest** | `data/raw/Personer _ HCA_tsv.txt` is an independent person-per-row transcription (10,228 rows). 70 fused rows → 82 new entries; 958 people missing here were imported. |
| **De-duplication** | The import matched on name text, so entries with empty or differently spelled given names were imported as "new": 393 duplicate groups, 453 rows removed (key: full page-reference signature + year), then 26 more where only one side had references or the surname differed by a leading particle (`d'Auchamp`/`Auchamp`). **Our spelling wins on conflict** — the reference has a systematic C→G OCR error (`Cornelis`→`Gornelis`). |
| **Dash sub-entries** | "— Hans Datter" lost its parent when sorted alphabetically; 13 re-linked via the reference's preserved print order. |
| **Field re-segmentation** | ≈ 900 descriptions still holding a name or life span: pattern A (description opens with its own life-span parenthesis), B (opens with given names + life span), G (life span duplicated inside `04_given_names`). **Deliberately not touched:** meeting years (`Amerikansk Beundrer (1871)`), bare titles (`Tysk-romersk Kejser` must not become a given name), sibling groups with several life spans. |

`data/review/personregister_xi_review_full.tsv` is the master plus a
`review_flags` column. The flag vocabulary and current counts:

| Flag | Rows | Meaning |
|---|---:|---|
| `no_refs_no_see` | 179 | nothing to cross-check |
| `hyphen_linewrap:verify_do_not_join` | 99 | a hyphen at a line end — **never auto-join**, it may be a real hyphen |
| `fused_entry:description_reference_run` | 61 | a citation run + name-head inside the description |
| `suspect_years:year_left_in_name` | 29 | a life span stranded in the name field |
| `fused_entry:embedded_name_year` | 24 | a whole "Surname, Given (year)," inside a description |
| `fused_entry:reference_run` | 16 | the same inside `04_given_names` |
| `paren_unbalanced` | 12 | |
| `death_before_birth` | 5 | |

Guarded by `tests/test_personregister_xi_parsed.py` (deliberately loose row-count
bounds — they catch a *change of shape*, not drift).

---

## 5. Stage 3 — detecting fused and duplicated rows

These are the **live** descendants of the archived passes: they find the same
defects, but only *propose*.

### 5.1 `suggest_row_corrections.py`

Two opposite defects in one pass, because they are the same mistake in either
direction: a row that should be two, and two rows that should be one.

**Split side** — a citation run sits where one cannot belong (`09_description`,
or `04_given_names`) and the next entry's name-head hangs on after it.

| Tier | Action | Why it is safe or not |
|---|---|---|
| **1** | *recover citations* into a **new** column `14_recovered_references` | additive and mechanical — a citation inside a description is in the wrong column by definition; never written over `11_references_parsed`; a page the row already carries is not a recovery |
| **2** | *trim the column* back to before the hanging name-head | independently checkable against `13_raw_text` |
| **3** | *split out a new row* | only if the hanging surname is **not already a row** — of 61 description fusions, **48 tails already exist**; splitting those would manufacture duplicates, which is worse than the fusion |
| **4** | *review by hand* | `embedded_name_year`: a second person is buried in a description |

The tail is accepted as a name only if it survives `tail_head()`: skip an
alphabet divider; refuse a genitive (`Amé's Far` is a relation); refuse a bare
initial.

**Merge side — reported, never applied** (removing a row renumbers
`01_entry_id` and rewrites citations; it is the most destructive edit here).

| Kind | Rule |
|---|---|
| `exact_duplicate` | identical surname, given names, both years, description and references |
| `cross_reference_twin` | same `se:` target **and** same page set **and** descriptions ≥ 0.55 similar (`difflib`). This is what a *manual split* produces — someone writes a hanging tail out as a row without noticing the register had it under a dash |
| `ocr_twin` | ≥ 2 shared pages, surnames ≥ 0.80 similar, and the pair becomes equal under a **known scanner confusion** (`rn↔m`, `ii↔ü`, `c↔e`, `c↔g`, `l↔i`, `i↔t`, `s↔5`, …) |
| `similar_names` | same, but *not* an OCR confusion → "probably not a merge" |

A single shared page is coincidence; ≥ 2 is the threshold.

`--write` produces `data/review/row_corrections_review.csv` (every finding,
with tier and evidence) and `data/parsed/personregister_xi_parsed.proposed.tsv`
(the master with tiers 1–2 applied, to **diff** against the real one).

### 5.2 Putting findings next to the rows

| Script | Adds |
|---|---|
| `annotate_register_with_recommendations.py` | columns 15–23 (`15_fix_kind` … `23_evidence`): what each finding *means for this row*. Columns 1–14 are copied through untouched. |
| `add_warnings_and_actions.py` | columns 24–26: `24_action`, `25_warnings`, `26_warning_detail` |

`add_warnings_and_actions.py` also merges two duplicate detectors that barely
overlap (73 pairs and 23 pairs, 1 in common — one needs the surname to match
exactly, the other needs two shared pages) into `merge_pairs_combined.csv`, and
decides **which row of a pair should go**:

1. rows **1–921** of the merged register are a separate, *worse* OCR pass
   (`Amesen Kali`, `Burdett-Goutts`); where a pair straddles that boundary the
   block-1 row is the corrupted reading and gives way;
2. otherwise the row carrying **fewer citations** gives way;
3. equal → left for a human; "probably not a merge" pairs get no action.

It then joins five other review files onto rows, translating between id spaces
(`HCAP`, `Reg`, `PerXI`) as each file requires:

| Warning | Source |
|---|---|
| `label_corruption` | `label_corruption.csv` — `wor` overwritten by `Pag` |
| `run_on_reference_list` | `person_reference_merge_review.csv` (see §8) |
| `no_live_match:<tier>` | `person_crosswalk_review.csv` |
| `bad_page_reference` | `page_reference_problems.csv` |
| `duplicate_candidate` | `person_duplicate_candidates.csv` |

**Nothing is corrected.** A warning marks a row as needing a person.
Files holding human edits: `data/parsed/…_proposed_corrected-manually.tsv` and
`data/review/row_corrections_review_manual-corrections.csv`. In the merged,
annotated register the extra rows carry a `B` suffix on `01_entry_id` (e.g.
`PerXI00391B`), which keeps them from colliding with the positional numbering.

---

## 6. Stage 4 — emendations

`scripts/segmentation/apply_person_emendations.py` · `data/curated/person_emendations.tsv`

An emendation is **not an edit of the master**. The register is the source; a
correction is a separate, sourced claim laid over it at read time, because page
references point at what the book actually prints, corrections can be wrong,
and `01_entry_id` renumbers. The script therefore has **no apply-to-master mode**.

Each emendation row names its target by `(match_surname, match_refs)` — the
surname plus the sorted page-reference signature — never by id. It carries the
`field` (`surname`, `given_names`, `birth_year`, `death_year`, `description`),
the `original` value it expects to find, the `emended` value, `source`, `date`,
`confidence` and `notes`.

**Validation is the point.** A row is rejected (and output refused) if: the
field or confidence is unknown; `source` or `notes` is empty; the key matches no
row or **more than one**; or the master's current value no longer equals
`original` — the entry underneath has changed, so the correction must be
re-checked rather than applied to whatever now sits there.

| Mode | Writes |
|---|---|
| (default) | validates and prints |
| `--emit` | `data/normalized/person_emendations.json` for consumers |
| `--emit-resolved` | `data/normalized/personregister_xi_resolved.tsv` — corrections applied, originals preserved in `14_emended_fields`, `15_original_values`, `16_emendation_source` |

Two rules are implemented here rather than left to the consumer:

- **An emended surname moves the entry in the alphabet** (Oesterling sits among
  the Ø/Ö names; Osterley lands thousands of rows earlier). So the resolved view
  also gains a `krydshenvisning` at the *printed* position, id `<entry_id>x`,
  or a reader looking up the printed name finds nothing. Its wording follows the
  confidence: `certain` → "se:", `probable` → "sandsynligvis hentydning til:",
  `proposed` → "muligvis hentydning til:". "se:" is the register's own word for
  an identity not in dispute; using it for a probable identification would claim
  more than is known.
- **The enrichment chain reads the resolved form.** "Oesterling" has no forename
  and no years, so gender and lifespan cannot be derived; "Osterley, Carl
  (1805-1891)" gives all three.

Currently 5 emendations (1 `certain`, 4 `probable`); the resolved file is the
master's 10,079 rows + 2 generated cross-references. Guarded by
`tests/test_person_emendations.py`.

---

## 7. Stage 5 — identity: minting and crosswalk

### 7.1 `mint_person_ids.py` — assigned once, then carried

Writes `00_person_id` (`HCAP00001`, …) as the first column of the master.

> **An identifier is carried, never derived.** A content-derived id changes when
> a typo is fixed and breaks every citation to it — the same defect this
> repository objects to in V0.94's place ids, which resolve 0 of 2,433 against
> the live register.

Rows that already carry an id keep it whatever their content does; only rows
without one get the next free number. The script is idempotent, **will not
renumber**, backs up before writing, and `--verify` checks the invariants
(every row has exactly one well-formed, unique id) without writing. Guarded by
`tests/test_person_identity.py`.

### 7.2 `build_person_crosswalk.py` — HCAP ↔ Reg

Bridges the segmented register to the live ids. The matching key is the one
calibrated against this corpus in `compare_to_reference.py`:

```
fold_name(s) = strip every year parenthesis → NFKD, drop combining marks
               → æ→ae, ø→o → keep letters/spaces only → collapse → UPPER
signature    = the set of (volume, page) citations
```

Tiers, tried in order, **each exact on one axis**; nothing is matched on a
similarity score, so the reason for any given match can always be stated:

| Tier | Rule | Rows |
|---|---|---:|
| `exact_name` | folded name matches exactly **one** live label | 9,049 |
| `name_and_signature` | several name candidates; exactly one has an **identical** signature | 111 |
| `name_and_overlap` | several candidates; exactly one has the **largest, non-zero** page overlap | 169 |
| `signature_only` | no name match; exactly one live person cites the identical page set (a re-segmented name still cites the same pages) | 131 |
| `ambiguous` | candidates neither name nor signature resolves — **written out, not picked from** | 28 |
| `none` | nothing matches | 181 |

9,460 of 9,669 rows (97.8 %) resolve. `krydshenvisning` rows are skipped.
Every row records the tier and `shared_pages`, so a consumer can decide how much
to trust it. The crosswalk is **curated, not generated**: rows with
`note == "human"` are carried across re-runs unless `--refresh` is passed.
Unresolved rows go to `data/review/person_crosswalk_review.csv`.

### 7.3 `scripts/index_maintenance/`

The reusable engine for updating *any* index while keeping ids (carry, mint,
split, merge, retire into a ledger). It applies the same rule with four passes:
**carried id → exact label → signature → singular side** (one-to-many becomes a
split, many-to-one a merge). A key that is ambiguous on *both* sides identifies
nothing and is reported rather than paired. See
[`index-maintenance.md`](index-maintenance.md).

---

## 8. Stage 6 — merging page references

`scripts/segmentation/merge_person_references.py` (dry-run by default; `--apply` writes)

The segmentation cites 45,293 person→page references against the live
`references.csv`'s 39,361, and is 16× cleaner against the authoritative page list
(0.03 % invalid citations against 0.47 %). It is folded in **additively**: live
rows and their `Reg…` ids stay exactly as they are, and the segmentation only
supplies rows the live set lacks. Dropping the added rows restores the previous
state. New rows are *appended* — never re-sorted, which would move rows this step
promised not to touch.

Per register entry, in order:

1. skip an entry with no references;
2. **run-on check** (only if > 20 references *and* its own citation sits in the
   description);
3. skip if it has no crosswalk partner (`Reg` id);
4. per reference: skip a page absent from the ten-volume page list
   (`normalized_v094/diary_pages.csv`); skip a page the live person already has;
   otherwise add.

**The run-on check** is the subtle rule. 27 entries have a citation list in
`09_description` *and* one in `10_references_raw`. Those are two different
defects, told apart because **the register cites volumes in ascending order**:

| | Volumes | Meaning | Action |
|---|---|---|---|
| **Split list** (16 entries, 1,303 refs) | the description's volumes *precede* the raw ones | the parser ended the description early; both halves are one person's | **admitted** |
| **Run-on** (11 entries, 887 refs) | the description's volumes run *past* where the raw list restarts (`max(desc) > min(raw)`) | `10_references_raw` belongs to the **next** entry | **excluded**, written to `person_reference_merge_review.csv` |

A first pass excluded all 27 and discarded 1,303 valid references. Guarded by
`tests/test_person_reference_merge.py`, which holds up the "only ever adds"
argument.

---

## 9. Validation

| Check | Script | What it measures |
|---|---|---|
| **Coverage** against the independent transcription | `validation/compare_to_reference.py` | (1) fold names; (2) set-difference the folded names; (3) for each one-sided name, look for the **same page signature** on the other side — a match means a spelling variant, not a real gap. On the recorded numbers this reclassified 330 of 344 apparent surpluses and 170 of 171 apparent gaps. Also scans for duplicates: same folded surname + identical signature + compatible given names (surname + signature alone returns ~500 groups, mostly spouses and siblings who share pages). |
| **Page validity** | `validation/check_page_references.py` | citations to pages that do not exist; never repaired, never merged |
| **Index integrity** | `validation/check_indexes.py` | dangling cross-references; fields empty where the entry kind requires them |

The independent transcription is **not a pipeline input**. Nothing reads it for
production, and nothing should.

Tests: `test_personregister_xi_parsed`, `test_row_corrections`,
`test_person_emendations`, `test_person_identity`, `test_person_reference_coverage`,
`test_person_reference_merge`. The bounds are deliberately loose — they exist to
catch a change of shape (a batch import that doubles entries, a parser re-run
that discards the cleaning chain), not to pin today's figures.

---

## 10. Enrichment parsers over the live persons

These read the **live set** (`entities.csv`, `Reg…` ids) and write one file
each, adding a derived fact without touching the core. Each degrades gracefully:
a missing enrichment empties a facet, it does not break a build.

### 10.1 The label and the description

A person's `label` has the shape

```
Surname, Given names[, Title | f. Birthname] (year–year)
```

and `description` is the free text after it. `split_label()` (in
`parse_person_gender.py`) removes the year parenthesis first so it is not
mistaken for a name segment, then splits on commas. It yields
`(surname, [given names], [other segments])`, discarding initials and name
particles (`von`, `van`, `de`, `af` …).

**264 labels carry a *title* where a forename should be** (`Ahlefeldt, Frøken`,
`Aldridge, Mrs.`). Without the title list, `Frøken` would be counted as a given
name: the category would come out right for the wrong reason, the indicator text
would lie, and the name statistics would gain titles as "names". Title words are
therefore moved into the *other segments*, where the title marker handles them.

### 10.2 Ethnic / national descriptors

`enrichment/parse_person_ethnic_descriptors.py` → `person_ethnic_descriptors.csv`
(+ `_review.csv`)

- **Whitelist only.** Adjectives come from `data/curated/ethnic_adjectives_da.csv`
  (surface forms grouped by nationality key and category). Never a bare
  `-sk/-isk` suffix heuristic, so the excluded false-positive families cannot
  slip in by construction: academic-field adjectives (`romansk Filolog`),
  religious terms (`katolsk`), agent nouns (`marsk`, `husholderske`), and
  surname-derived `-ske` words (`Anckerske`) that name an estate, not a nation.
- Tokens are Unicode letter runs with internal hyphens (an earlier hand-listed
  accent set split `württembergsk` at the ü).
- Match types: `single`; `fixed_compound` (one political entity — `tysk-romersk
  Kejser` is a Holy Roman Emperor, not "German and Roman"); `hyphen_compound`
  (each part counts — `czekisk-dansk Violoncellist`); `solid_compound`
  (`svensknorsk`, found by splitting at a point where both halves are in the
  table, only tried on tokens shaped like an adjective and longer than 6 letters).
- **Position matters.** `leading` = the first word of the description (all but
  certainly about the subject); `embedded` = further in. For embedded matches a
  triage hint is recorded: `possible_relation` (a relation marker — `g`, `gift`,
  `m`, `søn`, `datter`, `enke`, … — in the 3 tokens before) or
  `possible_institution` (a definite article just before: *"Præst for den tyske
  Menighed"*) or `unclear`. This is **triage for a human, not a classifier**.
- Every `-sk/-iske`-shaped token the whitelist did **not** match is written to the
  review file, so new vocabulary and transcription typos (`fiansk` for `fransk`)
  surface on every run instead of vanishing.

Downstream, `parse_person_gender.py` uses only `leading` + `subject` matches as
the person's own nationality.

### 10.3 Role / occupation

`curation/parse_person_role.py` → `person_role.csv` (`entity_id, roller,
kilde_vaerk, kilde_beskrivelse_termer`). Not a pipeline stage — it reads the
publication repo's **built** `works-extra.js` (see `scripts/curation/README.md`).

A person can carry several roles (`;`-joined), from two independent sources:

- **A — works register.** A person who authored a work in a given wing gets that
  wing's bucket: `billedkunst` → Kunstner/Billedkunst, `bibliotek` →
  Forfatter/Digter, `teater-musik` → Musiker/Scenekunst. Resolved through
  `name_key()` — a 1:1 port of the JS `nameKey()` (folded surname + sorted set
  of given-name initials) so it agrees with what a reader already sees on the
  person's page.
- **B — description harvest.** About 185 hand-clustered terms
  (`data/curated/person_role_terms_da.csv`) in 9 buckets: Gejstlig, Militær,
  Adel/Kongelig/Hof, Embedsmand/Jura/Politik, Handel/Erhverv, Akademiker/Lærd,
  Kunstner/Billedkunst, Musiker/Scenekunst, Forfatter/Digter.

**Referent safety.** A leading relation clause is stripped *whole* before
harvesting (`RELATION_RE`: `Søn|Datter|Broder|Søster|…|Enke` + `af|til|efter` +
up to the next `,.;`), as is a marriage clause (`MARRIED_RE`: `g. [year[–year]]
m. …`). "Enke efter …" is the dominant widow form (142×) and names *his*
occupation, not hers. An empty role list is a legitimate result, like
"Endnu ubestemt" on the gender facet.

### 10.4 Gender

`enrichment/parse_person_gender.py` → `person_gender.csv`,
`given_name_gender_stats.csv`, `person_gender_review.csv`

Outputs **Mandlig | Kvindelig | Endnu ubestemt** with a confidence and the
explicit list of indicators it rests on. It is a facet category, not a claim
about identity, and "Endnu ubestemt" is a valid result — it marks that the
evidence does not suffice, not that something failed.

There is **no built-in name list.** Name knowledge is *derived from the register
itself*, so it fits this register's naming conventions and period (19th-century
Danish with German/French/Swedish admixture), is inspectable, and can be
recomputed.

#### Pass 1 — markers that need no name knowledge

Weights are in `data/curated/gender_markers_da.csv`.

| Marker | Fires when | Typical weight |
|---|---|---|
| title in label | `Grevinde`, `Komtesse`, `Fru`, `Frøken`, `Mrs`, `Frau` … (K) / `Greve`, `Baron`, `Konge`, `Prins`, `Sir`, `Herr` … (M) as its own label segment (`label_segment`; also `Konge af –`) | 2.2 – 3.0 |
| `Datter af` / `Søn af` | opens the description (`desc_prefix`) | 3.0 |
| relation | `Hustru`, `Søster`, `Moder`, `Broder`, `Fader`, `Ægtemand` as `X til …` or as the first word (`desc_relation`) | 2.0 – 2.8 |
| title, predicative | `Fru`, `Frøken`, `Jomfru`, `Madame` in the description (`desc_title_pred`) | 2.2 – 2.4 |
| civil status | `Enke` (K) / `Enkemand` (M) (`desc_word`) | 2.6 / 2.8 |
| pronoun | lower-case `hun`, `hendes` (K) / `han`, `hans` (M) (`desc_word_cased` — capital *Hans* is a name) | 1.8 – 2.0 |
| `f. <Surname>` | in the label — née; requires a capital after `f.` so `f. 1808` does not match | 3.0 (K) |
| `-inde` | `Forfatterinde`, `Skuespillerinde`, … (≥ 5 letters before `-inde`); `-minde` excluded (`Kerteminde`); relational words (`veninde`, `elskerinde`, …) weaker | 2.0 / 1.3 (K) |

**Referent safety** is the most important source of error in this register and
is built into the matching:

- A marker counts only **predicatively**. `Broder til Fru Therese Henriques,
  Typograf.` is a man; the *Fru* belongs to his sister.
- A relation word counts only as `X til …` or as the description's first word —
  not after a possessive (`hans Moder`).
- A title directly **before a proper name** names someone else (`Fru Therese
  Henriques`; `Fader til Fyrstinde Caroline`) and is skipped.
- `med` is treated like a possessive: `Dansk Turist med Frue og Børn` is a man
  *accompanied by* a wife.
- Place-name noise (`Vor Frue Kirke`, `Frue Plads`) is removed first — otherwise
  12 male parish priests would receive a female *Fru* marker.

#### Pass 2 — derive name statistics from the sure rows

Persons that pass 1 settles with **confidence ≥ 0.90** become the seed. For each
seed person, **only the first given name** counts (middle names are often family
names or namesakes of the opposite sex). It is counted in two buckets: the
person's own nationality (from §10.2) and a general bucket. A name becomes an
indicator only when it has enough coverage and a clear skew:

| Bucket | Min. n | Min. share | Weight scale |
|---|---:|---:|---:|
| nationality-specific | 3 | 0.85 | 1.0 |
| general | 5 | 0.85 | 0.75 (context unknown) |

Weight = `min(1.7, (skew − 0.5)·2.4 + log10(n)·0.5) · scale` — grows with skew
and sample size, but the **1.7 cap means a given name alone can never reach
"high confidence"**. `data/curated/given_name_gender_overrides.csv` overrides per
(name, nationality) — e.g. *María* neutralised in Spanish and Italian (*Juan
María* is male), *Jean* strengthened in French, *Anne* neutralised in French.
A weight ≤ 0 neutralises the name rather than flipping it.

A **spouse indicator** (`g. 1856 m. John A.`) uses the spouse's first name via
the same statistics and votes the *opposite* way at weight `min(1, 0.6·w)` —
explicitly labelled second-order, since it can amplify an error in the name
statistics.

#### Pass 3 — combine

```
score      = Σ(female weights) − Σ(male weights)
conflict   = min(Σ female, Σ male)
confidence = 1 / (1 + e^−|score|)            ∈ [0.5, 1.0]
if conflict ≥ 1.5:  confidence = 0.5 + (confidence − 0.5) · 0.45
category   = sign(score);  "Endnu ubestemt" if confidence < 0.70 or score == 0
```

Thresholds: **≥ 0.90** high, **0.70–0.89** probable, **< 0.70** undetermined.
The conflict damping exists so genuinely contradictory evidence cannot hide
behind a high score. The review queue is ordered: contradictory first, then
undetermined-with-indicators, then 0.70–0.89.

#### What this produced, and where it is weakest

10,228 persons: **3,714 Mandlig, 3,286 Kvindelig, 3,228 Endnu ubestemt.**
Measured in [`reports/gender-inference-experiment.md`](reports/gender-inference-experiment.md):

- The category is **itself inferred** — none of the source workbooks has a
  gender field. **2,337 of the 7,000 categorised rows rest on the given name
  alone.**
- Name statistics learned from Danish/German naming do not transfer: `Andrea`
  is 3/3 female here, yet Palladio and Vaccá Berlinghieri are Italian men;
  `Marie` and `Auguste` are male in French use (three French men are currently
  Kvindelig).
- `f.` in `Pseud. f. Georg …` ("pseudonym *for*") is read as *née*.
- `Jfr.`, `Frk.`, `Madam`, `Mile` sit in the given-name position and are learned
  as names rather than recognised as markers.
- Reference stubs and mis-segmented rows (`– Se også: Nielsen, Augusta.`) receive
  a gender, although gender belongs to the target, not the pointer.
- Titles in the **description** (`Komtesse`, `Greve`, `Pave`) are not read — only
  titles in the label are. 121 of the undetermined persons carry such a title.

Any further inference for the undetermined third must be stored as a **separate
inferred enrichment**, never as an overwrite of this file; see §8 of that report.

### 10.5 Related, out of scope here

- `parsers/ner_page_grounding.py` locates, in the transcribed diary text, the
  strings for entities that `references.csv` already says appear on a page. It is
  a rule-based baseline (surname + first given name, whole-word, joined into a
  high-confidence "full name" hit when close together), **not open NER**. Only a
  minority of pages have transcribed text.
- `scripts/correspondence/*` extracts and matches the sibling *Brevveksling*
  person index against the register.

---

## 11. Principles the parsers share

| Principle | Where it shows |
|---|---|
| **Findings are not corrections** | `suggest_*` writes review files; emendations lie over the master; warnings only mark |
| **Additive over destructive** | `14_recovered_references` beside, not over, `11_references_parsed`; the reference merge appends; enrichments write their own files |
| **Identifiers are carried, never derived** | `mint_person_ids.py`, `index_maintenance` |
| **Exact on one axis, never fuzzy** | every crosswalk tier; `ambiguous` is written out, not guessed |
| **Tiering by who must decide** | tier 1–2 mechanical, 3 needs a decision, 4 never automatic |
| **Validate the premise before acting** | emendations store the `original` they expect and refuse to apply if it moved |
| **Whitelists, not suffix heuristics** | ethnic adjectives, role terms, gender markers |
| **Referent safety** | gender and role strip or skip clauses that describe a *relative*, not the subject |
| **Surface what was not matched** | `person_ethnic_descriptors_review.csv`, the role "unused terms" report |
| **Triage hints are not classifiers** | `referent_hint` is for a human |
| **Honest uncertainty** | `Endnu ubestemt`; conflict damping; `probable`/`proposed` emendation wording |

## 12. Sharp edges

Things found while documenting that a newcomer will otherwise trip over:

1. **`parse_personregister_xi.py` writes the committed master.** Re-running it
   replaces 10,079 reviewed rows with ≈ 9,338 unreviewed ones. Redirect its
   output before experimenting.
2. **`apply_person_emendations.py` reads `data/review/personregister_xi_review_full.tsv`**
   (the master *plus* `review_flags`), not `data/parsed/…parsed.tsv` — and its
   docstring still names an `archive/` path although the script lives in
   `scripts/segmentation/`. Both files currently have 10,079 rows, but they are
   two files and can drift.
3. **Despite its `apply_` prefix, `apply_person_emendations.py` never writes the
   master.**
4. **`01_entry_id` is a row number.** The `B`-suffixed ids of manually inserted
   rows and the `<id>x` ids of generated cross-references are conventions, not
   identifiers; use `00_person_id` for anything that must survive.
5. **`parse_person_role.py` needs a built sibling checkout** (`hca-open-repo`) and
   re-implements the JS `nameKey()` — a silent drift risk if the JS changes.
6. **The cleaning chain is provenance, not a build step.** Replaying it is
   impossible by design (§4).
7. **Gender is inferred, not recorded**, and its name statistics are culturally
   narrow (§10.4). Treat "Mandlig/Kvindelig" as *derived from markers and given
   names* in any UI or documentation.

## 13. File map

| Concern | Script | Reads | Writes |
|---|---|---|---|
| OCR parse | `segmentation/parse_personregister_xi.py` | OCR PDF | `parsed/personregister_xi_parsed.tsv`, `review/personregister_xi_review.tsv` |
| Chain (archived) | `segmentation/archive/*` | review files | the master |
| Detect | `segmentation/suggest_row_corrections.py` | master | `review/row_corrections_review.csv`, `parsed/….proposed.tsv` |
| Annotate | `segmentation/annotate_register_with_recommendations.py` | merged register | cols 15–23 |
| Warn | `segmentation/add_warnings_and_actions.py` | annotated register + 5 review files | cols 24–26, `review/merge_pairs_combined.csv` |
| Emend | `segmentation/apply_person_emendations.py` | master, `curated/person_emendations.tsv` | `normalized/person_emendations.json`, `normalized/personregister_xi_resolved.tsv` |
| Mint ids | `segmentation/mint_person_ids.py` | master | `00_person_id` column |
| Crosswalk | `segmentation/build_person_crosswalk.py` | master, `entities.csv`, `references.csv` | `curated/person_id_crosswalk.csv`, `review/person_crosswalk_review.csv` |
| Merge refs | `segmentation/merge_person_references.py` | master, crosswalk, `references.csv`, V0.94 page list | `references.csv` (appended), `review/person_reference_merge_review.csv` |
| Coverage | `validation/compare_to_reference.py` | master, independent transcription | review CSVs |
| Nationality | `enrichment/parse_person_ethnic_descriptors.py` | V0.82 workbook, `curated/ethnic_adjectives_da.csv` | `normalized/person_ethnic_descriptors.csv` |
| Role | `curation/parse_person_role.py` | `entities.csv`, built `works-extra.js`, `curated/person_role_terms_da.csv` | `normalized/person_role.csv` |
| Gender | `enrichment/parse_person_gender.py` | `entities.csv`, ethnic descriptors, `curated/gender_markers_da.csv`, `curated/given_name_gender_overrides.csv` | `normalized/person_gender.csv`, `given_name_gender_stats.csv` |
| Gender experiments | `enrichment/gender_inference_experiments.py` | the above | `review/gender_inference/` |
