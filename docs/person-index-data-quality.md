# Person-index data quality — method and findings

How the problems in the person register were found, how each was classified,
and what was done with it. Written while carrying out plan steps 10b–10c, and
kept because the *method* is reusable: the same three checks apply to the work
and place registers when their turn comes.

The short version, for the people who maintain the register, is
[`reports/person-index-input-report.md`](reports/person-index-input-report.md).

---

## 1. Why none of this was measurable before

Three things had to exist before the register could be checked at all, and
none of them did:

| | |
|---|---|
| **An authoritative page list** | V0.82's `diary.csv` holds volumes VI–VII only, so a citation to `IX:454` had nothing to be wrong against. V0.94's `3-DIARY-PAGES` supplies 4,413 pages across all ten volumes. |
| **A stable identifier** | `01_entry_id` is a row number assigned at parse time. `PerXI00001` is "Åberg" in a fresh parse and "Abbott" in the committed file. Nothing could be tracked across a change. |
| **A scripted comparison** | The coverage measurement against the independent transcription existed only as prose in `person-register-segmentation.md`, which says of itself "ingen færdig scriptfil". |

All three now exist: `data/normalized_v094/diary_pages.csv`, `00_person_id`
(minted by `scripts/segmentation/mint_person_ids.py`), and
`scripts/validation/compare_to_reference.py`.

---

## 2. The checks

### 2.1 Do the cited pages exist?

`scripts/validation/check_page_references.py` joins every citation against the
page list and classifies the failures.

| | citations | invalid | |
|---|---:|---:|---|
| live `references.csv` | 69,405 | **329** | 0.47 % |
| segmented register | 45,293 | **14** | 0.03 % |

Failure kinds: `missing` (no volume or page at all), `out of range` (page
number past the end of its volume), `unknown vol`.

The out-of-range cases are almost always digits that ran together — `I:1841`
is a year, `IX:222123` is two page numbers concatenated, `V:2456` is "245"
and "6". **Nothing is repaired.** A citation points at a printed page, and
guessing which digits to drop would invent a claim about what the diary says
on a page nobody has checked. Findings go to
`data/review/page_reference_problems.csv`.

### 2.2 Does the register cover the same people as an independent transcription?

`data/raw/Personer _ HCA_tsv.txt` is a separately produced, already
person-per-row transcription of the same printed volume. It is not a pipeline
input — it is the only external check that exists.

`scripts/validation/compare_to_reference.py` reproduces the method the
original session used by hand:

1. **Fold the name** — NFKD-strip diacritics, remove *every* year parenthesis
   (removing only the trailing one was an early bug), fold punctuation away,
   upper-case.
2. **Set-difference the folded cores.** What appears on one side only is a
   *candidate* discrepancy, not yet a real one.
3. **Disambiguate on the page-reference signature.** If the opposite side has
   an entry citing exactly the same `(vol, page)` set, the two are the same
   person spelled differently.

Step 3 is what makes the measurement worth anything: it reclassifies 250 of
314 apparent surpluses and 170 of 210 apparent gaps as spelling variants.

Result: 9,669 register entries against 9,538 in the transcription, **net real
difference +24** — reproducing the hand measurement's ~10 closely enough to
trust, with the remaining gap explained by the register having moved from
10,136 to 10,079 rows since that session.

#### Two wrong turns worth recording

Both were caught by the numbers rather than by reading, and both are now
covered by tests in `tests/test_person_reference_coverage.py`:

- **A redirect stub is identified by its `se:` marker, not by having no
  citation.** 1,276 transcription rows carry no tabulated page, but only 690
  are redirects; the other 594 are ordinary people whose citations that
  transcription simply did not put in columns. Excluding all 1,276 mislaid
  594 real entries and reported a **net +572 discrepancy that did not exist.**
- The redirect pattern then matched `ogsaa` but not `også`, leaving ~300
  stubs counted as missing people.

### 2.3 Are there duplicate entries?

Same script. Group on folded surname + identical page signature + **compatible
given names**.

The given-name test is what makes the scan usable. Surname and signature alone
return ~500 groups, mostly siblings and spouses who share pages because they
appear together — "Anholm, Frieda" beside "Anholm, Ida". Requiring the given
names to be compatible (one empty, equal, or an initial-form of the other)
leaves **66 groups**, and those look like real candidates: a bare "Bang"
beside "Bang, Caroline Amalie, f. Ibsen" on the same page.

This is the class the session record lists as known weakness #3 — "der er
intet i tests der fanger en fremtidig gentagelse". There is now.

---

## 3. The split/run-on defect, and how the two are told apart

The most consequential finding, because getting it wrong in either direction
loses data.

### The symptom

27 register entries carry a citation list in `09_description` **as well as**
one in `10_references_raw`. A first pass excluded all 27 from the reference
merge, on the assumption that they had absorbed a neighbour's list.

**That was too blunt.** They are two different defects.

### The discriminator: volume order

The register cites volumes in ascending order. That single fact separates
them:

```
CLASS A — split citation list         CLASS B — run-on into the next entry
16 entries, 1,303 references          11 entries, 887 references

description  II 33 … VIII …           description  … X 335 342 384.
references   X 2 7 21 …               references   IV 269 367 393-96 …
             ^ volumes CONTINUE                    ^ volumes GO BACKWARDS
             both halves are his                   the list is the next
                                                   person's
```

**Class A** — the parser ended the description early, stranding the head of
the citation list there and keeping the tail in `10_references_raw`. Both
halves belong to this person. Verified against the live register: every
reference these entries contribute falls in the *tail* volumes, exactly as
the diagnosis predicts. Baller, Sophie gains 24 volume-X references against
the 1 the live register holds. **Admitted to the merge.**

**Class B** — `10_references_raw` belongs to the *following* entry. Scharff,
Elvilda Antonia Victoria is the clearest: her own three pages sit in the
description as "X 335 342 384.", the references restart at IV, and her
`13_raw_text` visibly runs on into "Scharff, H…". Merging these would
attribute hundreds of pages to the wrong person. **Excluded**, and written to
`data/review/person_reference_merge_review.csv`.

Implemented as `runs_on_into_next_entry()` in
`scripts/segmentation/merge_person_references.py`.

### Why it matters that the first rule was wrong

Excluding all 27 discarded 1,303 valid references — more than the 887 it
correctly withheld. A blunt safety rule is not automatically the safe one,
and "exclude anything that looks odd" cost more than it saved.

---

## 4. What was done with each finding

| Finding | Count | Action |
|---|---:|---|
| Citations to pages that do not exist (register) | 14 | Excluded from the merge, reported. Never repaired. |
| Citations to pages that do not exist (live data) | 329 | Reported. Pre-existing, and not this migration's to fix. |
| Run-on entries (class B) | 11 | Excluded from the merge, sent to review. |
| Split citation lists (class A) | 16 | Admitted after verification against the live register. |
| Duplicate candidates | 66 groups | Reported for editorial review. |
| Exact-duplicate rows | 2 pairs | **Left in place.** They differ in `13_raw_text`, so all 10,079 rows stay distinct and no deletion was needed to mint identifiers. Removing a scholarly row is an editor's decision. |
| Entries with no live counterpart | 209 | Reported in `data/review/person_crosswalk_review.csv`. |
| `01_entry_id` is positional | — | Superseded by `00_person_id`, minted once and carried. |

---

## 5. The principle these share

Every check above **reports and withholds; none repairs.** The pipeline's own
constraint is that ambiguity is escalated rather than guessed, and a citation
or a name in this material is evidence about a printed book. The value of
finding 329 bad citations is that a person can now look at them — not that a
script can now silently rewrite them.

The one place data was changed — the reference merge — is strictly additive
and append-only: the first 80,803 lines of `references.csv` are byte-identical
and dropping the tail restores the previous state exactly.

---

## 6. Reproducing all of it

```bash
python scripts/validation/check_page_references.py --write
python scripts/validation/compare_to_reference.py --write
python scripts/segmentation/merge_person_references.py          # dry run
python -m pytest tests/ -q
```

Review output lands in `data/review/`. See
[`architecture.md`](architecture.md) for where these sit in the pipeline, and
[`migration-plan.md`](migration-plan.md) §J.6 for the acceptance criteria the
merge was measured against.
