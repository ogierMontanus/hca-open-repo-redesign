> **Archived copy — not current.** Verbatim from `docs/data-model/october-pipeline.md` in
> [hca-open-repo](https://github.com/ogierMontanus/hca-open-repo), kept for its
> reasoning. An unratified proposal. Its format argument — why CSV and JSON, not SQLite or Parquet — still decides things here.
>
> Relative links below point at files in *that* repository and do not resolve
> here. See [`README.md`](README.md) for why these are kept.

# October mockup — automated CSV + JSON pipeline

A concrete, end-to-end proposal for the October deliverable: an **automated conversion pipeline** that takes the Excel workbook (which embeds the Power Pivot star schema) and produces a deployable static website mockup, with **CSV and JSON as the only data formats**.

This document records the proposal — it is not yet ratified.

## Why CSV + JSON (and nothing else)

Per the constraint "only include SQL/SQLite or other formats if they offer very big gains", the proposal deliberately does **not** introduce SQLite, DuckDB, or Parquet. The reasoning:

| Format | Considered for | Verdict |
|---|---|---|
| **CSV** | Star-schema export from Excel (dimensions + facts) | **Use.** Native Power Query / Power Pivot output. Diff-friendly in git. Re-opens in Excel for collaborators. Already the language of `scripts/normalization/hca_xlsx_to_csv.py`. |
| **JSON** | Web-consumable view artifacts | **Use.** Native to `fetch()`. No parsing dependency. Maps directly to JS data structures. Carries denormalised "view" shapes the UI needs. |
| **SQLite / DuckDB** | Single-file SQL engine in browser | **Skip.** At Places scale (~2.5k rows) a JSON array + `Array.filter` is fast enough; the Power Pivot model already provides the SQL-shaped analysis surface upstream. SQLite would duplicate logic without unlocking new mockup behaviour. |
| **Parquet** | Compact columnar data exchange | **Skip.** Compression / scan-speed advantages are negligible below ~100k rows. Inspectable only via tooling, so collaborators lose the "double-click to read" affordance. |

The door stays open: every intermediate CSV is a clean dimension or fact table, so a future migration to SQLite, Postgres, or Parquet is a `LOAD DATA INFILE` away.

## Pipeline overview

```
┌─────────────────────────────────────────────────────────────┐
│  data/raw/HCA-Repository V*.xlsx  (canonical source)        │
│  └── Power Query + Power Pivot star schema embedded         │
│  data/raw/Rejser_HCA_X.htm        (geocoded add-on,         │
│                                    sourced from hcax.dk)    │
│  data/raw/sorens/*.xlsx | *.csv   (optional, when provided) │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │ [1a] scripts/normalization/  │
         │      hca_xlsx_to_csv.py      │   (exists; extend for star tables)
         │                              │
         │  xlsx → dimension + fact CSV │
         └──────────────────────────────┘
         ┌──────────────────────────────┐
         │ [1b] scripts/build_web/      │
         │      parse_rejser_htm.py     │   (new)
         │                              │
         │  Rejser_HCA_X.htm → TSV      │
         │  (table only; jpg ignored)   │
         └──────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │  data/normalized/             │
         │   entities.csv                │
         │   diary.csv                   │
         │   references.csv              │
         │   rejser.tsv          (add-on)│
         │   rejser_journeys.tsv (add-on)│
         └──────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │ [2] scripts/build_web/       │   (new)
         │     build_web_data.py        │
         │                              │
         │  CSV → denormalised JSON     │
         │  per Places-demo query       │
         └──────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │  web/data/                   │
         │   manifest.json              │
         │   places.json   (lat/lon for │
         │                  matched 377)│
         │   places_visits.json         │
         │   places_works.json          │
         │   places_timeline.json       │
         │   rejser.json   (geocoded    │
         │                  add-on,     │
         │                  separate)   │
         └──────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────┐
         │ [3] web/  — static site      │   (new)
         │     HTML + vanilla JS        │
         │     Leaflet for map          │
         │     fetch() → render         │
         └──────────────────────────────┘
                         │
                         ▼
              GitHub Pages (or any static host)
```

Three stages, two file formats. No server, no database, no build-time JS toolchain required beyond what the chosen mapping library wants.

## Stage 1 — Excel → CSV (star tables)

**Builds on:** `scripts/normalization/hca_xlsx_to_csv.py` (already emits `entities.csv`, `diary.csv`, `references.csv`).

**Extension:** split `entities.csv` along the WEMI sub-type axis and emit explicit star-schema files in `data/normalized/`:

- `dim_place.csv` — `STED-REGISTER` rows + Sørens-Sted overlay (when present)
- `dim_calendar.csv` — Calendar1800 → ISO date, year, month, day, weekday, season
- `dim_diary.csv` — Diary page / section identity
- `dim_person.csv` — deferred for October but emitted as scaffolding
- `dim_work.csv` — deferred for October but emitted as scaffolding
- `fact_reference.csv` — (diary_id, entity_id, entity_type, page, section)
- `fact_place_work.csv` — M-M edges from Sørens 2. register (when present)

**Versioning:** the existing `resolve_ground_truth_xlsx()` rule (highest `V*` wins) picks up new workbook versions automatically. Stage 1 records the source filename and a SHA-256 of the workbook into `data/normalized/_source.json` for downstream traceability.

**Sørens-register handling:** Stage 1 looks for optional inputs under `raw/sorens/`. If the files are absent, the corresponding columns / fact rows are omitted and a `warnings` array in `_source.json` notes which overlays were skipped. The pipeline never fails on missing Sørens data.

## Stage 2 — CSV → web JSON

**New script:** `scripts/build_web/build_web_data.py`.

**Inputs:** `data/normalized/*.csv`.

**Outputs:** `web/data/*.json` — one file per demo query plus a manifest.

**Per-query shapes (proposed, to be confirmed against the actual demo queries):**

- `manifest.json` — `{ "source_xlsx": "...V0.82.xlsx", "source_sha256": "...", "built_at": "...", "warnings": [...] }`
- `places.json` — full Places dimension, denormalised with coords (when available) and Sørens overlay attributes. Array of `{ id, name, lat, lon, type, sorens_notes, ... }`.
- `places_visits.json` — per Place, the diary entries that reference it: `{ place_id, visits: [{ diary_id, iso_date, page, section, snippet }, ...] }`.
- `places_works.json` — Work ↔ Place edges: `{ place_id, works: [{ work_id, title, type }, ...] }`.
- `places_timeline.json` — facet aggregation: `{ place_id, by_year: { "1840": 3, "1841": 7, ... } }`.

These are **denormalised view shapes** — the relational joins are pre-computed in Stage 2 so the browser does no join work. This keeps the front-end thin (the "thin layer between data and presentation" constraint) and makes each JSON file independently usable.

**Implementation:** pure-Python stdlib + `csv` module is enough at this scale; pandas optional. Aim for the script to be readable end-to-end in one screen.

## Stage 3 — Static web mockup

**New folder:** `web/`.

**Stack:** intentionally minimal.

- `web/index.html` — semantic HTML, no framework required.
- `web/app.js` — vanilla ES modules: `fetch('data/places.json')`, render list / map / timeline.
- `web/styles.css` — plain CSS.
- **Map:** Leaflet (no API key, OpenStreetMap tiles) — the right minimum for the Places demo.
- **Timeline:** vanilla CSS bars driven by `places_timeline.json`; upgrade to a small lib only if needed.

If a framework is later wanted (Astro, SvelteKit, etc.), it can sit on top of the same `web/data/*.json` artifacts without changing Stages 1–2.

## Automation

A single GitHub Action makes the pipeline self-running:

```
.github/workflows/build-mockup.yml

on:
  push:
    paths:
      - 'raw/**'
      - 'scripts/normalization/**'
      - 'scripts/build_web/**'
      - 'web/**'
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - checkout
      - setup-python 3.12
      - pip install -r scripts/parsers/requirements.txt
      - python scripts/normalization/hca_xlsx_to_csv.py
      - python scripts/build_web/build_web_data.py
      - upload web/ as Pages artifact
      - deploy to Pages
```

The trigger is "a new workbook lands in `raw/`": the Action re-extracts CSVs, rebuilds JSON, and redeploys the static site. No manual step between Excel and web.

## Concrete file layout (proposed additions only)

```
scripts/
  build_web/
    build_web_data.py        ← new
    README.md                ← new
web/
  index.html                 ← new
  app.js                     ← new
  styles.css                 ← new
  data/                      ← built artifact, .gitignored or committed snapshot
    manifest.json
    places.json
    places_visits.json
    places_works.json
    places_timeline.json
.github/workflows/
  build-mockup.yml           ← new
docs/data-model/
  october-pipeline.md        ← this file
```

Stage 1's CSVs land in the existing `data/normalized/` directory — no new top-level folder for them.

## What it costs to skip SQLite (and what it would unlock)

Skipping SQLite costs:

- No ad-hoc query interface inside the mockup (users can only see what Stage 2 pre-baked).
- Slightly larger JSON payloads than equivalent SQL queries would return on-demand.

For an October mockup demoing 3–5 fixed Places queries, neither cost is real. If the mockup later wants user-driven exploration over the full star schema, swapping in DuckDB-WASM (option 2 from `star-schema.md`) means *adding* a query layer over the same CSVs — no rework of Stage 1.

## Geocoded add-on — hcax.dk Rejser table

The October scope is focused on Q1, Q2, and Q4 from the candidate query list, with Q4 (map view) limited to places that can be geocoded **without an open-ended geocoding pass**. The supplementary HTML table at `data/raw/Rejser_HCA_X.htm` (scraped from rejser.hcax.dk) carries lat/lon for every leg of every Andersen journey.

Stage 1b (`scripts/build_web/parse_rejser_htm.py`) converts the table to TSV — `rejser.tsv` (one row per leg, 10 columns including separate Latitude/Longitude) and `rejser_journeys.tsv` (one row per journey, with Danish dates and descriptions). Embedded `<img>` rejsekort `.jpg` references are ignored.

Stage 2 matches Place labels from the Excel workbook against `Destination_DA` from the Rejser TSV (case-insensitive exact match). Matched places get `lat`, `lon`, `geocoded: true`, `destination_en`, `journey_count`, and `leg_count` injected into `places.json`. Unmatched places carry `geocoded: false` with null coordinates.

The Rejser-derived data is also emitted as its own artifact, `web/data/rejser.json`, keeping it **distinct from the Excel-derived JSON** so provenance is never blurred.

Current match rate against V0.82: **377 of 2,508 places** carry coordinates. The remaining majority is intentionally not geocoded for the October demo.

Front-end behaviour (`web/app.js`):

- Geocoded places sort to the top of the list and render with an accent colour, a blue "●" pin glyph, and a "Nj" journey-count badge.
- The detail panel shows a "Journeys passing through this place" section with arrival/departure dates, transport methods (emojis preserved), and journey context (description, countries) for every matched place.
- The Leaflet map renders a real marker for geocoded places; for non-matched places the map zooms out and a muted note explains the place isn't in the Rejser table.
- A "Geocoded only" toggle in the left rail filters the list to the 377 places that have map data.

## Integration direction — lean cross-entity model

Resolution from the 2026-06-02 planning session (second round):

> Focus on integrating the different named entities. For place names,
> focus on the places contained in the index of words — e.g., place of
> publication for paintings and sculptures, gallery location, person's
> place of birth, death, or professional activity. Keep the basic data
> lean and limit the number of cross-connections between entities; add
> aggregate categories per entity so people can do broader searches.

This translates into two design rules:

### Rule 1 — no new M-N fact tables between entities

The cross-references that link Persons ↔ Works ↔ Places already exist as
parenthetical fragments inside the index labels themselves:

- Work labels carry the publication place: `(Napoli 1846)`,
  `(Hamburg 1846)`, `(Leipzig 5.7.1841)`, `(Utrecht 1869)`,
  `(New York 1869)`.
- Person labels carry life dates: `(1807–1883)`, `(1818–1880)`,
  `(død 1181)`, `(525–456 f. Chr.)`.
- Where birth / death / activity place is recorded in the source, it
  also sits in the label or description string, not in a separate
  column.

Surface these as **lazily-parsed derived fields** at display time, not
as new fact tables. A Work's detail panel runs a small regex over its
label to expose `publication_place_label` + `publication_year`; that
label string is then matched (case-insensitive) against the Places
dimension to resolve to a Place id and inherit its coordinates +
country. The reverse view ("Works published in Hamburg") is a cheap
string-equality scan over the 3,717-row Work register — no
pre-computed index needed.

### Rule 2 — every entity gets aggregate dimensions

Each entity type carries a small set of broad categorical columns so
the mockup can answer "show me everything from category X":

| Entity | Aggregate dimensions | Source |
|---|---|---|
| **Place** | `country_da` / `country_en` | Lat/lon → bounding-box gazetteer (377 geocoded places via Rejser add-on; see below) |
| **Work** | `language`, `form_h3` (genre) | `form_h3` already in `entities.csv`; language via existing `scripts/parsers/add_language_column.py` |
| **Person** | `birth_year`, `death_year`, era band | Regex on label parens: `(YYYY–YYYY)`, `(død YYYY)`, `(ca. YYYY–YYYY)`, `(YYYY–YYYY f. Chr.)` |

The aggregates are the search facets the user described:
- "All places in Italy"
- "All works in French"
- "All persons born after 1800"

### Currently implemented

- **Place → country** is now in `places.json`. The 377 geocoded places
  are tagged via a 33-country European bounding-box gazetteer inlined
  in `scripts/build_web/build_web_data.py`. Distribution against V0.82:
  Tyskland 82, Schweiz 49, Frankrig 45, Italien 38, Danmark 36, Østrig
  26, Norge 26, Tjekkiet 16, Storbritannien 14, Spanien 14, Holland 11,
  + 12 smaller countries. Coverage: 377/377 of geocoded places. The UI
  carries a `country-filter` dropdown populated from
  `manifest.places_by_country`.

### Not yet implemented (proposed next, awaiting confirmation)

- **Work → language + form aggregates.** Extend Stage 1 to materialise a
  per-Work `language` column (re-use `scripts/parsers/add_language_column.py`)
  and emit `web/data/works.json` containing `{id, label, form_h3, language,
  publication_place_label, publication_year}`. Mockup adds a Works tab
  with language + form filters.
- **Person → life-dates aggregate.** Stage 2 adds a `parse_person_label`
  step extracting `birth_year`, `death_year` from the parens patterns
  catalogued in `wemi-and-relations.md`; emit `web/data/persons.json`
  with `{id, label, birth_year, death_year, era}`.
- **Lazy cross-refs.** When a Work detail panel is opened, run a regex
  over `label` to surface `publication_place_label`; resolve that string
  against `places.json` for a "show on map" link. Same pattern for
  Person → place-of-birth/death once those are parsed.

The intent is that the Places, Works, and Persons JSON files stay
**flat and small**, with no cross-entity arrays. Connectivity happens
at display time via cheap string lookups.

## Open items before implementation

1. **The remaining demo queries** — Q1 and Q2 are wired against the existing data; Q4 is now answered for the 377-place subset. Q3 and Q5 (works-co-occurrence using Sørens 2. register; Place typology from Sørens-Sted) remain placeholders.
2. **Sørens registers** — schema and arrival date still pending Søren's clarification.
3. **Hosting** — GitHub Pages is the default assumption; confirm or pick an alternative static host before wiring the Action's deploy step.
