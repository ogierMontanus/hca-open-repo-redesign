# Register integrity rules

Guards against two failure modes that are invisible in the published site:
a cross-reference that leads nowhere, and a field that is empty when its
kind of row requires it.

Both are easy to get wrong in the same way — by writing one rule for the
whole corpus. The registers do not share one logic. A cross-reference stub
*must* have an empty description; an ordinary entry with an empty one has
lost something. A music entry may legitimately have no title. A synthesised
container has no source row to point back to. So the rules below are
written per index and per entry kind, and the shared machinery
(`scripts/validation/registers.py`) exists to encode the citation
conventions each index actually uses.

    python scripts/validation/check_indexes.py           # report
    python scripts/validation/check_indexes.py --write   # + review CSV
    python -m pytest tests/test_index_integrity.py       # the guards

## The indexes and their entry kinds

| Index | Source | Entry kinds |
|---|---|---|
| `work` / `person` / `place` | `data/normalized/entities.csv` | ordinary entry, redirect stub (`se:`), soft link (`se ogsaa:`) |
| `music_register`, `non_fiction`, `novels_plays_tales` | `data/parsed/*.tsv` | `standardpost`, `krydshenvisning`, `inferred_container` |
| `personregister_xi` | `data/parsed/personregister_xi_parsed.tsv` | `standardpost`, `krydshenvisning`, `underpost` |

**`se:` and `se ogsaa:` are not the same thing**, and conflating them is the
single easiest mistake here. A bare `se:` makes the row a *stub*: it has no
content of its own and exists only to forward the reader. `se ogsaa:` is a
*soft link printed on a substantive entry* — "Brylluppet paa Ulfsbjerg
(Frans Hedberg)- Se ogsaa: Brölloppet på Ulfåsa" is a real entry that also
points at its Swedish twin. Treating the second as a stub removes 76 real
entries from the resolution index, and because see-also pairs are mutual,
each half then reports the other as blind. That is exactly what happened in
a first draft of these rules: 30 false findings in one sub-register.

## Cross-reference rules

| Rule | Applies to | Says |
|---|---|---|
| `XR1-no-target` | every stub, every index | a cross-reference with nothing to point at is not a cross-reference — it is an entry whose `se:` clause failed to parse |
| `XR2-*` | every stub | the target must resolve to an entry that exists (graded — see below) |
| `XR3-self-reference` | every stub | a row must not point at itself |
| `XR4-chained-redirect` | every stub | a redirect must land on a substantive entry, never on another redirect. The printed register never chains; a stub pointing at a stub means the entry between them was lost |
| `XR5-see-also-*` | soft links | `se ogsaa:` still has to land somewhere |

### Grading, and why it is not a boolean

"Resolves / does not resolve" would put an editorial gap, an OCR misread and
a parser bug in one bucket. They need different people and different fixes,
so the resolver classifies:

| Status | Means | Fix belongs to |
|---|---|---|
| `resolved` | the target exists | — |
| `ocr_variant` | the two agree once the corpus's documented OCR confusion classes (C/G, l/i, 0/9) are collapsed | whoever corrects the misread spelling — the reference and the entry still disagree |
| `near_miss` | one entry is within one or two characters | usually the *target entry's* own label ("Slouet i Poitou" for "Slottet i Poitou") |
| `linewrap` | the target still carries an unrejoined printed-column break ("Berner-Schil- den") | `scripts/parsers/apply_hyphen_linewrap_fixes.py` |
| `overrun` | the target has swallowed the following entry | the splitter |
| `malformed` | the target is not a name or title at all — empty, or a bare column pointer (`Sp. 60.`) | the parser |
| `blind` | nothing exists and nothing is close | an editor: the register points at something it does not contain |

Only the last four are counted as needing a human. `near_miss` and
`ocr_variant` are reported, not escalated.

### The citation conventions the resolver has to know

Each of these was added because leaving it out produced false blind
references, and the count in brackets is how many it recovered:

- **Alternative titles.** The register writes "Tempora mutantur, oder Die
  gestrengen Herren (Karl Blum)" and cross-references it as "Tempora
  mutantur". Both sides of `eller` / `oder` / `ou` / `or` are indexed. [~20]
- **Trailing parentheticals.** A creator, a publication year, a museum —
  peeled off, never part of what a reference cites. [~40]
- **Leading articles.** "Chant des Titans" → "Le Chant des Titans". [~5]
- **Alias parentheticals.** "Ûxküll (Uexküll), Berend" is cited as either
  spelling. [~3]
- **Inverted heads.** The register files under the distinctive word:
  "Brenets, Les", "Geer, de". A reference cites the natural order. [~4]
- **Surname-only heads.** "se: Junot" reaches "Junot, Andoche (1771-1813)".
  Used for resolution only — never for chain detection, where it would make
  every "Andersen, X" stub look like every other one. [~100]
- **Prefix heads.** "Skopas" → "Skopas fra Paros". Floored at six
  characters and a word boundary, so a short word cannot claim an entry.
- **Multi-target fields.** "Bagtalelsens Skole og School for Scandal" names
  two. Tried *only* after the whole field fails, because "og" sits inside a
  title ("Fordum og nu", "Capital og Arbeide") as often as between two, and
  accepted only if every part then resolves.

## Required-value rules

Each is written against one entry kind. The point of the split is that the
right assertion for one kind is the wrong assertion for another.

| Rule | Kind | Says | Why not the obvious rule |
|---|---|---|---|
| `RV-no-identity` | ordinary entry | must have a title **or** an incipit | 30 songs in the music register are known only by their first line and have no title at all. `main_title != ""` would fail on all 30 and still miss a row that lost both |
| `RV-no-content` | person `standardpost` | must have a description **or** page references | either alone is a complete entry — a bare name followed by column numbers is how the register prints many people. Requiring the description fires on 34 good rows; requiring both fires on 218. Requiring *either* finds the 5 that are genuinely truncated |
| `RV-stub-carries-content` | `krydshenvisning` | must **not** have a description, references, creator or note | content lives at the target. Content here means a split cut on the wrong side |
| `RV-entry-redirects` | ordinary entry | must **not** have a `Krydshenvisning_til` | only a stub redirects; an ordinary entry with one was mis-typed and publishes as both a work and a signpost |
| `RV-no-parent` | `underpost` | must have an inherited surname **and** parent linkage | a dash sub-entry ("— Hans Datter") is meaningless alone, and alphabetical sorting has orphaned them before — the dash sorts ahead of every letter |
| `RV-no-provenance` | every row except `inferred_container` | must carry `RegistryTitelID` | the containers the parser synthesises for a `part_of` with no row of its own have nothing to point at, so a blanket rule would fire on all 8 |

## What the tests assert

`tests/test_index_integrity.py` splits the guards deliberately:

- **Hard zero** for rules no legitimate entry can violate — self-reference,
  chained redirect, an ordinary entry that redirects, a targetless stub in
  the work registers, a stub carrying content, a missing identity, missing
  provenance, an orphaned sub-entry.
- **A measured ceiling** for rules whose residual is genuine source damage.
  These cannot be asserted to zero without deleting real findings, so each
  is pinned at today's count with a note on what it is. They are down-only:
  lower one whenever a cleaning pass fixes some, and raise one only after
  checking the new failures against the register itself.

Every rule was fault-injected before being trusted — a defect of its own
kind was written into a copy of the data, and the rule had to fail. That
caught a self-reference guard that could never fire, because stubs are
excluded from the resolution index and a self-redirect therefore fell
through as `blind` instead.

## Current state

41 findings need a human out of roughly 584 cross-reference targets; 31
more are OCR near misses. `--write` puts the full list in
`data/review/index_integrity_review.csv`.

## Known gap: redirects the ingester does not extract

`entities.csv` has a `see` column, but it is populated for **works only** —
117 rows. The other 464 redirects, 388 in the person register and 76 in the
place register, survive only inside the label text
(`"Aage, se: Drewsen, Aage."`). Every consumer that needs them therefore
re-derives them with its own regex: `build_works_extra.py`,
`build_places_extra.py` and `reconcile_steder_categories.py` each carry one.

These rules read the label as well as the column (`registers.redirect_of`),
so all three registers are checked rather than a quarter of them. But the
underlying gap is in the ingester, and populating `see` for persons and
places would let the published site link a redirect instead of printing it
as text. That is a data change with downstream effects, so it is recorded
here rather than made as part of a validation pass.
