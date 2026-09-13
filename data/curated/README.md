# Curated authority tables

**Hand-maintained inputs. Edit these deliberately; they decide what the
pipeline does.** Nothing regenerates them, and no run overwrites them.

Generated review output used to live here too. It now lives in
[`../review/`](../review/README.md), so that this folder contains only files a
person is meant to edit.

| File | Read by | Carries |
|---|---|---|
| `ethnic_adjectives_da.csv` | `enrichment/parse_person_ethnic_descriptors.py`, build 4b/4f | the nationality vocabulary |
| `nation_umbrellas_da.csv` | build 4b/4f | 91 nationality keys clustered into pickable groups |
| `nation_place_labels_da.csv` | build 4f | nationality key → that nation's own place-register label |
| `steder_country_to_nation_da.csv` | build 4f | country → nation bucket |
| `person_entity_types.tsv` | build 4b | the gate that keeps families, firms and the register's dog out of the person facets |
| `breve_person_crosswalk.csv` | build 4b | Collin-letter ↔ person-register crosswalk |
| `works_wikidata.csv` | build 4a/4b | Wikidata QIDs and hero images for works |
| `gender_markers_da.csv` | `enrichment/parse_person_gender.py` | the gendered-term vocabulary |
| `given_name_gender_overrides.csv` | the same | cross-culturally ambiguous given names, resolved by hand |
| `person_role_terms_da.csv` | `curation/parse_person_role.py` | ~185 role terms grouped into buckets |
| `person_emendations.tsv` | `parsers/apply_person_emendations.py` | editorial corrections to individual register entries |

The first seven cross to the publication repository — see
[`../../docs/interface.md`](../../docs/interface.md). The rest are read only
here.

`persons_wikidata.csv` is declared optional in `scripts/publish.py` and is not
yet populated.
