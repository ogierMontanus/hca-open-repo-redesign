# Problems found in the person-index input

**For:** whoever maintains the *Personregister* (bind XI) segmentation and the
diary data cleaning.
**From:** the pipeline work in
[`hca-open-repo-redesign`](https://github.com/ogierMontanus/hca-open-repo-redesign),
plan steps 10b–10c.
**Date:** 2026-09-14.

---

## Why you are hearing about this now

Most of what follows could not be checked until recently, and nothing here is
a complaint about the cleaning work — the segmented register turns out to be
**16 times cleaner than the data the live site currently runs on**. What
changed is that three missing pieces arrived at once:

- **V0.94's `3-DIARY-PAGES`** lists 4,413 pages across all ten volumes. Until
  it did, a citation to `IX:454` had nothing to be wrong against, because
  V0.82's `diary.csv` covers volumes VI–VII only.
- **The register now has stable identifiers** (`00_person_id`). `01_entry_id`
  is a row number: it is "Åberg" in a fresh parse and "Abbott" in the
  committed file, so nothing could be tracked across a change.
- **The coverage measurement is a script now.** It existed as prose in
  `person-register-segmentation.md`, which says of itself *"ingen færdig
  scriptfil"*.

So this is the first time anyone could actually count these things.

**Nothing below was repaired.** Every finding was reported and withheld,
never silently rewritten — a citation points at a printed page, and guessing
which digits to drop would invent a claim about what the diary says. All of it
is sitting in CSV files for you, listed at the end.

---

## 1. The big one: 27 entries where the citation list is broken in two

**This is the finding worth your time.** 27 entries carry a citation list in
`09_description` *as well as* one in `10_references_raw`. They are two
different defects, and they need opposite treatment.

### Class A — the list was split (16 entries, 1,303 references)

The parser ended the description early, leaving the **head** of the citation
list stranded there and keeping the **tail** in `10_references_raw`. Both
halves belong to the same person.

> **Bournonville, August** — description ends `II 33 213 346 361. III 122 …
> VIII …`, while `10_references_raw` holds `X 2 7 21 33-34 …`.
> Both are his.

### Class B — the list belongs to the next person (11 entries, 887 references)

`10_references_raw` was filled from the **following** entry. The entry's own
pages are the ones left in the description.

> **Scharff, Elvilda Antonia Victoria** — her own three pages sit in the
> description as `X 335 342 384.`; `10_references_raw` starts at `IV 269 …`
> and runs to 275 references; her `13_raw_text` visibly runs on into
> `"Scharff, H…"`. The live register has exactly 3 references for her.

### How to tell them apart

The register cites volumes in **ascending order**. That one fact separates
them cleanly:

| | description volumes | reference volumes | verdict |
|---|---|---|---|
| Class A | II … VIII | **X** — continues | both halves are this person's |
| Class B | … X | **IV** — goes backwards | the list is the next person's |

### What we did

Class A was **admitted** after checking every entry against the live register:
the references they add all fall in the tail volumes, exactly as the diagnosis
predicts. Baller, Sophie gained 24 volume-X references against the 1 the live
register holds.

Class B was **excluded** and written out for you. Merging it would attribute
hundreds of pages to the wrong people.

> Worth flagging honestly: our first rule excluded all 27, and that was wrong
> — it threw away 1,303 valid references to withhold 887 bad ones. A blunt
> safety rule is not automatically the safe one.

**What would help at source:** if the parser's boundary between description
and reference list can be made to end at the citation list rather than inside
it, class A disappears entirely. Class B looks like a missed entry boundary —
the next person's header was not recognised as a header.

Full list: `data/review/person_reference_merge_review.csv` (class B),
and §3 of [the method notes](../person-index-data-quality.md) for class A.

---

## 2. Citations to pages that do not exist

Now checkable for the first time.

| | citations | invalid | |
|---|---:|---:|---|
| **segmented register** | 45,293 | **14** | 0.03 % |
| live `references.csv` | 81,080 | 329 | 0.41 % |

The register is in good shape here. The 14 are digits that ran together:

```
I:1841       a year read as a page number
IX:222123    two page numbers concatenated
V:2456       "245" and "6"
VIII:1345    "134" and "5"
```

They were excluded from the merge and reported, not repaired.

The 329 in the live data are a separate, pre-existing problem — 192 rows with
no volume or page at all, 81 past the end of their volume, 56 in an unknown
volume. Mostly work references (192) rather than person ones (128). Not yours,
and not fixed here, but now visible.

That count is also a check on our own merge: it stayed at exactly 329 while
`references.csv` grew from 69,405 rows to 81,080, so the 11,675 references we
added contain no invalid citation at all.

Full list: `data/review/page_reference_problems.csv`.

---

## 3. Duplicate candidates — 66 groups

Entries sharing a surname, an identical page signature, **and** compatible
given names:

> a bare **"Bang"** beside **"Bang, Caroline Amalie, f. Ibsen"** on the same
> page.

The given-name test matters: surname and page alone return ~500 groups, mostly
siblings and spouses who legitimately share pages ("Anholm, Frieda" beside
"Anholm, Ida"). Requiring compatible given names leaves 66 that look real.

This is the class your own notes flag as known weakness #3 — *"der er intet i
tests der fanger en fremtidig gentagelse"*. There is a test now.

Full list: `data/review/person_duplicate_candidates.csv`.

### And two exact duplicates

**Bretton, Florence, Baronesse** and **Melchior, Emil** each appear twice.
The rows differ only in `13_raw_text` — `"Bretton,Florence"` without the
space, `"(1857-81)"` against `"(1857–1881)"` — so they are the same entry
transcribed twice from two sources.

**We left both copies in place.** Because they differ in raw text, all 10,079
rows stay distinct and no deletion was needed. Removing a scholarly row is
your call, not a precondition for our work.

---

## 3b. 18 labels damaged by a find-and-replace

Found while assessing the V0.94 work register, and **not an OCR problem**:

```
Festen paa KenilPagth                  ->  Festen paa Kenilworth     (W. Scott)
Household Pagds (Udg.: Charles Dickens) ->  Household words          (Dickens)
Journey to Angora (William AinsPagth)  ->  … Ainsworth
Einige Pagte über Pferdezucht          ->  Einige worte …
Om Holger-Danske-Sagnet (Pauline Pagm) ->  … Pauline worm
```

The letters **`wor` have been replaced by `Pag`** — 15 works, 2 persons and 1
place. OCR does not turn three letters into three different letters
consistently, mid-word, across unrelated entries. It looks like a
substitution meant for the `Pag…` page-handle prefix that ran over the label
text on its way past.

The damage is in the **V0.82 workbook**, so it is upstream of us and shows on
the live site today. V0.94's work registry does not have it, which is how it
surfaced: the corrupted entries are among the handful that fail to crosswalk
between the two.

Careful with the detection — six real names legitimately begin with "Pag"
(Paganini, Paget, Pagani, Pagh, Pagliani-Gagliardi). There is no mechanical
way to tell `Pagds` → `words` from `Pagani` → `worani`; the six are excluded
by name, so a new one will show up as a finding rather than be silently
swallowed.

**Not repaired here** — the fix belongs in the workbook. Correcting it
downstream would leave the source wrong and quietly diverge the two.

Full list with suggested corrections: `data/review/label_corruption.csv`,
from `scripts/validation/check_label_corruption.py`.

---

## 4. Coverage against the independent transcription

Measured against `Personer _ HCA_tsv.txt`:

| | |
|---|---:|
| register person entries | 9,669 |
| transcription person entries | 9,538 |
| **net real difference** | **+24** |

That reproduces the ~10 reached by hand in the original session closely enough
to trust; the gap is explained by the file having moved from 10,136 to 10,079
rows since.

209 entries have no counterpart in the live register and 40 appear in the
transcription but not ours — both lists are in
`data/review/person_crosswalk_review.csv` and
`data/review/person_reference_unmatched_reference.csv`.

---

## 5. `01_entry_id` renumbers

Not news to you — `apply_person_emendations.py` already gives this as the
reason emendations are layered over the register rather than edited into it.
What is new is the measurement:

```
                  fresh parse        committed file
PerXI00001        Åberg              Abbott
PerXI05000        Licht, Carl        Jacobsen, Peder
```

The chain inserted 741 rows, so every id after the first insertion moved.

We added `00_person_id` (`HCAP00001`…) as a first column: assigned once,
carried thereafter, never re-derived from content. Purely additive — one new
column, no existing value touched. If the register is regenerated on your
side, that column should travel with the rows rather than be recomputed.

---

## What we changed, and what we did not

**Changed:** `references.csv` gained 11,675 references across 2,373 people,
strictly additive and append-only, so no person lost anything and dropping the
appended rows restores the previous state exactly.

**Not changed:** no citation repaired, no duplicate removed, no name altered,
no row deleted. Every problem above is reported, not fixed.

## The files

| File | Contents |
|---|---|
| `data/review/person_reference_merge_review.csv` | the 11 class-B run-on entries |
| `data/review/page_reference_problems.csv` | all 343 invalid citations, both sides |
| `data/review/person_duplicate_candidates.csv` | the 66 duplicate groups |
| `data/review/person_crosswalk_review.csv` | 209 entries with no live counterpart |
| `data/review/person_reference_unmatched_*.csv` | coverage gaps against the transcription |
| `data/review/label_corruption.csv` | the 18 `wor`→`Pag` labels, with suggested corrections |

Method, including how each check works and the two mistakes we made getting
there: [`docs/person-index-data-quality.md`](../person-index-data-quality.md).
