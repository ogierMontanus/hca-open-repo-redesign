# V0.94 — field-structure recommendations

Where the V0.94 workbooks pack more than one fact into one cell, and which
unpackings pay for themselves.

This is deliberately narrow. It does not propose a new schema, new tables, or a
different release; every recommendation below is *one column split, one column
filled, or one vocabulary aligned* inside the shape V0.94 already has. The
release-level assessment — row counts, id crosswalks, reference encoding, fill
rates — is in [`v094-structural-diff.md`](v094-structural-diff.md) and is not
repeated here.

Measured against `data/raw/HCA REPOSITORY V0.94/`: 2,433 locations, 3,590
works, 4,413 diary pages, 36,889 calendar rows.

---

## Summary of recommendations

Ordered by gain per unit of work. "Cost" is the effort to produce the data,
not to consume it.

| # | Registry | Change | Gain | Cost |
|---|---|---|---|---|
| 1 | Location | Split `Location` into name + four typed qualifier columns | 185 rows stop being unsearchable; 119 alternative names become findable | low |
| 2 | Work | Fill `See also` from the `- Se ogsaa:` suffix already inside `WorkTittle` | 71 of 79 cross-references resolve to a `WorkID`; two provisioned columns stop being dead | low |
| 3 | Work | Finish `Artist` / `MuseumEtc` / `City` from the trailing parenthesis | 115 art rows gain a museum; add a `Year` column while there | medium |
| 4 | Diary page | Move `Day` from a space-separated list to a page↔date bridge | the documented join to `Calendar` becomes real; one impossible date surfaces | low |
| 5 | All | Align `Category` / `PlaceType` with the `Kontrollister` sheet in `1-SITES.xlsx` | validation starts catching things | low |
| 6 | All | Remove dead columns and placeholder values | 6 dead columns, 2,973 `(blank)` strings, 2 country values split in two by a trailing space | trivial |
| 7 | Work | Mark the 39 collection headings and the 119 `*` entries as what they are | two categories stop being counted as works | low |

Nothing here requires a new file. Items 1–3 and 7 add columns to sheets that
already exist; item 4 adds one sheet that the workbook's own documentation
already specifies.

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
and says the same for `Belvedere (ved Wien)`'s Austrian neighbour rows.

**A caution on the split.** The parentheses contain OCR damage of the same kind
the page references do: `Amönenhöhe (ved ltzehoe)` for *Itzehoe*,
`Auf der Jugend (ved Hohensehwangau)` for *Hohenschwangau*, `Teulelsbrücke`
for *Teufelsbrücke*. Splitting mechanically will mint these as alternative
names, which makes the OCR errors look like editorial decisions. Run the split,
then review the 119 extracted forms once — it is one screen of text.

---

## 2. Work — `See` and `See also` are empty, and the data for them is in the title

Both columns are provisioned and 0 % filled. Meanwhile 77 titles end in a
literal `- Se ogsaa: …` suffix, and two more carry `, se: …`:

```
Bagtalelsens Skole (Richard Brinsley Sheridan)- Se ogsaa: Die Lästerschule og School for Scandal
Brölloppet på Ulfåsa (Frans Hedberg)- Se ogsaa: Brylluppet paa Ulfsbjerg
Frankfurter Didaskalien, se: Didaskalia
```

Normalising the title — strip the author parenthesis, the leading `*`, the
trailing period — and matching the target against it resolves **71 of 79
targets to an existing `WorkID`**. The remaining eight are near-misses
(`Et Glas Vand` against the stored `Et GlasVand`; `En lille Heks` against
`Die Grille (… efter George Sand: La petite Fadette)`) and are a short manual
list, not a research problem.

That converts an untraversable string into the translation/adaptation network
the register was built to express: the Danish, German and English titles of the
same play currently sit in three unconnected rows.

`Se ogsaa` targets are multi-valued (`… og School for Scandal`), so `See also`
needs the same multi-value convention as the `FK…` columns, or its own bridge.

---

## 3. Work — finish the artist / museum / city columns from the trailing parenthesis

`Artist` is 59 % filled, `MuseumEtc` and `City` 16 %. The unfilled rows are not
unknowable. For 873 of the 918 `BILLEDKUNST` rows the trailing parenthesis is
the `artist, museum, city` triple the columns want, and 680 of those already
carry the commas that separate it:

```
Annibale Carracci, Uffizi, Firenze
Leonello Spada, M. borbonico, Napoli
Salvator Rosa, Doria-P., Rom
```

**115 art rows have that triple in the title and an empty `MuseumEtc`.** Of the
576 that are filled, 563 have the column value appearing verbatim in the title
— good evidence that the same extraction rule produced them, that someone
stopped partway, and that finishing is mechanical rather than editorial.

The same parenthesis carries, in the non-art genres, facts that have no column
at all: publication year (466 titles contain one), original-language title
(267 use `»…«`), and translator or adapter (64 titles contain `efter`, 35
contain `overs.`). **A `Year` column is the cheapest of these and the most
used** — it is what makes the works register sortable against the diary
chronology, which is the one axis the whole repository is organised on.

I would not attempt translator/adapter extraction in the same pass. Those
strings are genuinely irregular —

```
En lille Heks (Ad. Recke og P. Aalborg, bearbejdet efter en tysk
Dramatisering (»Die Grille«) af George Sands Roman »La petite Fadette«)
```

— and a bad extraction there is worse than none.

---

## 4. Diary page — `Day` is a list, so the documented calendar join does not exist

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

One bridge sheet — `PageKey`, `DateID` — makes it real. The same pass makes
three other things go away:

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

## 5. Align the controlled vocabularies with the workbook's own control lists

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

---

## 6. Dead columns, sentinels and stragglers

Cheap, and each one currently costs a reader a moment of doubt about whether
the data is missing or the column is.

| Where | What | Count |
|---|---|---|
| Location | `TypeH1` = `STED-REGISTER` on every row | 2,433 |
| Work | `TypeH1` = `VÆRK-REGISTER` on every row | 3,590 |
| Work | `SourceStatus` = `Needs review` on every row — carries no information | 3,590 |
| Location | `Latitude`, `Longitude` entirely empty | 2,433 |
| Diary page | `AI-genSummary`, `HCACSummary` entirely empty | 4,413 |
| Work | `SubFormH4` holds the string `(blank)` rather than an empty cell | 2,973 |
| Location | `Country` / `Category` hold the string `0` rather than empty | 5 rows |
| Work | `FormH3` values with a trailing space (`Skulptur `, `Faglitteratur `) | 2 values, 517 rows |
| Location | `Country` values with a trailing space (`Slovakiet `, `Polen `) | 2 values |
| Diary page | `KBLinkString` with trailing whitespace | 2 |
| Diary page | `SourceStatus` marked required (`*`) but empty | 4,363 of 4,413 |

The two trailing-space countries are the ones to fix first: `Polen` and
`Polen ` are two different values in every pivot, facet and group-by built on
this file, and nothing on screen distinguishes them.

`Sequense` in the works register runs 1–5,120 across 3,590 rows. If the 1,530
gaps are deleted entries, the column is a register-order key rather than a
sequence, and saying so in the header stops the next reader treating the gaps
as data loss.

---

## 7. Two kinds of row in the works register that are not works

- **39 collection headings.** `FormH3 = "Museer og Samlinger"` holds rows like
  `Amsterdam. Chr. E. van Eeghens Samling` and `Firenze. Aceademia delle helle
  arti - Galleria Pitti`. These are institutions, not works: none has an
  artist, they carry 145 page references between them, and several are
  near-duplicates of each other. They inflate the works count — and they are
  also the natural authority for `MuseumEtc`, which is the argument for keeping
  them, in a column that says what they are. (`Aceademia delle helle arti` is
  OCR of *Accademia delle belle arti*; these rows need the same OCR review
  as §1.)
- **119 rows whose title begins with `*`**, all of them H.C. Andersen poems.
  The asterisk is a register convention with a defined meaning in the printed
  legend, and it is currently a character in the sort key — `*»Aabne Strand…«`
  sorts ahead of everything. Moved to a flag column, the poems sort where a
  reader expects them and the convention becomes queryable.

---

## What I would do first

Items 6 and 4, in that order. The trailing spaces and sentinels are twenty
minutes of work and stop silently splitting groups; the calendar bridge turns
the largest sheet in the release from decoration into data. Then item 1, which
is the one that changes what a reader can find.

Item 2's cross-references and item 3's year extraction are both worth doing,
but each needs a short human pass over the output. They are afternoon jobs,
not five-minute ones.
