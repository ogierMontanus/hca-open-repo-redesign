# Person-register XI — segmentation record

Migrated from `HANDOVER.md` in the publication repository, where this work
was done before the cleaning pipeline moved here. Paths named below are
relative to this repository now: `scripts/parsers/`, `data/parsed/`,
`data/curated/` and `tests/` all carry the same contents they did there.

---

# Håndovering — personregister XI segmentering (2026-09-02)

Session-status ved afslutning: alt commit'et (`2c6dfde wrangling`), working
tree ren, 13/13 tests grønne. `data/parsed/personregister_xi_parsed.tsv`:
**10.136 rækker** (9.725 standardposter, 394 krydshenvisninger, 17 underposter).

## Reelt overskud/underskud lige nu

Rå rækketal er misvisende (de to kilder tæller krydshenvisninger forskelligt).
Sammenlignet på **personposter** mod `data/raw/Personer _ HCA_tsv.txt`
(uafhængig præ-segmenteret transskription, 10.228 rækker, 699 er
krydshenvisninger → 9.529 personer):

| | Antal |
|---|---|
| Vores personposter | 9.742 |
| Referencens personer | 9.529 |
| **Rå person-overskud** | **+213** |
| — heraf blot stavevariant (samme sidehenvisnings-signatur) | 330 af 344 "kun hos os" |
| — heraf blot stavevariant (samme sidehenvisnings-signatur) | 170 af 171 "kun i ref" |
| **Reelt nettooverskud** | **~10 poster** (11 reelt ukendte hos os − 1 reelt ukendt i ref) |

Konklusion: de to kilder er nu praktisk talt dækningslige på personniveau.
Målemetoden (se nedenfor) er selv skrøbelig — næste session bør genbekræfte
tallet efter enhver ny batch-ændring.

**Målemetode** (genbrugt gennem hele sessionen, ingen færdig scriptfil):
1. Normalisér navn: NFKD-strip diakritika, fjern ALLE årstalsparenteser
   (ikke kun den sidste — det var en tidlig bug), fold tegnsætning væk.
2. `core(navn)`-sæt-differencer mellem vores personposter og referencens.
3. For "kun hos os"/"kun i ref": slå op om den anden sides
   sidehenvisnings-signatur (fuldt ekspanderet `VOL:PAGE`-sæt) matcher en
   post på den modsatte side — matcher den, er det samme person med
   forskellig stavemåde, ikke et reelt overskud.

## Hvad der er gjort i denne session (kronologisk)

1. **Beskrivelses-fusion** (`suggest_description_fusion_splits.py` →
   `apply_description_fusion_splits.py`): 46 rækker splittet hvor
   `09_description` skjulte en ny person efter romertal+arabertal-henvisning
   eller tankestreg+efternavn-forbogstav.
2. **Embedded name+year** (`suggest_embedded_name_splits.py` →
   `apply_embedded_name_splits.py`): 132 rækker splittet hvor et
   "Efternavn, Fornavn (år)," var begravet midt i en lang beskrivelse
   (Melchior-familien, Hauch, Wulff, Collin).
3. **Ekstern reference-harvest** (`harvest_segmentation_from_tsv.py` →
   `apply_tsv_harvest_splits.py`): opdagede at
   `data/raw/Personer _ HCA_tsv.txt` er en uafhængig, allerede
   person-pr-række transskription (10.228 rækker). 70 fusionerede rækker →
   82 nye poster, med navn/år/beskrivelse/sidehenvisning hentet direkte
   derfra.
4. **Import af 958 manglende personer**
   (`import_reference_missing_candidates.py`): personer i referencen uden
   modstykke hos os, indsat på alfabetisk plads UDEN at omsortere hele
   filen (registret selv afviger fra ren sortering ~600 steder — partikler,
   tilnavne). Én ortografisk rettelse anvendt (Û→Ü i Üxküll).
5. **Navnediff-gennemsyn** (bruger-godkendt liste): 132 "our_name" beholdt,
   45 markeret "skæv parring" → 6 manuelle splits
   (`apply_reviewed_name_diff_splits.py`: Kohle/Kok, Morsing/Mortensen/
   Mortier de Fontaine, Power Ellen+Marguerite, Schram/Skram, Seidelin/Seidl,
   Skovgaard/Schougaard) + 38 reelt manglende importeret.
6. **13 tankestregs-underposter koblet til ophav**
   (`link_dash_subentries_to_parents.py`): "— Hans Datter" havde mistet sin
   forælder ved alfabetisk sortering (tankestreg sorterer før bogstaver).
   Genfundet via referencens bevarede trykrækkefølge, matchet på
   sidehenvisning. Injiceret i `09_description` OG `12_see_also`.
7. **Dublet-opdagelse og -fjernelse** — den STØRSTE fejlkilde i sessionen:
   - `dedupe_imported_twins.py`: 958-importen matchede på navnetekst, så
     tomme/anderledes-stavede fornavne hos os fik referencens person
     importeret som "ny" — 393 dubletgrupper, 453 rækker fjernet
     (fuld sidehenvisnings-signatur + årstal som nøgle).
   - `merge_particle_and_refless_twins.py`: en ANDEN dublettype samme
     dedupe ikke fangede — par hvor kun den ene side har
     sidehenvisninger, og/eller efternavnet afviger med en ledende
     partikel (`d'Auchamp` vs `Auchamp`). 26 yderligere fusioneret.
   - Begge scripts prioriterer VORES stavemåde ved konflikt — referencen
     har en systematisk C→G-OCR-fejl (`Cornelis`→`Gornelis`,
     `Puggaard, C.`→`Puggaard, G.`, `Riegels, H.C.`→`H.G.`), bekræftet
     ved stikprøve før reglen blev sat.
8. **3 fusionsrester rettet manuelt** (`fix_three_fusion_remnants.py`,
   senere overhalet af punkt 7's dublet-opdagelse — Gerdislaw og
   Glücksborg viste sig at være dubletter, ikke bare defekte; kun Hansen-
   raden var reelt et selvstændigt fix).
9. **Feltsegmentering internt i `09_description`**
   (`refine_description_segmentation.py`, `merge_particle_and_refless_twins.py`
   er separate): tre mønstre hvor beskrivelsen stadig indeholdt navn/år:
   - **A**: beskrivelse begynder direkte med egen levetidsparentes
     (`Tiziano Vecellio | "(1476/77-1576), italiensk Maler."`)
   - **B**: beskrivelse begynder med fornavn(e) + levetid
     (`Titov | "Vladimir Pavlovič (død 1891), russisk Diplomat..."`)
   - **G**: levetid dublereret inde i `04_given_names`
     (`"Carl (ca. 1820-ca.1876)"`)
   Bevidst IKKE rørt: mødedatoer (`Amerikansk Beundrer (1871)` er ikke en
   levetid), rene titler (`Tysk-romersk Kejser` bliver IKKE til et
   fornavn), søskendegrupper med flere levetider i én beskrivelse.
   Udvidet undervejs til at acceptere komma i navnedelen
   (`Elisa, f. Hallady`, `Maria Elizabeth, Lady, f. Grevinde ...`) med
   værn mod at fange slægtskabsled (`Datter af Heinrich Z.`) som navn.

## Åbne tråde — bruger stillede 7 punkter i sidste besked, ALLE besvaret

Alle 7 punkter fra brugerens sidste instruktion (Auchamp/Ohsson-
alfabetisering, Alton/Aubert/Avezac-dubletter, Drewsen Elisa-segmentering,
Drewsen J.C., Puggaard C./G., Riegels H.C./H.G.) er verificeret løst i
punkt 7 og 9 ovenfor. **Ingen kendte åbne punkter fra brugerens direkte
instruktioner.**

## Kendte svagheder / bør tjekkes i næste session

1. **Dublet-jagten er sandsynligvis ikke udtømt.** To dublet-klasser blev
   fundet reaktivt (bruger pegede på konkrete eksempler), ikke ved
   systematisk scanning. En tredje klasse kan eksistere — f.eks. par hvor
   BEGGE sider har sidehenvisninger, men til delvist overlappende (ikke
   identiske) sider, eller hvor efternavnet afviger på andet end en
   ledende partikel. Værd at køre en bredere similarity-baseret scanning
   (fx difflib på `(efternavn, fornavn)`-par med delvist overlappende
   referencer) i næste session.
2. **`refine_description_segmentation.py`'s mønster A/G er kun kørt på
   rækker uden ÅRSTAL i 06/07.** Der kan være rækker der HAR årstal, men
   hvor `09_description` alligevel indeholder en overflødig ekstra
   parentes (linjeskift-fragment, dobbelt-OCR) som mønsteret aldrig så,
   fordi det tjekkede `if r["06_birth_year"] or r["07_death_year"]: continue`.
3. **Ingen automatiseret regressionstest for dublet-frihed.** De 453 + 26
   fjernede dubletter blev fundet og fjernet manuelt her; der er intet i
   `tests/test_personregister_xi_parsed.py`, der fanger en fremtidig
   gentagelse (fx hvis en ny import-runde laves). Overvej en test der
   flager grupper med identisk (efternavn, fuld sidehenvisnings-signatur).
4. **`test_row_count_in_expected_range`** blev hævet flere gange under
   sessionen (senest til `9000 ≤ n ≤ 10800`, se
   `tests/test_personregister_xi_parsed.py`). Grænsen er bevidst løs og bør
   ikke strammes uden at genmåle mod referencen.
5. **`data/review/personregister_xi_review_full.xlsx`** er sidst
   genereret FØR punkt 7-9's rettelser i denne session (`build_review_workbook.py`
   blev kørt, men kontrollér tidsstemplet mod seneste `parsed`-ændring —
   kør scriptet igen hvis der er tvivl, inden nogen læser arket).
6. **Reference-scriptets C→G-antagelse er ikke systematisk verificeret
   ud over de konkrete rækker brugeren pegede på.** Hvis flere C/G-
   forvekslinger findes i referencen fremover, er reglen i
   `merge_particle_and_refless_twins.py` allerede generisk nok til at
   fange dem (den prøver `ga.replace('g','c') == gb.replace('g','c')`),
   men er ikke testet bredt.

## Snapshots til rollback (i scratchpad, IKKE i git)

`C:\Users\nh\AppData\Local\Temp\claude\c--Users-nh-Documents-GitHub-hca-open-repo\cb83abfb-0574-45c0-8da0-6baff51e3858\scratchpad\`:
`parsed_before_split_yes.tsv`, `parsed_before_cue_splits.tsv`,
`parsed_before_desc_fusion.tsv`, `parsed_before_embedded_name.tsv`,
`parsed_before_tsv_harvest.tsv`, `parsed_before_import958.tsv`,
`parsed_before_namediff.tsv`, `parsed_before_skew38.tsv`,
`parsed_before_dashlink.tsv`, `parsed_before_3fix.tsv`,
`parsed_before_dedupe.tsv`, `parsed_before_twins2.tsv`,
`parsed_before_refine.tsv`, `parsed_before_refine2.tsv`.
Disse forsvinder med scratchpad-oprydning — kopiér til `data/curated/` hvis
langtidsopbevaring ønskes.

## Scripts skrevet denne session (alle i `scripts/parsers/`, alle tracked)

`suggest_description_fusion_splits.py`, `apply_description_fusion_splits.py`,
`split_wendell_chain.py`, `build_review_workbook.py` (udvidet),
`suggest_embedded_name_splits.py`, `apply_embedded_name_splits.py`,
`harvest_segmentation_from_tsv.py`, `apply_tsv_harvest_splits.py`,
`import_reference_missing_candidates.py`, `apply_reviewed_name_diff_splits.py`,
`link_dash_subentries_to_parents.py`, `fix_three_fusion_remnants.py`,
`dedupe_imported_twins.py`, `merge_particle_and_refless_twins.py`,
`refine_description_segmentation.py`, `calibrate_names_from_reference.py`,
`clean_year_parentheses_in_names.py`.

Kør i denne rækkefølge for at reproducere status fra bunden af en ældre
snapshot — men i praksis er alt allerede anvendt og commit'et; disse er
til reference/audit, ikke til genkørsel.
