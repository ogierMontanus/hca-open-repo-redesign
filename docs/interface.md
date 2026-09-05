# The prepared-data interface

The contract between this repository and
[hca-open-repo](https://github.com/ogierMontanus/hca-open-repo). Every file
below is read by a build stage there; nothing else in this repository
crosses the boundary. The authoritative list is `INTERFACE` in
[`scripts/publish.py`](../scripts/publish.py) — this page explains it.

`python scripts/publish.py --into ../hca-open-repo` copies the set into a
publication-repo checkout at the same relative paths, so no path in a build
script had to change when the preprocessing moved out.

## Star-shaped core — from the canonical workbook (stage 1a)

| File | Read by | Carries |
|---|---|---|
| `data/normalized/entities.csv` | every build stage | persons, places and works: id, type, H1–H4 register classification, label, description, see / see-also, derived year and date |
| `data/normalized/diary.csv` | 2, 3a, 3b | one row per transcribed diary entry — volume, page, date, text |
| `data/normalized/references.csv` | 2, 3a, 3b, 4a–4e | the entity × diary-page join that the whole site navigates on |

## Geocoded travel add-on (stage 1b)

| File | Read by | Carries |
|---|---|---|
| `data/normalized/rejser.tsv` | 2, 4c | travel legs with coordinates — the primary geo source for places |
| `data/normalized/rejser_journeys.tsv` | 2 | per-journey metadata |

## Enrichment layers (stages 1c–1h)

| File | Read by | Carries |
|---|---|---|
| `data/normalized/sv14_places_reconciled.csv` | 4c | coordinates matched from the SV14 TEI place-list, for places `rejser.tsv` does not cover |
| `data/normalized/work_languages.csv` | 4a, 4f | probable language per work title, with method and confidence |
| `data/normalized/person_ethnic_descriptors.csv` | 4b, 4f | ethnic/national adjectives per person, with leading/embedded position |
| `data/normalized/person_gender.csv` | 4b | gender facet |
| `data/normalized/person_role.csv` | 4b | role facet |
| `data/normalized/kb_diary_links.csv` | 3a | Det Kgl. Bibliotek facsimile permalink per diary page |
| `data/normalized/steder_verified_categories.csv` | 4c, 4f | human-verified place category and country |
| `data/normalized_v092/timeline.csv` | `build_timeline_index.py` | the Tidstavle events behind the Tidslinje view |

## Register segmentation (human-reviewed, committed as data)

| File | Read by | Carries |
|---|---|---|
| `data/parsed/music_register_parsed.tsv` | 4a | segmented music register — creator overrides for works |
| `data/parsed/non_fiction_parsed.tsv` | 4a | segmented non-fiction register |
| `data/parsed/novels_plays_tales_parsed.tsv` | 4a | segmented novels/plays/tales register |

`data/parsed/personregister_xi_parsed.tsv` is the largest segmentation
product in the repository but is **not** in the interface: the publication
build reads persons from `entities.csv`, not from it. It stays here, with
its tests.

## Curated authority tables the build reads directly

| File | Read by | Carries |
|---|---|---|
| `data/curated/works_wikidata.csv` | 4a, 4b | Wikidata QIDs and hero images for works |
| `data/curated/persons_wikidata.csv` | 4b | Wikidata QIDs for persons (optional; not yet populated) |
| `data/curated/person_entity_types.tsv` | 4b | the entity-type gate that keeps families, firms and the register's dog out of the person facets |
| `data/curated/breve_person_crosswalk.csv` | 4b | Collin-letter ↔ person-register crosswalk |
| `data/curated/ethnic_adjectives_da.csv` | 4b, 4f | the nationality vocabulary |
| `data/curated/nation_place_labels_da.csv` | 4f | nationality key → that nation's own place-register label |
| `data/curated/nation_umbrellas_da.csv` | 4b, 4f | 91 nationality keys clustered into pickable groups |
| `data/curated/steder_country_to_nation_da.csv` | 4f | country → nation bucket |

## Provenance

`publish.py` writes `data/normalized/_source.json` next to the data:

```json
{
  "prepared_by": "HCA-Diary-data-cleaning",
  "prepared_at": "…",
  "sources": {
    "source_xlsx":       {"name": "HCA-Repository V0.82.xlsx", "sha256": "…"},
    "source_rejser_htm": {"name": "Rejser_HCA_X.htm",          "sha256": "…"},
    "source_sv14_xml":   {"name": "SV14_places.xml",           "sha256": "…"}
  }
}
```

The publication repo's `build_web_data.py` reads it into
`web/data/manifest.json`. That is how the built site keeps naming the exact
workbook it descends from, now that it no longer holds the workbook itself.

## Known cross-repo dependency

Three curation scripts here read the publication repo's **built** cards
(`mockup/data/works-extra.js`, `persons-extra.js`, `places-extra.js`):

- `scripts/parsers/parse_person_role.py`
- `scripts/parsers/wikidata_lookup.py`
- `scripts/correspondence/match_collin_{persons,places,works}_to_register.py`

They are occasional, human-driven curation passes, not pipeline stages, and
their outputs are committed — so nothing in the automated flow depends on
them. They resolve the cards via `HCA_MOCKUP_DATA_DIR`, defaulting to a
sibling `../hca-open-repo/mockup/data`. Run them against a built checkout.
