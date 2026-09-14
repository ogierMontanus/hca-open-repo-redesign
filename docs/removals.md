# Removals — what was removed, what was not, and why

Plan step 12, the last one. The short answer: **almost nothing was removed,
and that is the correct outcome.**

The plan's removal list was written before the migration ran. Most of it was
conditional on decisions that have since gone the other way, and the rest
turned out on inspection to be load-bearing. This records each item and its
verdict, so that the next person does not have to re-derive them — and so that
the ones still genuinely available can be taken when their blocker lifts.

---

## 1. The publication-repo removals are blocked by decision, not evidence

The largest group by far — A's `data/raw/`, `raw/`, five `scripts/`
directories, 56 cleaning-only data files, and `openpyxl`/`lingua` from its CI.

**The evidence for all of them is solid.** PR #1 verified it: A's build was run
with `data/raw/` and `raw/` moved aside entirely and produced byte-identical
output, so nothing there depends on the raw sources any more.

**But the user chose to leave `hca-open-repo` alone**, and step 4 — the
commit that strips preprocessing out of it — was dropped. Until that lands,
A still runs its own copies of this pipeline and needs every one of these
files. Removing them would break it.

So: **available, evidenced, and not actionable.** They come back on the table
the day step 4 does.

---

## 2. Items whose verdict changed while the migration ran

| Plan said | Now | Why |
|---|---|---|
| `data/parsed/personregister_xi_parsed.tsv` — "wire in or stop maintaining" | **Neither. It is the person source.** | Resolved at §E.3. It is richer than the live data (45,293 references against 39,361) and 16× cleaner on citation validity. Not a removal candidate at all — it moved *into* the published interface. |
| `data/normalized_v092/*` — "become the primary files at cutover" | **They never will.** | V0.94 superseded V0.92 for places and pages, and V0.92's person slice covers two volumes out of ten. Kept as a verification surface, which is what they already were. |
| `build_cooccurrence.py` — "deleted at the V0.92 cutover, replaced by `FactDiaLocPerPag`" | **Stays.** | V0.94 withdrew the fact tables. There is no successor to replace it with. |
| The title-parenthesis artist regex — "superseded by V0.94's `Artist`" | **Stays, and is the better source.** | Across the 921 shared BILLEDKUNST works the regex fills 267 artists and V0.94 fills 3. The plan had this backwards. |
| `build_kb_links.py` + the `.xlsm` — "superseded by `KBLinkString`" | **Stays.** | V0.94's links are byte-identical, so switching gains nothing — and it would lose the OffSetTab derivation check, which caught vol I page 13. |
| The bounding-box gazetteer in `build_web_data.py` | **Stays** (and is in A anyway). | Retiring it depends on adopting V0.94's places, which is blocked on identity: `OLDLocationID` resolves 0 of 2,433. |

Six of the plan's removal candidates, and **not one of them survived contact
with a measurement.** That is worth noticing: a removal list written from a
design is a list of hypotheses, not a work queue.

---

## 3. `ner_page_grounding.py` — dormant, not abandoned

The plan's one genuinely open question: *"Committed, read by no build stage.
Establish whether it is dormant or abandoned."*

**Dormant.** It is not stray code:

- It implements a **written task definition** — `docs/data-model/ner-page-task.md`
  in the publication repo — and its docstring is explicit that this is not
  open NER extraction: the entity is known in advance from `references.csv`,
  and the job is only to locate the occurrence string in the page text.
- It is a deliberate rule-based baseline, with the method and its limits
  spelled out.
- It is blocked on something concrete and external: **`diary.csv` holds
  transcribed text for 751 of 4,549 pages.** It cannot ground what it cannot
  read.

V0.94 does not lift that block — it carries a ten-volume page list but no
diary text at all. So the work resumes if and when more of the diaries are
transcribed, and the script is exactly what should be waiting when that
happens.

Its two outputs (1.0 MB and 0.9 MB) stay committed for the same reason.

---

## 4. What was actually moved

Four files were in the wrong folder — a loose end from step 8, which split
`data/curated/` by lifecycle but left review artefacts sitting in
`data/normalized/`:

```
data/normalized/ner_page_grounding_review.csv        -> data/review/
data/normalized/person_ethnic_descriptors_review.csv -> data/review/
data/normalized/person_gender_review.csv             -> data/review/
data/normalized/sv14_places_ambiguous.csv            -> data/review/
```

All four are written by one stage, read by nothing, and published to nobody —
the definition of a review artefact under the rule
[`data/review/README.md`](../data/review/README.md) states. None is in the
interface, so nothing downstream moved.

Verified by re-running stages 1c, 1e and 1f: each now writes to
`data/review/` and nothing reappears in `data/normalized/`.

---

## 5. What was checked and found clean

A reachability audit over the whole repository, rather than working from the
plan's list:

- **118 data files.** 24 published, the rest either written by a stage or
  hand-maintained. After the four moves above, none is misfiled.
- **53 live scripts** (excluding `scripts/segmentation/archive/`). Every one
  is reached by the runner, the tests, the docs, or another script. The
  apparent orphans — `correspondence/`, `migration/`, `place_typology/` — are
  documented as groups rather than per file, which is appropriate for
  occasional curation passes whose output is committed.
- **No tracked cruft**: no `.bak`, no `__pycache__`, no `.pyc`, no
  `desktop.ini`, no editor lock files. Working tree clean.

Steps 7 through 9 did the tidying that a removal pass would normally find.
There was nothing left to sweep.

---

## 6. Still available, when their blocker lifts

| Removal | Waiting on |
|---|---|
| A's `data/raw/`, `raw/`, five script directories, 56 data files, two CI dependencies | plan step 4 — stripping preprocessing out of the publication repo |
| `build_cooccurrence.py` | a source that ships the place × person × page fact table again |
| The artist regex | a work register whose `Artist` column covers billedkunst |
| `build_kb_links.py` and its `.xlsm` | the KB link workbook ceasing to be maintained |
| The bounding-box gazetteer | V0.94's places becoming adoptable, which needs a working place crosswalk |
| `ner_page_grounding.py` | nothing — it is waiting on more transcribed diary text, and should stay |
