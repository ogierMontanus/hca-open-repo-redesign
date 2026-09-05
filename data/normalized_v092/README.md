# V0.92-sourced normalized CSVs

Output of `scripts/normalization/hca_v092_to_csv.py`. The three CSVs mirror the
column shapes that the V0.82 ingester writes to `data/normalized/`, so
downstream builders can be pointed here for the persons/places/diaries slice
that V0.92 covers.

Regenerate with:

```powershell
python scripts\normalization\hca_v092_to_csv.py
```

## Content

| File | Rows | Notes |
|---|---:|---|
| `entities.csv` | 11,352 | 8,917 persons + 2,435 places. Works are absent from V0.92 — keep using `data/normalized/entities.csv` for them. |
| `diary.csv` | 2,176 | Vol VI and VII. Same scope as the V0.82 baseline. |
| `references.csv` | 32,961 | Person + place mentions per diary page (`FactDiaPerPag` + `FactDiaLocPag`). Excludes work references — V0.82's `references.csv` still owns those. |

## ID scheme

The V0.92 outputs use a separate identifier space from V0.82's `Reg…` IDs so
the two CSV sets never collide if joined:

| Entity | V0.92 ID format | Source key |
|---|---|---|
| Person | `P{PerID:05d}` (e.g. `P1000000`) | `DimPer1.PerID` in `DiaryFactDim-PQ` |
| Place | `L{LocID:05d}` (e.g. `L100000`) | `DimLoc1.LocID` in `DiaryFactDim-PQ` |
| Page (in `references.page_id`) | `Pag{vol:02d}{page:04d}` (e.g. `Pag060001`) | `DimDiaPag2` joined to `Vol` + `Page` |

Padding `:05d` is a *minimum*; the source IDs already include several
6–7-digit values, so the prefix `P`/`L` is the durable discriminator, not the
width.

The `person_derived` column on **place** rows is repurposed to carry
`lat,lon` when geocoded (otherwise empty). This keeps the column shape
identical to V0.82 without inventing new columns. Place country and region
are concatenated into `description` separated by ` · `.

## Schema mapping (V0.92 source → CSV)

### `entities.csv` (persons)
| CSV column | V0.92 source |
|---|---|
| `entity_id` | `P{DimPer1.PerID:05d}` |
| `entity_type` | constant `"person"` |
| `category_h1` | constant `"PERSON-REGISTER"` |
| `label` | `DimPer1.RegistryTitle` |
| `description` | `DimPer1.RegistryDescription` |
| `year_derived` | `YearOfBirth–YearOfDeath` (em-dash) when both present, else either |

### `entities.csv` (places)
| CSV column | V0.92 source |
|---|---|
| `entity_id` | `L{DimLoc1.LocID:05d}` |
| `entity_type` | constant `"place"` |
| `category_h1` | constant `"STED-REGISTER"` |
| `label` | `DimLoc1.LocationTitle` |
| `description` | `"Country · Region"` |
| `person_derived` | `"Lat,Lon"` when present |

### `diary.csv`
| CSV column | V0.92 source |
|---|---|
| `vol` | `DimDiaPag2.VolRef` (roman) |
| `page` | `DimDiaPag2.PageRef` |
| `date` | `Date` cell rendered `YYYY-MM-DD`, or `YYYY-MM-XX` fallback |
| `month`, `year` | `DimDiaPag2.Month` / `Year` |
| `heading` | `DimDiaPag2.DiaryDayHeading` |
| `text` | `DimDiaPag2.DiaryTextLines` |

### `references.csv`
| CSV column | V0.92 source |
|---|---|
| `page_id` | derived from `DimDiaPag2.VolRef`+`PageRef` (Pag handle) |
| `entity_id` | `P{PerID:05d}` or `L{LocID:05d}` |
| `entity_label` | joined from `DimPer1.RegistryTitle` / `DimLoc1.LocationTitle` |
| `vol`, `page` | from the same `DimDiaPag2` row |
| `seq` | running 1-based counter per `page_id` |

## Cross-references

`LocationData-PQ-V0.92.xlsx` ships a `Raw.See-Also` sheet (85 rows) that
structures the place cross-references V0.82 buried inside `RegistryTitle`.
The current ingester does not yet load it — its column layout (`Metric`,
`Value`) suggests an unfinished export. Once the format settles, lift the
edges into `entities.see` / `entities.see_also` for place rows. Tracked in
`docs/data-model/source-field-audit.md` and `ai-context/coding_agent_plan.md`
§15.1 (which should be re-scoped to persons once a person-side `Raw.See-Also`
ships).

## Dual-source state today

- The **mockup** (`mockup/*.html`) and the existing build scripts still read
  `data/normalized/` (V0.82) so nothing here disturbs the current site.
- The V0.92 outputs in this folder are intended for:
  1. **Verification** — compare row counts and joins against V0.82.
  2. **Co-occurrence cutover** — `FactDiaLocPerPag` (92,307 rows) replaces
     `scripts/build_mockup/build_cooccurrence.py` once persons/places are
     sourced from V0.92.
  3. **Migration of place cross-references** — `Raw.See-Also` (when usable).

When V0.9x grows a `WorkData-PQ` workbook, drop V0.82 entirely and merge
this folder into `data/normalized/`.

See also: [`docs/data-model/v0.92-structural-diff.md`](../../docs/data-model/v0.92-structural-diff.md).
