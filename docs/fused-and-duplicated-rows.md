# Fused and duplicated rows

One scanning defect, in two directions: **one printed entry read as two rows**,
and **two printed entries read as one row**. Both are found by the same pass.

```
python scripts/segmentation/suggest_row_corrections.py            # dry run
python scripts/segmentation/suggest_row_corrections.py --write
```

It writes findings and a proposal. **It never writes the register.**

| | |
|---|---|
| `data/review/row_corrections_review.csv` | every finding, with its evidence and what it proposes — committed |
| `data/parsed/personregister_xi_parsed.proposed.tsv` | the register with the safe corrections applied, to diff against the master — regenerable, not committed |

---

## Where the rule came from

The regexes are not new. They were written for
`scripts/parsers/build_review_workbook.py` and described in
[`docs/data-model/ocr-and-segmentation-scan-2026-09-05.md`](https://github.com/ogierMontanus/hca-open-repo)
in the publication repo. Re-running them today reproduces that scan's counts
**exactly** — nothing upstream has been fixed since:

| rule | column | then | now |
|---|---|---:|---:|
| `reference_run` | `04_given_names` | 16 | 16 |
| `description_reference_run` | `09_description` | 61 | 61 |
| `embedded_name_year` | `09_description` | 27 | 27 |
| `see_reference` | `04_given_names` | 1 | 1 |

They are imported rather than re-written, so there is one definition instead of
two that drift.

### What the rule looks for

A roman numeral, an arabic page run, and a terminating period — a citation —
sitting in a column that cannot hold one:

```
(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+
```

`09_description` holds prose and `04_given_names` holds names. A citation in
either is, by construction, text that belongs to a different column or a
different row. That is why the rule is reliable: it is not guessing at meaning,
it is finding a shape that cannot legitimately occur where it occurs.

---

## The finding that changed the design

The pre-existing rule and [the run-on rule used by the reference
merge](person-index-data-quality.md) have **zero overlap**. They are opposite
failures, and conflating them was the mistake worth avoiding:

| | what went wrong | how many |
|---|---|---:|
| **run-on** (step 10c) | this entry's *reference list* absorbed the next entry's | 27 |
| **fused** (this rule) | this entry's *own citations* were never parsed out of its description | 61 |

Of the 61 fused rows, **51 carry two or fewer parsed references** while their
descriptions hold roughly **192 unparsed page numbers**. `Tybjerg` has one
parsed citation against about thirty-seven stranded in prose; `Danner` one
against fourteen. Those pages are not wrong in the register — they are simply
not in the column anything reads.

---

## Four tiers, because "fused" is not one problem

The useful distinction is not how confident the match is. It is **what a
correction would cost if it were wrong**.

### 1 · Recover the citations — mechanical

A citation inside a description is in the wrong column by definition, and there
is nothing to decide. It is written to a **new** `14_recovered_references`
column, never over `11_references_parsed`, and any page already carried there
is dropped rather than repeated. Purely additive, so it cannot lose anything.

**67 rows, 145 page references that nothing currently reads.**

### 2 · Trim the column — safe

Everything from the hanging name onward belongs to a different entry and is
removed from this one. Checkable against `13_raw_text` without knowing anything
about the people involved.

**77 rows.**

### 3 · Split out a new row — only where there is nothing to split into

This is where the measurement mattered. Of the fused tails, **54 name someone
who already has a row of their own**. Splitting those would manufacture a
duplicate — turning a fusion into the *other* defect on this page, which is
worse, because a duplicate divides a person's citations in two and nothing
signals that it happened.

Only **17 tails name someone with no row at all.** Those are genuinely lost
entries: `Ahrens (Arenz), Portugiser, Setubal`, `Birger Jarl (død 1266)`,
`Jean Paul (Pseud. f. Johann Paul Friedrich Richter)`, `Uxkull (Uexkull),
Clara`.

Proposed, never applied — a new row needs an identifier, and minting one is
[`index_maintenance`](index-maintenance.md)'s job, not a scanner's.

### 4 · Merge — reported, never applied

Removing a row renumbers `01_entry_id` and rewrites every citation that named
it. It is the most destructive edit in this project and the one most often
wrong. Nothing here touches it.

---

## The reverse defect: rows that need merging

Two rows are merge candidates when they cite **the same two or more pages**
under names that are **80 % alike**. One shared page is coincidence in a
register this dense; two is not.

Then a second test separates the real ones. A pair whose names differ only by a
substitution the scanner actually makes is a reading error:

```
rn ↔ m    ii ↔ ü    c ↔ e    c ↔ g    l ↔ i    o ↔ ö    a ↔ ä    "" ↔ " "
```

**13 pairs pass it** — `Amesen Kali` / `Arnesen Kali`, `Golloredo-Mansfeld` /
`Colloredo-Mansfeld`, `Clausen-Schiitz` / `Clausen-Schütz`,
`Sayn-Wittgens tein-Berleburg` / `Sayn-Wittgenstein-Berleburg`. Each is one
scanner confusion away from its twin.

**4 pairs fail it** and are demoted to *probably not a merge*: `Jensen` /
`Jørgensen`, `Philipsen` / `Philips`, `Braminer` / `Brammer`,
`Storbritannien og Irland` / `Storbritannien og Wales`. Similar names, real
distinctions — they share pages because they appear on the same diary pages,
which is what people who know each other do.

Without that second test all seventeen look alike, and a reviewer who finds
`Jensen / Jørgensen` at the top of the list stops trusting the other sixteen.

Plus **2 exact duplicates** — `Bretton, Florence, Baronesse` and
`Melchior, Emil` — identical in name, years, description and citations.

---

## Using it

```
$ python scripts/segmentation/suggest_row_corrections.py --write
  register rows 10,079

    tier 1  recover citations                         67
    tier 2  no split — the entry already exists       54
    tier 2  trim the column                           77
    tier 3  split out a new row                       17
    tier 4  merge — review by hand                    13
    tier 4  probably not a merge — review by hand      4
    tier 4  review by hand                            27
```

Then diff the proposal against the register:

```
git diff --no-index data/parsed/personregister_xi_parsed.tsv \
                    data/parsed/personregister_xi_parsed.proposed.tsv
```

Tiers 1 and 2 are in that diff and can be promoted by replacing the master with
the proposal. Tiers 3 and 4 are not: they are in the review CSV, and they need
a person, then a run of
[`update_index.py`](index-maintenance.md) to mint what a split creates and to
follow references through a merge.

## Related

| | |
|---|---|
| [`person-index-data-quality.md`](person-index-data-quality.md) | the run-on rule, and why it is a different defect |
| [`index-maintenance.md`](index-maintenance.md) | what happens after a split or merge is decided |
| [`reports/person-index-input-report.md`](reports/person-index-input-report.md) | written for the register's maintainers |
