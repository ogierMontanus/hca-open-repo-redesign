# Index maintenance — the update workflow

What to run when a register is updated, for **any** register. One engine, one
descriptor per index.

```
python scripts/index_maintenance/update_index.py person --from <updated.tsv>
python scripts/index_maintenance/update_index.py person --from <updated.tsv> --apply
```

Dry run by default. A run that finds unresolved conflicts refuses to write at
all: a half-assigned index is worse than an unchanged one.

---

## The one rule everything rests on

> **An identifier is carried, never derived.**

A content-derived id changes when a typo is fixed, and takes every citation
with it. This is not a theoretical worry in this project — it is the measured
difference between V0.94's two id schemes:

| | resolves into the live register |
|---|---|
| `OLDWorkID`, carried | **3,590 of 3,590** |
| `OLDLocationID`, content-derived | **0 of 2,433** |

So the engine does exactly three things with an id: keep it on the row it
already belongs to, mint a new one, or retire it in the ledger with a pointer
to its replacement. It never recomputes one.

---

## The seven steps

All in the one command.

| | Step | What it does |
|---|---|---|
| 1 | **Update** | Read the updated source and the index as it currently stands. |
| 2 | **Detect** | Match them, and classify every row: carried, changed, new, merged, split, withdrawn. |
| 3 | **Preserve** | Carry every id that can be carried. This is the default outcome, not the exception. |
| 4 | **Mint** | New ids only for genuinely new entries and for the extra rows a split produced. |
| 5 | **Follow** | Rewrite references that pointed at an id a merge retired. |
| 6 | **Validate** | Duplicate, malformed and missing ids; ledger drift; dangling supersessions. Report what it refused to decide. |
| 7 | **Write** | The index, the ledger, and the review file. |

### How matching works

Four passes, each seeing only what the earlier ones left:

| Pass | Key | Catches |
|---|---|---|
| 0 | **carried id** | The incoming row already names its entry. Makes a re-run idempotent. |
| 1 | **folded label** | Unique on both sides. |
| 2 | **signature** | A renamed entry still cites the same pages. |
| 3 | **singular side** | One-to-many (a split) or many-to-one (a merge). |

Nothing is matched on a similarity score. The tiers that resolved 97.8 % of
the 9,669-row person crosswalk were all exact on one axis or the other, and a
fuzzy tier buys the last percent at the cost of not being able to say why any
given row matched.

A key that is ambiguous on **both** sides identifies nothing. Those rows are
reported, not paired — see "What it refuses to do".

### The signature

Every register here cites diary pages, and that citation set is what survives
a re-spelling. It is the reason split and merge detection can work at all: it
tells "the same person spelled differently" from "a different person with a
similar name".

An index with no signature can still carry ids across a rename, but cannot
tell a split from two unrelated new rows. Say so in its descriptor rather than
pretending otherwise.

---

## Splits — the case this was built for

A split is one entry becoming several. It is the hard case because existing
citations point at the undivided entry and have to keep resolving.

**The continuation keeps the parent's id.** That is the child whose citations
overlap the parent's most — where most existing references still legitimately
land. Its siblings are minted fresh, and the ledger records the relationship
in both directions.

A split normally **renames** at least one half, which is the point of it. So
the label cannot see the relationship, and the signature has to: a split child
cites a subset of what the undivided entry cited.

That subset test needs a tie-break, because busy entries cite supersets of
everyone's pages by coincidence. Tested on the real register, a two-page child
of `Åberg` had **two** previous entries whose citations enclosed it, only one
of them the parent. A split child shares its parent's heading, so the label
breaks the tie; a candidate sharing no label token is not a parent at all.

Where two children have an equal claim, nothing is assigned and the case is
reported. Guessing which half of a split person keeps the citations is exactly
the decision a person should make.

## Merges

Several entries becoming one. The survivor keeps the id it overlaps most; the
others are retired with `superseded_by` pointing at the survivor, and step 5
rewrites references that named them. An old citation still resolves.

---

## The ledger

`data/curated/<index>_id_ledger.csv` is what makes an id permanent rather than
merely current. Every id ever minted stays in it:

| status | meaning |
|---|---|
| `active` | in use on a row today |
| `merged` | retired; `superseded_by` names the survivor |
| `split` | the row it named was split; `note` lists the siblings |
| `withdrawn` | the row is gone and nothing replaced it |

A citation to a retired id is still answerable, which is the entire point.
A retired number is **never reused** — reusing it would silently re-point
every old citation at a different entity.

---

## What it refuses to do

The engine escalates rather than guesses, which is the same rule the rest of
this pipeline follows. It will not decide:

- a **split tie** — two children with equal claim to the parent's citations;
- a **merge tie** — two previous entries with equal claim to be the survivor;
- an **ambiguous split parent** — several candidates share the child's label
  and enclose its citations equally;
- **ambiguous on both sides** — the same key identifies several rows in the
  old index *and* several in the new one. On the live person register with
  ids stripped there are 10 such pairs, identical in both label and citation
  set. They are also near-certain duplicate entries: `Cranach. Barbara` beside
  `Cranach, Barbara`.

Everything it refuses goes to `data/review/<index>_index_update_review.csv`.

---

## Adding an index

Write an `IndexSpec` in [`scripts/index_maintenance/spec.py`](../scripts/index_maintenance/spec.py).
Nothing in `core.py` changes.

```python
PLACE = IndexSpec(
    name="place",
    path=ROOT / "data" / "parsed" / "stedregister_parsed.tsv",
    id_column="00_place_id",
    id_prefix="HCAL",
    label_of=lambda r: r["03_name"],
    signature_of=lambda r: parse_vol_page(r["11_references_parsed"]),
    is_entry=lambda r: r["02_entry_type"] != "krydshenvisning",
    reference_files=((ROOT / "data" / "curated" / "place_id_crosswalk.csv", ",", "place_id"),),
)
```

Then `update_index.py place --from …`. `tests/test_index_maintenance.py`
covers a place-shaped index with different column names, a different prefix
and a different signature separator, to keep the engine honest about not being
person-shaped.

Two things to decide per index before wiring it:

- **Does it have a signature?** Works cite pages, but in this project those
  citations live in `references.csv` rather than in the register row, so
  `signature_of` would have to join before it could answer. Until it does,
  the work index is declared in `spec.py` but not wired.
- **Does it already have identifiers worth keeping?** Works are identified by
  the live `Reg…` ids. Giving an index a second id space before that question
  is settled creates exactly the ambiguity this framework exists to prevent.

---

## Running it on the person register today

```
$ python scripts/index_maintenance/update_index.py person
  carried=9,669  changed=0  minted=0  splits=0  merges=0  withdrawn=0  conflicts=0
  integrity: clean
```

A no-op run against the index itself is the cheapest integrity check there is,
and it is worth running before and after any hand edit.

## Related

| | |
|---|---|
| [`person-index-data-quality.md`](person-index-data-quality.md) | how the register's defects were found and classified |
| [`fused-and-duplicated-rows.md`](fused-and-duplicated-rows.md) | what to run before an update when rows may need splitting or merging |
| [`reports/person-index-input-report.md`](reports/person-index-input-report.md) | the findings, written for the register's maintainers |
| [`architecture.md`](architecture.md) | where this sits in the pipeline |
