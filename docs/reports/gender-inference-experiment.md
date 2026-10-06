# Køn for de ubestemte personer: eksperimenter og anbefaling

*Oktober 2026. Script: `scripts/enrichment/gender_inference_experiments.py`.
Alle tal kan genskabes med `python scripts/enrichment/gender_inference_experiments.py`
(og `--strict` for følsomhedsanalysen). Måledata ligger i
`data/review/gender_inference/`.*

**Kort fortalt:** En gennemsigtig kaskade af regler — titel i beskrivelsen, så
fornavn, så erhverv — kan kategorisere **837 af de 2.671 egentlige personer
(31 %)** blandt de ubestemte. Den estimerede præcision er ≈ 99,5 %.

Hvis en logistisk regression får lov til at tilføje **mænd** med sikkerhed
≥ 0,98, stiger dækningen til **1.477 (55 %)** ved samme præcisionsniveau.
Maskinlæringens **kvindelige** forudsigelser er ikke sikre nok til at bruges
(≈ 76 % korrekte i stikprøven), og en mere avanceret model gav ingen
forbedring.

Der er to forbehold, som skal med, hvor resultatet bruges:

- De infererede kategorier er stærkt skæve mod mænd (45 K mod 1.432 M). Det
  er langtfra den sande fordeling.
- Den eksisterende "kendte" kategorisering er selv regelbaseret inferens og
  ikke en uafhængig registrering.

---

## 1. Datagrundlag og features

### Den "kendte" kategorisering er selv infereret

De 10.228 personer fordeler sig i `person_gender.csv` som 3.714 mandlige,
3.286 kvindelige og 3.228 "Endnu ubestemt". Ingen kildeworkbook (V0.82, V0.92
eller V0.94) har et kønsfelt. Hele kategoriseringen er output fra
`parse_person_gender.py`, og scriptet genskaber den eksakt (0 afvigelser).

Det har betydning for evalueringen, fordi parseren selv bruger fornavnet.
Evidensgrundlaget for de 7.000 kategoriserede er:

| Evidens bag den eksisterende etiket | Poster |
|---|---:|
| **kun fornavn** | **2.337** |
| fornavn + beskrivelse | 1.366 |
| fornavn + label-titel | 952 |
| fornavn + beskrivelse + label-titel | 834 |
| kun beskrivelse (Datter af, -inde, hun …) | 709 |
| kun label-titel (Grevinde, f. Hansen …) | 488 |
| beskrivelse + label-titel | 314 |

En fornavnsmodel, der evalueres mod alle 7.000, ville blive målt mod sig selv.
For de 2.337 poster med kun fornavn er overensstemmelsen pr. konstruktion 100 %.

**Løsning: uafhængige referenceetiketter pr. feature-familie.** For hver post
genberegnes parserens indikatorer. Den familie, featuren tilhører, fjernes, og
etiketten bruges kun, hvis den resterende evidens stadig giver samme køn med
parserens egen sikkerhedsgrænse (≥ 0,70).

| Feature-familie | Evalueres mod | K | M |
|---|---|---:|---:|
| Fornavne | etiketter fra markører alene | 2.877 | 1.787 |
| Beskrivelse (erhverv, titel, rolle) | etiketter uden beskrivelsesevidens | 2.937 | 3.326 |
| Efternavn, nationalitet, metadata | alle etiketter (parseren bruger dem ikke) | 3.286 | 3.714 |

**Hvor rene er referenceetiketterne?** 2.988 poster har både en fornavnsindikator
og en sikker markøretiket. De to uafhængige kilder er enige i **2.983 tilfælde
(99,83 %)**. Alle 5 uenigheder skyldes noget, der kan forklares:

- "Mrs. George" (ægtemandens navn)
- "Marie Joseph Anton, Greve"
- to fejlsegmenterede labels
- "Sophus, f. Buchholz"

Etiketterne er altså gode nok som ground truth, men ikke fejlfri (se §4.5).

### Hvem er de ubestemte?

| Profil af de 3.228 ubestemte | Poster |
|---|---:|
| **Ikke en enkeltperson** (bør ikke have køn) | **557** |
| – henvisningsstubs uden beskrivelse ("Tum, se Thum.") | 372 |
| – fejlsegmenterede "– Se også: …"-rækker | 53 |
| – kurateret som family / crossReference / organisation / relational / group / animal (`person_entity_types.tsv`) | 101 |
| – grupper ("Frøknerne", "Juliette og Julia", "Kvartetsangere") | 31 |
| **Egentlige personer** | **2.671** |
| har fornavn i label | 1.409 |
| har et erhvervsord i beskrivelsens hovedled | 2.526 |
| har hverken fornavn eller erhvervsord | 70 |

Det centrale strukturelle fund er dette: **De ubestemte er ubestemte, netop
fordi deres fornavne er sjældne eller udenlandske.** Af de 1.881 ubestemte
med et fornavn har kun 1.075 et fornavn, der overhovedet forekommer blandt de
navne-uafhængigt kategoriserede, og kun 102 et, der forekommer mindst 5 gange.
Til gengæld er de domineret af erhvervsbeskrivelser som "Italiensk Maler",
"Fransk Forfatter", "Sognepræst" og "cand. jur.".

### Afprøvede features

- **Navn:** fornavn (eksakt), fornavn (stavevariant: Christian=Kristian,
  Sophie=Sofie, Frederikke=Frederike), sidste fornavn, fornavnsendelse på 2 og
  3 tegn, fuldt navn, efternavn og efternavnsendelse (-sen, -datter, -dotter …).
- **Label:** titel-segmenter ud over markørlisten.
- **Beskrivelse:** første erhvervsord i beskrivelsens *hovedled*, rolle fra
  `person_role.csv` og titelord i beskrivelsens hovedled.
- **Øvrige metadata:** nationalitet, leveår i label, antal bind med
  henvisninger, og om der er et fornavn.

*Hovedled* betyder teksten før første relationsord: af, til, efter, med, hos,
Datter, Søn osv. Uden den afgrænsning lærer modellen, at "Proprietær" er
kvindeligt, fordi tusind poster lyder "Datter af Proprietær …".
Markørord (Datter, Hustru, -inde, hun) maskeres også, så beskrivelsesfeatures
ikke kan genfinde den markør, der skabte etiketten.

---

## 2. Eksperimenter med enkeltfeatures

Tabellen viser 5-fold CV grupperet på efternavn + fornavnsvariant (samme
person med flere navneformer havner i samme fold). Feature-værdier er
opslag med Beta(1,1)-udglatning. Hver feature evalueres mod sin uafhængige
reference.

| Feature | Dækning | Præcision | Dækning ved ≥ 0,95 | Præcision ved ≥ 0,95 | Har featuren blandt ubestemte |
|---|---:|---:|---:|---:|---:|
| **fornavn (stavevariant)** | 79,9 % | **99,7 %** | 35,7 % | 99,9 % | 1.409 |
| fornavn (eksakt) | 78,4 % | 99,7 % | 32,3 % | 99,9 % | 1.409 |
| sidste fornavn | 72,8 % | 99,4 % | 27,3 % | 99,9 % | 1.409 |
| fornavnsendelse, 3 tegn | 87,0 % | 97,1 % | 49,8 % | 99,6 % | 1.362 |
| fornavnsendelse, 2 tegn | 90,3 % | 94,8 % | 58,4 % | 99,3 % | 1.407 |
| fuldt navn | 0 % | – | – | – | – |
| efternavn | 59,2 % | **44,3 %** | 0 % | – | 2.671 |
| efternavnsendelse | 11,7 % | 52,5 % | 0 % | – | 375 |
| label-segment (ikke-markør) | 5,7 % | 99,4 % | 3,1 % | 100 % | 63 |
| **erhverv (hovedled)** | 34,8 % | 96,2 % | 12,6 % | 99,3 % | **2.526** |
| **titel i beskrivelsen** | 2,5 % | 99,3 % | 1,0 % | 100 % | 121 |
| rolle (`person_role.csv`) | 56,2 % | 80,2 % | 0 % | – | 1.798 |
| nationalitet | 15,4 % | 75,5 % | 0,1 % | – | 889 |
| leveår / antal bind / har fornavn | 100 % | 55–59 % | 0 % | – | – |

Fortolkning:

- **Fornavnet er den stærkeste enkeltfeature, og det er ikke en artefakt af
  cirkularitet.** Målt mod etiketter, der *intet* har med navnet at gøre,
  rammer det 99,7 %. Stavevariantnøglen giver 1,5 procentpoint mere dækning
  uden målbart præcisionstab.
- **Erhverv er den eneste feature, der rækker ud til de ubestemte.** Næsten
  alle ubestemte har et erhvervsord. Men erhverv er praktisk talt kun et
  mandssignal: K-recall er 7 %, og kvindelige erhvervsformer (-inde, -ske) er
  allerede markører. "Digter" 100/101 M, "Forfatter" 96/98, "Maler" 78/78,
  "Sognepræst" 47/47.
- **Titel i beskrivelsen** er et hul i parseren. Den leder kun efter titler i
  label-feltet, så "Lindorf — *Grevinde*, Dresden 1844", "Baudissin, Thecla —
  *Komtesse*" og 22 *paver* er endt som ubestemte. Reglen har 99,3 % præcision.
- **Efternavn er værre end tilfældighed** (44 %). Når samme person og familie
  holdes i samme fold, peger et efternavn typisk på familiemedlemmer af modsat
  køn ("Datter af X" deler efternavn med X).
- **Fuldt navn** har nul dækning under grupperet CV. Under tilfældig CV
  dækker det ≈ 3 %, og det er udelukkende dubletter. Featuren er et
  dublet-detektor, ikke en prædiktor (se §4.4).
- Nationalitet, rolle og metadata er svage hver for sig. Fortolkningen af
  rolle-, nationalitets- og metadatarækkerne følger i §4.

### Fornavn som selvstændig feature

Præcisionen afhænger af, hvor mange gange navnet er set i træningsfolden:

| Navnet set i træning | Testposter | Præcision |
|---|---:|---:|
| 1 gang | 293 | 98,0 % |
| 2 gange | 231 | 100 % |
| 3–4 gange | 294 | 99,7 % |
| 5–9 gange | 629 | 99,7 % |
| 10–19 gange | 676 | 100 % |
| 20+ gange | 1.553 | 99,94 % |
| aldrig set | 925 (20 %) | — (ingen forudsigelse) |

Oversigten over fornavne ligger i `firstname_overview.csv`, med former,
optællinger, Wilson-nedre grænse og forekomst blandt de ubestemte.

| Klasse | Navne | Eksempler |
|---|---:|---|
| Meget sikker mand (n ≥ 5, ≥ 95 %) | 74 | Carl/Karl 0/115, Frederik 0/64, Christian/Kristian 0/52, Wilhelm/Vilhelm 0/52 |
| Meget sikker kvinde (n ≥ 5, ≥ 95 %) | 106 | Marie 122/1, Anna 116/0, Caroline/Karoline 90/0, Sophie/Sofie 82/0 |
| Sandsynlig (n 3–4, eller 90–95 %) | 113 | Holger 0/4, Søren 0/4, George 1/9 |
| Tvetydig (< 90 %) | 2 | Sophus 1/7, Richard 1/4 (begge skyldes fejl i referencen) |
| Sjælden (n < 3) | 584 | 636 af de ubestemte bærer et sådant navn |

Der er tre kritiske punkter:

1. **Navnestatistikken er lært af dansk/tysk navneskik og kan ikke flyttes
   ukritisk.** "Andrea" er 3/3 kvindeligt i registret, men Andrea Palladio og
   Andrea Vaccá Berlinghieri er italienske mænd. "Auguste" og "Marie" er
   mandlige i fransk brug (se §4.5). Et **nationalitetsværn**, som kun bruger
   navnet uden for dansk/norsk/svensk/tysk/islandsk kontekst, når navnet er
   belagt med samme køn i personens egen nationalitet, hæver præcisionen på
   fremmede nationaliteter fra 99,2 % til 100 %. Det koster kun 2 % dækning.
2. **"Fornavne", der er titler.** "Jfr.", "Frk.", "Madam" og "Mile" står i
   fornavnsfeltet. De første tre er korrekt kvindelige, men bør være markører
   i `gender_markers_da.csv` og ikke navne.
3. **Sandsynlighederne fra navneopslaget er underkonfidente.** Poster med en
   beregnet sandsynlighed på 0,60–0,70 er i virkeligheden korrekte i 98 % af
   tilfældene (ECE 0,096), fordi udglatningen trækker sjældne navne mod 0,5.
   Optællingen ovenfor er den ærlige kalibrering, ikke den rå sandsynlighed.
   Derfor bruges en simpel regel (n ≥ 3 og ≥ 95 % ét køn) i stedet for en
   sandsynlighedstærskel.

---

## 3. Eksperimenter med kombinationer

### Navnefeatures + beskrivelse

Logistisk regression og gradient boosting (HistGradientBoosting på
out-of-fold target-encodings) blev evalueret mod markør-etiketter (n = 4.601)
under to CV-regimer:

- **grupperet:** samme person og navnevariant holdes samlet.
- **navne-disjunkt:** intet fornavn i testfolden er set i træning. Det er den
  situation, de ubestemte er i.

| Model | Grupperet CV ≥ 0,95: dækning / præcision | Navne-disjunkt CV ≥ 0,95: dækning / præcision | Navne-disjunkt CV ≥ 0,99: dækning / præcision |
|---|---|---|---|
| LR, kun navne | 55,6 % / 99,88 % | 26,7 % / 99,67 % | 3,7 % / 100 % |
| LR, alle features | 63,3 % / 99,90 % | 36,8 % / 99,59 % | 10,6 % / 99,80 % |
| LR uden metadata | 63,7 % / 99,93 % | 39,8 % / 99,62 % | 11,5 % / 99,81 % |
| LR, alle features, isotonisk kalibreret | 81,4 % / 99,36 % | 62,7 % / **98,02 %** | 46,1 % / 99,10 % |
| Gradient boosting | 88,9 % / 99,05 % | 61,5 % / **93,96 %** | 42,4 % / 97,08 % |

Fortolkning:

- **Kombinationen forbedrer kun lidt, når der er et kendt fornavn.** Ved
  0,95 går præcisionen fra 99,88 % (kun navne) til 99,90–99,93 %, og
  dækningen fra 56 % til 63–64 %. Fornavnet bærer næsten alt.
- **Gradient boosting giver ingen dokumenterbar forbedring.** Den er dårligst
  på ukendte navne (94 % ved ≥ 0,95). Den fravælges.
- **Kalibrering, der virker inden for fordelingen, holder ikke uden for den.**
  Isotonisk kalibrering bringer ECE ned fra 0,039 til 0,006 under grupperet
  CV. Men på ukendte navne betyder en sikkerhed på "≥ 0,95" kun 98,0 %
  præcision. En model, der siger 95 %, er altså ikke korrekt 95 % af gangene,
  når den møder nye navne.

### Ikke-navnefeatures på poster, der ligner de ubestemte

Den bedste proxy for de ubestemte er de 2.110 poster, der er kategoriseret på
fornavnet alene. De har ingen markører, kun navn + beskrivelse, ligesom de
ubestemte. Deres etiket er uafhængig af beskrivelsen, så en model *uden*
navnefeatures kan evalueres ærligt på dem (199 K, 1.911 M).

| Model (ingen navnefeatures) | ≥ 0,95: dækning / præcision | ≥ 0,98: dækning / præcision | K-præcision ved 0,5 |
|---|---|---|---|
| beskrivelse (hovedled + rolle) | 55,5 % / 99,3 % | 42,2 % / 99,4 % | 43 % |
| + nationalitet | 54,2 % / 99,7 % | 43,6 % / **99,7 %** | 42 % |
| + efternavn + metadata | 47,4 % / 99,6 % | 18,9 % / 99,5 % | 40 % |

Beskrivelsen kan altså sikkert pege på **mænd** (≈ 99,5 %), men den kan ikke
pege på kvinder. Ved en neutral tærskel er kun 43 % af dens K-forudsigelser
korrekte.

---

## 4. Resultater og målinger

### 4.1 Regeltabeller (gennemsigtige opslag, grupperet CV)

| Regel | Kriterium | Dækning af reference | Præcision | Ubestemte dækket |
|---|---|---:|---:|---:|
| Fornavn | n ≥ 3, ≥ 95 %, nationalitetsværn | 66,3 % | **99,90 %** | 341 (32 K / 309 M) |
| Fornavnsendelse, 3 tegn | n ≥ 10, Wilson ≥ 0,95 | 23,8 % | 99,82 % | 37 |
| Erhverv | n ≥ 5, Wilson ≥ 0,90 | 7,8 % | 99,15 % | 463 (alle M) |
| Titel i beskrivelsen | markørlistens titelord | 2,6 % | 99,35 % | 121 |

Erhvervsreglens 4 "fejl" er alle fejl i *referencen* (se §4.5). Den reelle
præcision er sandsynligvis højere. Fornavnsendelsen fravælges: den dækker få
ubestemte, og i stikprøven ramte den netop romanske mandsnavne forkert
(Antoine → K).

### 4.2 Sikkerhedstærskler og dækning af de 2.671 ubestemte personer

| Tilgang | Dækning | K | M |
|---|---:|---:|---:|
| S1 fornavn alene | 341 (12,8 %) | 32 | 309 |
| S2 titel → fornavn → erhverv | 837 (31,3 %) | 45 | 792 |
| S2 + LR-mænd ≥ 0,99 | 1.347 (50,4 %) | 45 | 1.302 |
| **S2 + LR-mænd ≥ 0,98** | **1.477 (55,3 %)** | **45** | **1.432** |
| S2 + LR-mænd ≥ 0,95 | 1.738 (65,1 %) | 45 | 1.693 |
| LR alene ≥ 0,95, prior-korrigeret (fravalgt) | 1.602 (60,0 %) | 68 | 1.534 |
| LR alene ≥ 0,70, prior-korrigeret (fravalgt) | 2.207 (82,6 %) | 275 | 1.932 |

**Prior-skift.** Træningsetiketterne er 45 % kvinder. EM-estimatet efter
Saerens et al. (2002) for de ubestemte er **21 % kvinder** (15 % under den
strenge reference). Uden korrektion overvurderer LR systematisk P(kvinde) for
de ubestemte. Med 0,95 som tærskel falder de rå K-forudsigelser fra 90 til 68,
når der korrigeres.

### 4.3 Kontrol på selve målpopulationen (stikprøve)

Ingen etiketter for de ubestemte findes. Derfor er stikprøver af forudsigelserne
vurderet ud fra navn og beskrivelse (`llm_spotcheck.csv`).

**Rettelse efter stikprøven.** Stikprøven er taget på en kørsel, hvor rollefeltet fra
`person_role.csv` blev læst forkert (skilletegn `;` læst som `|`, så 1.254 personer med flere
roller blev én sammensat kategori). Fejlen er rettet, og alle tal i denne rapport er fra den
rettede kørsel. Rettelsen ændrede ikke S2, men flyttede 130 poster ud af og 112 ind i S3's
mandlige niveau uden at vende noget køn. De 112 tilkomne er gennemlæst (alle læses som mænd:
fx Ulysses S. Grant, Madvig, Tietgen). De øvrige stikprøvetal gælder forrige kørsel, og de
er derfor ikke gentaget på det rettede resultat.

**Forbehold: Vurderingen er foretaget af Claude, en sprogmodel, og er ikke
kildeverificeret.** Den bør gentages af en redaktør, før resultatet
publiceres.

| Stratum | Vurderet | Korrekt | Fejl | Uafgørligt |
|---|---:|---:|---:|---:|
| S2, alle kvinder | 45 | 43 | 0 | 2 ("Olsen, Mile") |
| S2, mænd via titel (alle) | 107 | 107 | 0 | 0 |
| S2, mænd, tilfældig stikprøve | 49 | 49 | 0 | 0 |
| LR-mænd ≥ 0,99, stikprøve | 60 | 60 | 0 | 0 |
| LR-mænd 0,95–0,99, stikprøve | 40 | 40 | 0 | 0 |
| **LR-kvinder ≥ 0,95 (alle)** | 39 | 29 | **9** | 1 |

Det svarer til en Wilson-nedre grænse på ≈ 98 % for S2 (199/199 afgørbare)
og ≈ 96 % for LR-mænd (100/100).

LR-kvindernes 9 fejl er alle mandsnavne:

- Antoine (×4)
- Napoleone
- Andrea
- Nicaise
- Otte
- Ira

Endelsesfeatures lærer, at -ine, -a og -e er kvindeligt, og det holder ikke
for romanske og ældre nordiske mandsnavne. **LR's kvindelige forudsigelser
kan ikke bruges automatisk.** Køen (41 poster) er derimod en god
gennemgangskø (≈ 76 % træf).

Stikprøven fandt også fejl, der *ikke* stammede fra metoderne:

- grupper og stubs, som skulle udelukkes (nu filtreret, se §1)
- et LR-"veto" over S2, som kun fjernede korrekte mænd: Jean-Marie Dargaud,
  Antoine de La Tour og Giambattista Zeno (vetoet er fjernet)

### 4.4 Dataproblemer (punkt 4 i opgaven)

- **Dubletter:** 320 navnenøgler (efternavn + fornavnsvariant) har mere end én
  post (725 poster) og 5 eksakte dubletter af label + beskrivelse. Under
  tilfældig CV ville de lække. Al CV her er derfor grupperet.
- **Samme person, flere navneformer:** stavevariantnøglen samler Christian og
  Kristian, Sophie og Sofie osv. i samme gruppe.
- **Features, der afslører den eksisterende etiket:** fornavnet (for 5.489
  etiketter), markørord i beskrivelsen og titler i label. Det er håndteret
  med familie-uafhængige referencer, maskering og afgrænsning til
  beskrivelsens hovedled.
- **Små navnegrupper:** 584 af 879 navnenøgler er set under 3 gange. Navne set
  én gang er stadig 98 % præcise, men de udelades fra højsikkerhedsniveauet.
- **Henvisningsstubs har fået køn:** Den eksisterende kategorisering giver køn
  til 277 henvisnings- og fejlsegmenterede rækker ("– Se også: Nielsen,
  Augusta." → Kvindelig). Køn hører til målposten, ikke til henvisningen.

### 4.5 Fejl i den eksisterende kategorisering (bifund)

Uenighederne mellem uafhængige kilder peger på konkrete fejl i
`person_gender.csv`:

- **Fejlagtigt kvindelige på grund af et fransk mandsnavn:** "Bouffé, Marie —
  Fransk Skuespiller", "Barbier, Auguste — Fransk Digter" og "Jeunesse,
  Auguste — Fransk Forfatter" (`existing_label_suspects.csv`).
- **"f." læst som pigenavn:** "Alexis, Willibald (Pseud, f. Georg Wilh.
  Heinr. Häring)". Her betyder "f." "for" i "Pseudonym for", men parseren
  læser det som et pigenavn og giver Kvindelig.
- **Navn og markør modsiger hinanden:** "Marie Joseph Anton …, Greve"
  (mandlig ifølge markør, men "Marie" peger på kvinde) og "Sophus, f.
  Buchholz" (`label_noise_name_vs_markers.csv`).

Det er få fejl, men de viser samme mønster som ovenfor: Navnestatistik fra én
kultur flyttes ukritisk til en anden.

---

## 5. De mest lovende tilgange

1. **Fornavnsleksikon med nationalitetsværn:** ekstremt præcist, men dækker
   kun 13 %, fordi de ubestemtes navne er sjældne.
2. **Erhvervsleksikon:** dækker mange, men kun som mandssignal.
3. **Titelord i beskrivelsen:** få poster, men sikre. Det er en ren rettelse
   af et hul i markørerne.
4. **Logistisk regression uden metadata, prior-korrigeret:** god til mænd med
   erhverv, upålidelig for kvinder og ukendte navne.

Fravalgt med begrundelse:

| Tilgang | Hvorfor fravalgt |
|---|---|
| Efternavn | under tilfældighedsniveau |
| Metadata | kun majoritetsklasse; skabte en falsk kvindelig skævhed for poster med kun efternavn |
| Gradient boosting | dårligst på nye navne |
| Fornavnsendelser som selvstændig regel | romanske mandsnavne |
| LR's kvindelige forudsigelser | ≈ 76 % |
| LR-veto | fjernede korrekte poster |

---

## 6. Tre endelige strategier

### S1 — Fornavnsleksikon

| | |
|---|---|
| **Features** | første fornavn (stavevariant) + egen nationalitet |
| **Sådan virker den** | Optælling af fornavnet blandt markør-kategoriserede personer. Navnet bruges, hvis n ≥ 3 og ≥ 95 % ét køn. For fremmede nationaliteter kræves det, at navnet er belagt med samme køn i personens egen nationalitet. |
| **Forventet præcision** | 99,9 % (CV, 3.052 poster) |
| **Dækning af de ubestemte** | 341 / 2.671 (12,8 %), 32 K / 309 M |
| **Vigtigste styrke** | En linje pr. navn med en tælling bag. Kan forklares til enhver bruger. |
| **Vigtigste svaghed** | De ubestemte har netop de navne, leksikonet ikke kender. |
| **Gennemsigtighed** | Fuld. Deterministisk, og tabellen kan inspiceres og overstyres i `given_name_gender_overrides.csv`. |

### S2 — Regelkaskade: titel → fornavn → erhverv

| | |
|---|---|
| **Features** | titelord i beskrivelsens hovedled, S1, første erhvervsord i hovedledet |
| **Sådan virker den** | Hvert led giver en stemme. Erhverv bruges kun, når fornavnet ikke afgør sagen. Uenighed giver "Endnu ubestemt" (0 tilfælde i praksis). Erhvervsleksikonet kræver n ≥ 5 og Wilson-nedre ≥ 0,90, hvilket giver 9 ord: digter, forfatter, skuespiller, maler, cand., sognepræst, student, premierløjtnant og gesandt. |
| **Forventet præcision** | ≈ 99,5–99,9 % (CV pr. led 99,2–99,9 %; stikprøve 199/199 afgørbare) |
| **Dækning af de ubestemte** | 837 / 2.671 (31,3 %), 45 K / 792 M |
| **Vigtigste styrke** | Hver beslutning har en menneskelæselig begrundelse ("erhverv »maler« 78/78"). |
| **Vigtigste svaghed** | Skæv mod mænd. Kvinder uden kendt fornavn eller titel findes ikke. |
| **Gennemsigtighed** | Fuld. Tre små tabeller og en deterministisk rækkefølge. |

### S3 — S2 + statistisk supplement for mænd

| | |
|---|---|
| **Features** | som S2, plus logistisk regression på fornavn, fornavnsendelser, efternavn, beskrivelsens hovedled (alle ord), rolle og nationalitet. Ingen metadata. Isotonisk kalibreret og prior-korrigeret. |
| **Sådan virker den** | S2 først. Poster, S2 ikke afgør, kategoriseres som **Mandlig**, hvis LR giver P(M) ≥ 0,98, og posten har mindst ét fornavn, erhvervsord eller titelord. LR's kvindelige forudsigelser bruges ikke automatisk, men lægges i en gennemgangskø. |
| **Forventet præcision** | ≈ 99,5 % (LR-mænd: 99,7 % på proxy-sættet ved 0,98; stikprøve 100/100) |
| **Dækning af de ubestemte** | 1.477 / 2.671 (55,3 %), 45 K / 1.432 M |
| **Vigtigste styrke** | Fanger mænd med usædvanlige erhvervsbeskrivelser ("Konsumptionskasserer", "Overrabbiner", "Hotelvært"), som intet leksikon har set nok gange. |
| **Vigtigste svaghed** | Modelvægte i stedet for en tælling; begrundelsen er mindre direkte. Afhænger af en tærskel, hvis kalibrering ikke kan verificeres på de ubestemte. |
| **Gennemsigtighed** | Reproducerbar (fast seed, deterministisk). Kan forklares som "ligner N mandlige poster med de samme ord", men ikke linje for linje. |

---

## 7. Anbefaling

**S2 som grundlag og S3's mandlige supplement som et separat, lavere
sikkerhedsniveau**, så det fremgår, hvilke poster der hviler på en regel, og
hvilke på en model.

| Niveau | Metode | Poster | Estimeret præcision |
|---|---|---:|---:|
| `høj` | S2 (titel / fornavn / erhverv) | 837 | ≈ 99,5–99,9 % |
| `sandsynlig` | S3, LR-mand ≥ 0,98 med evidens | 640 | ≈ 99,5 % |
| — | ingen tilstrækkelig evidens | 1.194 | – |
| `ikke relevant` | henvisning, gruppe, familie, organisation | 557 | – |

Det er **ca. 55 % af de ubestemte personer** med meget høj sikkerhed.
Resten forbliver ubestemt. Det er korrekt og ikke en mangel.

Fire ting, der skal med:

1. **Repræsentationsskævhed.** 45 K mod 1.432 M, mens den estimerede andel af
   kvinder blandt de ubestemte er ≈ 21 % (≈ 550 personer). Metoden finder
   kvinderne langt dårligere end mændene. Facettællinger efter inferensen må
   derfor ikke læses som registrets kønsfordeling. Et UI med kønsfacet bør
   vise "infereret" separat.
2. **Kvinderne kræver mennesker.** LR-kvindekøen (41 poster, ≈ 76 % træf blandt de 38 afgørbare i stikprøven),
   "Mile"-tilfældene og de 70 poster uden fornavn og erhverv er de oplagte
   mål for manuel gennemgang.
3. **Billige forbedringer af parseren** med samme metode:
   - tilføj "Jfr.", "Frk.", "Madam" og "Demoiselle" som markører
   - anvend label-titlerne også på beskrivelsens hovedled
   - indfør et nationalitetsværn for navnestatistikken
   - skeln "Pseud. f." fra pigenavnet "f."
   - giv ikke køn til henvisningsstubs
4. **Følsomhed.** Kræves der ≥ 0,90 i stedet for ≥ 0,70 for referenceetiketter
   (`--strict`), forsvinder etiketterne baseret på kun fornavn fra
   erhvervsleksikonets grundlag. S2's erhvervsled skrumper da (S2: 837 → 448).
   Fornavns- og titelleddene er uændrede (99,9 % og 99,1 %), og S2 + S3
   dækker stadig 1.624. Valget af 0,70 er begrundet i, at fornavns- og
   markøretiketter er enige i 99,83 % af tilfældene.

---

## 8. Markering i datasættet

Den infererede kategori er en **berigelse**, ikke en ændring. Den følger
mønsteret fra `docs/architecture.md` §Enrich: Hvert berigelsestrin skriver
sin egen fil, og et manglende trin tømmer en facet uden at bryde et build.

**`person_gender.csv` røres ikke.** Den nye kategorisering skrives til en
separat fil, `data/normalized/person_gender_inferred.csv`, med én række pr.
person, der i dag er "Endnu ubestemt":

| Kolonne | Indhold |
|---|---|
| `entity_id` | nøgle |
| `koen_infereret` | `Mandlig` / `Kvindelig` / `Endnu ubestemt` / `Ikke relevant` |
| `sikkerhedsniveau` | `høj` (regel) / `sandsynlig` (model) |
| `estimeret_praecision` | stratumets målte præcision, ikke modellens egen sandsynlighed |
| `metode` | `titel-beskrivelse` / `fornavn` / `erhverv` / `lr-mand` |
| `evidens` | menneskelæselig begrundelse, fx `erhverv »maler« 78/78` |
| `metode_version` | fx `gender-inference 2026-10` + git-commit |
| `gennemgang` | `ikke gennemgået` / `bekræftet` / `afvist` + redaktørens initialer |

Det giver tre lag med hver sin proveniens:

1. **Registreret:** ingen findes i kilderne i dag.
2. **Regelafledt:** den eksisterende `person_gender.csv` fra
   `parse_person_gender.py`.
3. **Infereret:** den nye fil.

Det er værd at gøre eksplicit, fordi det, der i dag kaldes "den eksisterende
kategorisering", heller ikke er en registrering. Det bør stå i UI og
dokumentation som *afledt af markører og fornavn*.

En redaktørs beslutning skrives i `gennemgang`. Den gemmes ikke ved at rette
`koen_infereret`, så næste kørsel ikke overskriver den.

I UI-facetten bør niveauerne kunne skelnes, fx "Mand", "Mand (infereret)" og
"Ukendt", med evidensen tilgængelig ved hover eller på personkortet.

*Note: Den UI-kravspecifikation, der nævnes i opgaven ("Diary Index UI
Requirements.txt"), var ikke tilgængelig i denne session. Forslaget bygger på
repoets egen arkitekturbeskrivelse.*

---

### Filer

| Fil i `data/review/gender_inference/` | Indhold |
|---|---|
| `summary.json` | alle nøgletal |
| `single_features.csv` | hver feature × tærskel: dækning, præcision, recall pr. køn, dækning af ubestemte |
| `combined_models.csv` | LR- og GBM-varianter × CV-regime × tærskel |
| `nonname_models_on_name_labels.csv` | beskrivelsesmodeller på proxy-sættet |
| `calibration.csv` | reliabilitetstabeller, ECE, log-loss, Brier |
| `rule_tables.csv`, `rule_occupation_table.csv`, `rule_errors.csv` | regelvarianter og deres fejl |
| `firstname_overview.csv`, `occupation_overview.csv` | leksika med klasser og forekomst blandt ubestemte |
| `unknown_predictions.csv` | alle 2.671 ubestemte personer med S1/S2/S3 og anbefalet køn + begrundelse |
| `llm_spotcheck.csv` | stikprøvevurderingerne (LLM, ikke kildeverificeret) |
| `existing_label_suspects.csv`, `label_noise_name_vs_markers.csv` | mistænkte fejl i den eksisterende kategorisering |
| `strict/` | samme kørsel med referencekrav ≥ 0,90 |

---

### Kategorier til gennemsyn (`build_gender_review_excel.py`)

`gender_inference_experiments.py` udvider nu »Endnu ubestemt« (parserens
confidence < 0,70) til fire værdier; `unknown_predictions.csv` har kolonnerne
`kategori`, `kategori_sikkerhed`, `kategori_metode` og `kategori_grundlag`.
`build_gender_review_excel.py` bygger samme kategorisering over den manuelt
rettede segmentering (`data/raw/hca-personregister-redesign_gender-testing.xlsx`,
10.079 poster) som en Excel-fil sorteret efter Køn, Kønssikkerhed og Navn og
farvet efter køn.

| Værdi i Køn | Betydning |
|---|---|
| Irrelevant | firma, slægt, anden korporation, gruppe, dyr eller krydshenvisning, uanset hvor mange personer posten dækker. Kuratorlisten tæller kun, når parseren ikke selv har fundet et køn (»Müller« er både en henvisning og en person) |
| Endnu ubestemt, sandsynligvis kvinde / mand | kun når forslagets sikkerhed er under 0,71 (`LEAN_BELOW`); derover står Mandlig/Kvindelig, og kolonnen Kønsmetode viser, at det er afledt. Forslaget er det første af: S2-kaskaden, S3-mand ≥ 0,98, enkeltnavn i fornavnsleksikonet, kvindelig form i beskrivelsens første ord (-inde, -dame, -datter, jfr. …), S3-mand ≥ 0,60 |
| Endnu ubestemt, kræver manuelt gennemsyn | ingen evidens, uenige regler eller en model, der kun peger svagt |

Modellens kvindeforslag bruges ikke alene, af samme grund som i §4.3: de
holdt ikke i stikprøven, og på poster med kun efternavn er de næsten
udelukkende mænd (Euripides, Moses, Eugène Cavaignac). De ligger under
»kræver manuelt gennemsyn« med modellens retning i grundlaget.
`--base-rate-male` flytter de poster, hvor modellen kun er svag, til
»sandsynligvis mand« ud fra grundraten; `--female-min` slår modellens
kvindeforslag til igen. Grænsen 0,60 for mænd er ikke målt mod facit.

**Ordregler (oktober 2026).** Reglerne R0–R5, P1–P5 og B1–B2 fra
[`gender-unclear-dictations.md`](../gender-unclear-dictations.md) er bygget ind i
`scripts/enrichment/gender_head_rules.py` med ordlisterne i
`data/curated/gender_head_terms_da.csv`. De kører efter S2 og før S3. På
HCAP-segmentringen (10.079 poster) falder »kræver manuelt gennemsyn« fra 648 til
454. To afvigelser fra diktatet: R4 tæller ikke, når hovedleddet også har et
-inde-ord (»Forfatterinde og Oversætter«), og R3 tæller ikke et -inde-ord foran
et egennavn (»Grevinde Elise Moltke-Hvitfeldts Sjælesørger«). *Abbed* er føjet
til P3. Hver regel er målt mod parserens afgjorte poster
(`head_terms_measured.csv`), og poster, hvor en regel modsiger parseren, står i
`rule_vs_parser_disagreements.csv` (fx Lafayette som Kvindelig, franske mænd ved
navn Auguste og Marie). R5's navneliste skrives til
`data/normalized/given_name_markers_male.csv`.
