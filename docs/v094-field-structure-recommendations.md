# V0.94 — field-structure recommendations

Where the V0.94 workbooks pack more than one fact into one cell, and which
unpackings pay for themselves.

This is deliberately narrow. It does not propose a new schema, new tables, or a
different release; every recommendation below is *one column split, one column
filled, or one vocabulary aligned* inside the shape the release already has. The
release-level assessment — row counts, id crosswalks, reference encoding, fill
rates — is in [`v094-structural-diff.md`](v094-structural-diff.md) and is not
repeated here.

Measured against `data/raw/HCA REPOSITORY V0.94/`: 2,433 locations, 3,590
works, 4,413 diary pages, 36,889 calendar rows. Two of the recommendations an
earlier draft made about the works register have since been answered by
`data/raw/5-WORK-Registry-V0.95.xlsx`; what that release settles, and what it
leaves, is in [the note below](#note--what-v095-already-fixes).

---

## Summary of recommendations

Ordered by gain per unit of work. "Cost" is the effort to produce the data,
not to consume it.

| # | Registry | Change | Gain | Cost |
|---|---|---|---|---|
| 1 | Location | Split `Location` into name + four typed qualifier columns | 185 rows stop being unsearchable; 119 alternative names become findable | low |
| 2 | Diary page | Move `Day` from a space-separated list to a page↔date bridge | the documented join to `Calendar` becomes real; one impossible date surfaces | low |
| 3 | All | Align `Category` / `PlaceType` with the `Kontrollister` sheet in `1-SITES.xlsx` | validation starts catching things | low |
| 4 | All | Remove dead columns and placeholder values | 6 dead columns, 2,973 `(blank)` strings now leaking into a derived key, 5 vocabulary values split in two by whitespace | trivial |
| 5 | Work | Mark the 39 collection headings and the 119 `*` entries as what they are | two categories stop being counted as works | low |
| 6 | Work | Finish `Artist` / `MuseumEtc` / `City` from the trailing parenthesis | 115 art rows gain a museum; the last part of the title still unparsed | medium |

Nothing here requires a new file. Items 1, 5 and 6 add columns to sheets that
already exist; item 2 adds one sheet that the workbook's own documentation
already specifies, and that V0.95 has now built for works.

---

## 1. Location — split the parenthetical

185 of 2,433 `Location` values carry a parenthesis, and it carries at least six
different kinds of fact. Today all six are invisible to search, sorting and
joins alike, because they sit inside the display string.

| Kind | Count | Example | Proposed column |
|---|---|---|---|
| Alternative / other-language form | 119 | `Bozen (Bolzano)`, `Brüssel (Bruxelles)`, `Theiss (Tisza)` | `AltForm` |
| Spatial qualifier | 50 | `Belvedere (ved Weimar)`, `Björkö (i Mälaren)` | `NearPlace` |
| Type or rank | 11 | `Appenzell (Kanton)`, `Slesvig (Hertugdømme)`, `Wien (Floden)` | → existing `Category` |
| Possible identification | 3 | `Adelsberg (Adlersberg?)`, `Baccano (Boccano?)` | `PossibleIdent` + `Uncertain` |
| Modern equivalence | 2 | `Van Diemens Land (=Tasmanien)` | `ModernName` |
| Editorial note | 1 | `Rosendal ved Aarhus (Navnet vist misforstaaet)` | `EditorialNote` |

Three complications, all small and all worth handling in the same pass:

- **Four rows carry two parentheses**, and the two mean different things:
  `Fribourg (Freiburg) (Schweiz)` is alt-form + country;
  `Città vecchia (Malta) (= Mdina)` is country + modern name;
  `Juellinge (Halsted Kloster) (Lollands Nørre Herred)` is alt-form + district.
  A split that keeps only the last parenthesis loses the more informative one.
- **Two rows continue after the closing bracket** —
  `Dyrehaven (ved København), Dyrehavsbakken` — a second name, not a qualifier.
- **22 rows are sort-inverted**: `Blaa Grotte, den`, `Cartuja, La`, `Maus, die`,
  `Escorial, El`. These are index-order strings, not names. A `SortName` /
  `DisplayName` pair costs one column and makes the Blue Grotto findable under
  the name a reader would actually type.

Why this is the highest-value single change: the alternative-form group alone
is 119 places that currently cannot be found under the name most sources use
for them, and `NearPlace` is the only containment signal in the registry
besides `Country` — which for `Belvedere (ved Weimar)` says only `Tyskland`,
and says the same for the Austrian `Belvedere (ved Wien)` two rows down.

**A caution on the split.** The parentheses contain OCR damage of the same kind
the page references do: `Amönenhöhe (ved ltzehoe)` for *Itzehoe*,
`Auf der Jugend (ved Hohensehwangau)` for *Hohenschwangau*, `Teulelsbrücke`
for *Teufelsbrücke*. Splitting mechanically will mint these as alternative
names, which makes the OCR errors look like editorial decisions. Run the split,
then review the 119 extracted forms once — it is one screen of text.

---

## 2. Diary page — `Day` is a list, so the documented calendar join does not exist

`1-SITES.xlsx` specifies step 2 of the load order as *"Kalender — én række pr.
dato, som en side omhandler"*, keyed `CalendarKey` → `PageKey`. The delivered
workbook instead puts the dates in one cell:

```
I-4   1825-XX   1825-09-XX   1825-09-20 1825-09-21 1825-09-22 1825-09-23
```

Pages carry between 0 and 12 dates (1,617 pages carry exactly two; 610 carry
four). The 36,889-row `Calendar` sheet is therefore joinable in principle and
joined to nothing in practice — 8,204 of its rows are referenced, and none of
them by a key a tool can follow.

One bridge sheet — `PageKey`, `DateID` — makes it real, and V0.95 has just
demonstrated the pattern on the works side. The same pass makes three other
things go away:

- `Year` and `Month` are derivable from `Day` and are stored as padded strings
  (`1825-XX`, `1825-09-XX`) that sort as text.
- Those padded strings encode the `DateStatus` concept (`Exact` / `Month only`
  / `Year only`) that `Kontrollister` defines and that no column carries. One
  `DatePrecision` field on the bridge row states it properly.
- **`1825-09-31` does not exist.** It is the only one of the 8,204 referenced
  dates that is absent from the calendar, and it is invisible today precisely
  because the join is not enforced. A malformed separator hides in there too
  (`1825-09-27  1825-09-28`, double space), surviving for the same reason.

---

## 3. Align the controlled vocabularies with the workbook's own control lists

`1-SITES.xlsx` → `Kontrollister` defines `PlaceType` as:

> City/Town · Continent · Historic Site · Island · Lake/Sea · Monastery ·
> Mountain · Mountain Pass · Region · River

`4-LOCATION-Registry.xlsx` → `Category` actually uses:

> City · Property · Region · Point of interest (POI) · River · Mountain ·
> Island · Lake · Country · Sea · Church · Continent · 0

Seven of the thirteen delivered values are not in the list, and four of the ten
listed values are never used. The list validates nothing. Either can be the
authority — but one of them has to go, and the delivered vocabulary is the
better candidate to keep: `Property` (292 rows) and `Point of interest`
(164 rows) are doing real work, while `Monastery` and `Mountain Pass` are doing
none.

Two smaller instances of the same drift:

- `Kontrollister.Weekday` is capitalised (`Mandag`); `Calendar.DayText` is not
  (`mandag`). A `Weekday` dropdown validated against that list would reject
  every row in the calendar.
- `Country` mixes countries with continents — `Afrika`, `Asien`, `Europa`,
  `Nordamerika`, `Sydamerika`, `Verden`, 27 rows between them — and contains
  one `By`. Either those rows need a different reading, or the column should
  take the name the JSON mapping already gives it: `CountryArea`. The mapping
  sheet and the registry disagree today, and the mapping sheet is right.

An unvalidated vocabulary drifts further with each release rather than
settling. `FormH3` in the works register carried two whitespace-damaged values
in V0.94 (`Skulptur `, `Faglitteratur `); in V0.95 it carries three, the new one
being `Skuespil\n` with a trailing newline. Eighteen genres are now spelled
twenty-one ways, and `Skuespil` is two of them.

---

## 4. Dead columns, sentinels and stragglers

Cheap, and each one currently costs a reader a moment of doubt about whether
the data is missing or the column is. Counts below are V0.94; the works figures
are unchanged in V0.95 unless noted.

| Where | What | Count |
|---|---|---|
| Location | `TypeH1` = `STED-REGISTER` on every row | 2,433 |
| Work | `TypeH1` = `VÆRK-REGISTER` on every row | 3,590 |
| Work | `SourceStatus` = `Needs review` on every row — carries no information | 3,590 |
| Location | `Latitude`, `Longitude` entirely empty | 2,433 |
| Diary page | `AI-genSummary`, `HCACSummary` entirely empty | 4,413 |
| Work | `SubFormH4` holds the string `(blank)` rather than an empty cell | 2,973 |
| Location | `Country` / `Category` hold the string `0` rather than empty | 5 rows |
| Work | `FormH3` values differing only in whitespace | 2 values in V0.94, 3 in V0.95 |
| Location | `Country` values with a trailing space (`Slovakiet `, `Polen `) | 2 values |
| Diary page | `KBLinkString` with trailing whitespace | 2 |
| Diary page | `SourceStatus` marked required (`*`) but empty | 4,363 of 4,413 |

The two trailing-space countries are the ones to fix first: `Polen` and
`Polen ` are two different values in every pivot, facet and group-by built on
this file, and nothing on screen distinguishes them.

**The `(blank)` sentinel has now escaped its cell.** V0.95's new
`WorkTittlePath` column concatenates the genre hierarchy into a single path
key, and 2,973 of 3,784 paths read

```
VÆRK-REGISTER / H. C. ANDERSEN / Samlede og blandede Skrifter / (blank) / Gesammelte Werke (1847-72)
```

The same release's `WorkRegistry` sheet builds `RegistryTitelPath` from the
same hierarchy and gets it right — 0 of 11,195 contain the sentinel. Two
builders of the same key disagree, which is the cheapest possible argument for
deleting the sentinel at source rather than teaching each consumer about it.

`Sequense` in the works register runs 1–5,120 across 3,590 rows in V0.94 and
1–40,193 across 3,784 in V0.95. If the gaps are deleted entries, the column is
a register-order key rather than a sequence, and saying so in the header stops
the next reader treating the gaps as data loss.

---

## 5. Two kinds of row in the works register that are not works

Both survive unchanged into V0.95.

- **39 collection headings.** `FormH3 = "Museer og Samlinger"` holds rows like
  `Amsterdam. Chr. E. van Eeghens Samling` and `Firenze. Aceademia delle helle
  arti - Galleria Pitti`. These are institutions, not works: none has an
  artist, they carry 145 page references between them, and several are
  near-duplicates of each other. They inflate the works count — and they are
  also the natural authority for `MuseumEtc`, which is the argument for keeping
  them, in a column that says what they are. The register itself says as much:
  V0.95's `PagkFormNote` records the printed legend *"De forkortede
  Museumsnavne er oplyst i foranstaaende Museumsregister."* (`Aceademia delle
  helle arti` is OCR of *Accademia delle belle arti*; these rows need the same
  OCR review as §1.)
- **119 rows whose title begins with `*`**, all of them H.C. Andersen poems.
  V0.95 supplies the legend that V0.94 left to inference — `PagkTitelNote`
  reads *"\* betegner at Digtets Tekst meddeles."*, i.e. the diary gives the
  poem's text. That is a genuine research facet and it is currently a character
  in the sort key: `*»Aabne Strand…«` sorts ahead of everything. Now that the
  meaning is recorded in the data, moving it to a boolean column is a rename,
  not a decision.

---

## 6. Work — finish the artist / museum / city columns from the trailing parenthesis

The one recommendation about the works register that V0.95 does not act on. A
cell-by-cell diff of the 3,590 carried-over rows shows **zero changes** in
`Artist`, `MuseumEtc` and `City`: still 2,113 / 576 / 574 filled, 59 % / 16 % /
16 %. The new `WorkRegistry` sheet provisions an `ArtistDerived` column and
leaves it 0 % filled.

The unfilled rows are not unknowable. For 873 of the 918 `BILLEDKUNST` rows the
trailing parenthesis is the `artist, museum, city` triple the columns want, and
680 of those already carry the commas that separate it:

```
Annibale Carracci, Uffizi, Firenze
Leonello Spada, M. borbonico, Napoli
Salvator Rosa, Doria-P., Rom
```

**115 art rows have that triple in the title and an empty `MuseumEtc`.** Of the
576 that are filled, 563 have the column value appearing verbatim in the title
— good evidence that the same extraction rule produced them, that someone
stopped partway, and that finishing is mechanical rather than editorial.

Two facts in the same parenthesis still have no column anywhere: the
original-language title (267 titles use `»…«`) and the translator or adapter
(64 titles contain `efter`, 35 contain `overs.`). I would take the first and
leave the second: those strings are genuinely irregular —

```
En lille Heks (Ad. Recke og P. Aalborg, bearbejdet efter en tysk
Dramatisering (»Die Grille«) af George Sands Roman »La petite Fadette«)
```

— and a bad extraction there is worse than none.

---

## Note — what V0.95 already fixes

`data/raw/5-WORK-Registry-V0.95.xlsx` answers two of this document's earlier
recommendations for the works register and most of a third from
[`v094-structural-diff.md`](v094-structural-diff.md). It carries the 3,590
V0.94 work rows forward byte-identically, adds 194, and adds a second sheet,
`WorkRegistry`, of 11,195 rows — one per work↔page reference.

**Cross-references: solved.** `See` is filled on 118 rows, `See also` on 76, and
a new `FKWorkID` column resolves **193 of 193 targets to a real `WorkID`** —
better than the 71-of-79 a title-suffix parse would have managed. The 118 `see`
entries are the printed register's own cross-reference headings
(`Aamanden, se: Klokkedybet`) and are correctly modelled as rows of their own.

One thing to tidy, though: the 76 `see also` links hang off 194 new stub rows
(`WOR200000`–) that carry no page references and no `OLDWorkID`, and 75 of them
duplicate the title of an existing work row. The original rows still carry the
unparsed `- Se ogsaa:` suffix in `WorkTittle` with `See also` empty — so
`Bagtalelsens Skole` (`WOR055700`) does not know about its own cross-reference;
its shadow (`WOR206050`) does. Copying `FKWorkID` onto the 76 originals and
stripping the suffix would finish the job. Titles now also carry embedded
newlines (137 rows, `Aamanden, \nse: Klokkedybet`), which belong in §4's list.

**Publication year: solved.** `YearDerived` covers 470 distinct works across
1,455 reference rows — against the 466 V0.94 titles that had a year buried in
them, so essentially complete. `DateDerived` adds an exact date for 228 works,
which V0.94 had nowhere at all. The six `WorkComposition…` / `WorkFirstPublication…`
/ `WorkFirstPerformance…` columns are provisioned and entirely empty; §4's
warning about empty columns applies to them.

**Artist, museum and city: not addressed.** See §6.

Three further gains worth recording, none of which this document asked for:

- **References are a fact table now**, not a space-separated list — `VolRef`
  and `PageRef` split, one row per reference, a KB link per row. This is the
  works half of what §2 still asks for on the diary-page side.
- **The OCR-damaged page keys are repaired.** `VIII           O-226-27` is now
  `VIII-226` and `VIII-227`; `VI ,-119,` is `VI-119`; `III  (Noten)-229` is
  `III-229`; `V l-l` is `V-1`. Abbreviated ranges are expanded rather than
  right-split. `v094-structural-diff.md` counted 224 unreadable keys across 37
  rows; what remains is 72 rows for a single work
  (`Franske - Fantaisies danoises …`) whose `PageKeys` read `IV-` — a volume
  with no page.
- **Order of mention is back.** `WorkSeqNo` is filled on all 11,195 rows.
  `v094-structural-diff.md` recorded that V0.94 could not express the live
  `seq` and that it "cannot be recovered from it — only re-invented"; V0.95
  carries it. The printed register's own apparatus comes with it: `ColumnNo`
  (499 rows), `PageRefStyle`, and the three `Pagk…Note` columns that record the
  legends quoted in §5.

Two small defects in the new sheet, for whoever ingests it: `PageRef` is mixed-
typed (11,006 numeric cells, 117 text), and `PageRefStyle` is filled on 35 of
11,195 rows — either a column that was started and abandoned, or one whose
blank means `Normal` and should say so.

---

## What I would do first

Items 4 and 2, in that order. The whitespace-split vocabulary values and the
sentinels are twenty minutes of work and stop silently splitting groups — and
the `(blank)` leak into `WorkTittlePath` shows the cost compounding rather than
holding steady. The calendar bridge then turns the largest sheet in the release
from decoration into data, and V0.95 has already shown, on the works side, that
the team can build exactly that.

Then item 1, which is the one that changes what a reader can find.

Item 6 needs a short human pass over its output, so it is an afternoon job
rather than a five-minute one — but V0.95's `ArtistDerived` column suggests it
is already on someone's list.
