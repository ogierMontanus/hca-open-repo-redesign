# Person-register segmentation

The printed *Personregister* (bind XI), via OCR, into one row per person.
This is the largest editorial effort in the project and the only part of the
pipeline that is not reproducible from its inputs.

| | |
|---|---|
| `parse_personregister_xi.py` | reads the OCR PDF, emits `data/parsed/personregister_xi_parsed.tsv` |
| `apply_person_emendations.py` | **live, despite the `apply_` prefix.** It never writes the master file — it validates the emendations against it and emits the merged view. Guarded by `tests/test_person_emendations.py` |
| `archive/` | 30 one-shot passes that were applied to the master file, in order, during a human-reviewed session. **They cannot be re-run.** |

## The output is not reproducible from the parser

The migration plan proposed extracting the chain's decisions into a table and
replaying them, with the acceptance test "prove it reproduces the committed
file exactly from the parser output". **That test cannot be met, and the
measurement that shows why is worth keeping.**

A fresh parse was taken and compared with the committed file:

| | |
|---|---:|
| fresh parse | 9,338 rows |
| committed | 10,079 rows |
| entries matching on (surname, given names) | 7,741 |
| in the fresh parse only | 1,135 |
| in the committed file only | 2,101 |
| shared entries differing in a substantive column | 920 |

The chain did not apply a tidy set of edits to a stable base. It restructured:
958 people were imported from the independent transcription, 479 duplicates
were removed across two passes, entries were split and merged, and 901
descriptions were re-segmented. 2,101 committed entries have no counterpart in
a fresh parse by name at all.

Replaying that would need each pass's *inputs* as they stood when it ran. Those
inputs were review files in `data/review/`, and later passes overwrote
earlier ones. The information is gone. What survives is the outcome — the
committed TSV — and the reasoning, in
[`../../docs/person-register-segmentation.md`](../../docs/person-register-segmentation.md).

So the file is **committed data, not build output**, in the strongest sense in
this repository: re-running the parser does not approximate it, it replaces it
with something substantially different and worse.

## `01_entry_id` is a row number, not an identifier

Found by the same comparison, and more consequential than the above. **The
project already knew** — `apply_person_emendations.py`'s docstring gives
"`01_entry_id` renumbers" as one reason an emendation is layered over the
register rather than edited into it. What is new here is the measurement of
how far it renumbers, and the consequence for the migration:

```
                  fresh parse        committed
PerXI00001        Åberg              Abbott
PerXI05000        Licht, Carl        Jacobsen, Peder
```

The ids are assigned positionally at parse time. Because the chain inserted
741 rows, every id after the first insertion denotes a different person than
it did before. Anything that cites a `PerXI…` id is citing a row position.

This blocks the person adoption in the migration plan's §I.10, which needs a
`PerXI… ↔ Reg…` crosswalk: there is nothing stable on this side to crosswalk
*to*.

A content key of (surname, given names, birth year, death year, page
references, description) is unique for **10,077 of the 10,079 rows**, so
stable ids can be seeded from content and then carried as data — assigned
once, never re-derived, which is what the architecture requires of an
identifier. The two collisions are genuine exact-duplicate rows
("Bretton, Florence, Baronesse" and "Melchior, Emil", both without page
references) and want deduplicating before ids are minted.

That work belongs to §I.10a and has not been done.

## What the archive is for

Audit. Each pass records a decision a person approved, and its paired
`suggest_*` output in `data/review/` records what they were shown. Read them
to answer "why is this entry like this"; do not run them.

They are kept rather than deleted because they are the provenance of roughly
1,700 editorial decisions on scholarly data, and because
[`../../docs/person-register-segmentation.md`](../../docs/person-register-segmentation.md)
names the order they were applied in, which only makes sense with the scripts
present.
