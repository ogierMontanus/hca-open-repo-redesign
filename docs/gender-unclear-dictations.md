# Uafklarede køn: gennemgang og nye regler

*Oktober 2026. Grundlag: manuel gennemgang af
`data/review/gender_inference/hca-personregister-redesign_gender-review.xlsx`,
arket »Personregister«, **kolonne G (Kønssikkerhed) = 0,5**, dvs. Excel-række
2–649 (648 poster, alle »Endnu ubestemt, kræver manuelt gennemsyn«). Rækkehenvisninger
gælder arkets nuværende sortering. Afsnit 1 er det oprindelige diktat i
renskrift. Afsnit 2 er regler, der kan bygges ind i pipelinen
(`gender_inference_experiments.py` / `lean_category`): R0–R4 (ord i label og
beskrivelse), P1–P5 (ord, der sætter både køn og rolle), B1–B2 (rene køns-
ord i beskrivelsen) og R5 (fornavne i anden runde).*

---

## 1. Iagttagelser fra gennemgangen

### Titler, der står som fornavn

Nogle poster har en titel i stedet for et fornavn. De er kvinder:

- **Misses** (række 468, »Philips, Misses«)
- **Mile / Mlle** (439, 460)
- **Madame** (567)
- **Jomfru** (66, 166, 196, 374)

### Slægts- og rolleord i beskrivelsen

I beskrivelsen (kolonne N) står der ofte et ord, som afgør køn:

- **Niece / Niecer** (378, 468): kvinder
- **Søster, Moder, Datter, Søsterdatter**, også efter »Hans« / »Hendes«
  (49, 142, 242, 340 m.fl.): kvinder. Possessivet peger på en anden person.
- **Tjenestepige** (364) og andre *-pige* (Barnepige, Stuepige, Kokkepige: 456): altid kvinde.
- **Pige** (646, 508): kvinde.
- **Elskede** (352 Laura, 373 Luti: »Petrarcas / Rafaels Elskede«): kvinde.
- **Værtinde** (380 Margherita): kvinde.

### Kvindelige former på *-inde*

Alle professions- og rolleord, der ender på *-inde*, skal give kategorien
kvindelig, også når ordet ikke står først i beskrivelsen: »prostitueret
*Tyrkinde*« (180, 181), »*Skuespillerinde*(?)« (570), *Værtinde* (380).

### Umarkerede erhverv er mænd

Registret kalder konsekvent kvinder *Forfatterinde*, *Skuespillerinde*,
*Malerinde*. Et erhverv **uden** *-inde* er derfor et mandssignal. Her kan vi
bruge negationen. Det gælder også sammensætninger: *Skuespilforfatter*,
*Lystspilforfatter*, *Librettoforfatter*, *Romanforfatter* (267, 357, 450, 586).
Det dækker også andre erhverv med en kvindelig form i registret: Lærer,
Digter, Maler, Komponist, Sanger.

### Foreslået metode

- Udled kønsspecifikke ord fra **professionsbeskrivelsen i kolonne N**, evt. med
  en reasoning-model, der gennemgår, hvilke professioner registret har, og
  hvilke der er kønsspecifikke.
- Brug de samme kønsspecifikke ord i **hele det usikre interval**, ikke kun i
  de poster, der blev set under gennemgangen.

---

## 2. Regler til pipelinen

### Hvorfor det ikke allerede virker

- Titelreglen i `gender_markers_da.csv` kender *Madame, Frøken, Frue*, men ikke
  *Jomfru, Mile, Mlle, Misses* som label-segment. *Jomfru* findes kun som
  titel i beskrivelsen.
- Kvindeformsreglen (`FEM_HEAD_RE`) ser kun på **beskrivelsens første ord**.
  *»prostitueret Tyrkinde«* rammes ikke.
- Erhvervsleksikonet (S2) matcher kun hele ord og kun det første erhvervsord.
  *Skuespilforfatter* og *Operakomponist* findes derfor ikke.
- Slægtsordene tæller kun med, når de er »referent-sikret«. *Hans Søster*
  giver to stemmer, M fra »hans« og K fra »Søster«, og ender som uafgjort.
- Modellen (LR) giver kvinde til mandlige forfattere og digtere med
  usædvanlige navne (Euripides 0,70, Eugène Sue 0,74, Hollenius 0,91). Disse
  regler skal derfor komme **før** modellen.

### Hovedled

Alle beskrivelsesregler arbejder på beskrivelsens **hovedled**: teksten før
første præposition eller underordnet led. I praksis afgrænses den ved:

`af, til, efter, med, hos, ved, i, fra, paa, for, under, over, om, som, g.m.,
gift, forlovet, se:`, komma, semikolon, parentes og punktum.

Beskrivelser, der begynder med citationstegn (`»`) eller indeholder »hvis«,
springes over, fordi ordet i så fald beskriver en anden person. Afgrænsningen
er nødvendig:

- *Kuntze*: »forlovet med Organist Rieffels **Datter**« er en mand
- *Jung*: »Pension for unge **Piger**« er ejeren
- *Metella, Cæcilia*: »g.m. Licinius Crassus, **Officer**« er hustruen
- *Petersen*: »hvis **Søster** …«

### Reglerne

Rækkefølgen er prioriteten. Første regel med svar vinder. Hvis to regler giver
modsat køn, bliver posten »kræver manuelt gennemsyn« (se *Eyckholt, Frue*,
række 174: label Frue, men beskrivelse »Fader til …«).

| # | Regel | Køn | Betingelse | Eksempler |
|---|---|---|---|---|
| **R0** | Par og blandede grupper → *Irrelevant* | – | Label slutter på »og Frue« / »og Hr.«, eller beskrivelsen er en blandet gruppe (Damekvartet). **Grupper af ét køn får kønnet**: Frøknerne, Komtesser, Piger → K, Drenge → M (se B1/B2) | 70, 236, 251, 256, 257, 302, 441, 442 (alle »X og Frue«). Alle markeres i kolonne S, se »Opdeling af familiegrupper« |
| **R1** | Titel i label | K | Et label-segment efter komma, eller et fornavnsfelt, er et af: Jomfru, Jfr, Frk, Frøken, Mile, Mlle, Mademoiselle, Misses, Madam, Madame, Mme, Frue, Fru | 66, 166, 196, 374, 439, 460, 468, 567 |
| **R2** | Slægts- og rolleord som hovedled | K / M | Ordet er hovedledets navneord, evt. efter genitiv eller possessiv (»Hans«, »Hendes«, »Fru X's«, »Rafaels«). K: Søster, Moder, Niece, Søsterdatter, Datter, Pige, \*pige, Elskede, Værtinde, Mætresse, Enke. M: Broder, Fader, Søn, Dreng, Svoger, Dattersøn, Søstersøn. Possessivets køn ignoreres | K: 49, 142, 232, 242, 281, 340, 352, 364, 373, 378, 389, 435, 455, 456, 508, 628, 646. M: 35, 108, 149, 194, 215, 347, 466, 521, 555, 573 |
| **R3** | Kvindelig form | K | Et ord i hovedledet eller label-segmentet ender på *-inde* eller *-esse* (ikke *-minde*; *-esse* kun i beskrivelsen, ikke i navnet: *Hesse*) | 180, 181, 380, 570, 582 (Mætresse) |
| **R4** | Umarkeret erhverv | M | Et ord i hovedledet *ender på* et ord fra mandslisten nedenfor, og ordet har ingen kvindelig endelse | 71 poster, fx 267, 357, 450, 586 (Forfatter), 14, 172, 566 (Tragediedigter) |

**R4's mandsliste** (bygges ud fra data, se nedenfor): forfatter, digter,
maler, lærer, komponist, skuespiller, sanger, præst, journalist, redaktør,
officer, oversætter, billedhugger, pianist, violinist, general, kejser, konge,
professor, læge, dreng, musiker, kontorist, kapelmester samt de attesterede
sammensætninger med *-mand* (embedsmand, landmand, sømand, stormand,
finansmand).

### Regler, der sætter både køn og rolle (P1–P5)

Disse ord afgør to felter på én gang: kolonne F (Køn) og kolonne H (Rolle /
Erhverv). Rollen er en af de eksisterende buckets i
`data/curated/person_role_terms_da.csv`. Bucketen for *Adelig* hedder i filen
**Adel/Kongelig/Hof**.

| # | Ord | Køn | Rolle | Hvor | Vagter | Eksempler |
|---|---|---|---|---|---|---|
| **P1** | Ord, der *ender på* **præst**: Præst, Sognepræst, Hjælpepræst, Hofpræst, Hovedpræst, Ypperstepræst, Feltpræst | M | Gejstlig | Hovedled og label-segment | Ordet skal *ende* på »præst«. Så rammes ikke Præstekone, Præsteenke, Præstedatter (K) og Præstegaard (et sted). *Præstekone* og *Præsteenke* tilføjes R2 som K | 36, 260, 461, 515 (»Russisk Præst«), 688, 733, 750 |
| **P2** | Hærens grader: **Menig, Sergent, Løjtnant**, også som sammensætning: Premierløjtnant, Sekondløjtnant, Underløjtnant, Oberstløjtnant, Generalløjtnant, Kaptajnløjtnant, Stabssergent; samt **Major**, **Oberstløjtnant**, **Officer.\***, **.\*korporal.\*** (Underkorporal) | M | Militær | Hovedled **og label-segment** (»Larsen, Menig, 6. Infanteriregiment, Nr. 424«) | Ikke efter »f.« (pigenavnet: »Rahbek, f. Major«). Ikke ord på *-inde* (Generalinde: R3 vinder) | 91, 155, 156, 296, 431, 434, 528, 538, 600, 621, 656, 670, 700 |
| **P3** | **Abbé** (også *Abbe*) | M | Gejstlig | Label-segment og hovedled | *Abbedisse* er K og står allerede i markørlisten | 675 (»Épée, Charles-Michel, Abbé de l'«) |
| **P4** | **Marquis**, *Marquisen*, *Marquis'en*, **Pasha**, **Emir** | M | Adel/Kongelig/Hof | Label-segment og hovedled | **Marquise er K og må ikke ramme**: mønstret skal være `Marquis(en|'en)?` og ikke `Marquis.*`. *Marquise* føjes til R1 som K | 5, 18, 74 (Emir), 239, 388, 406 (Pasha), 128, 676, 679 (Marquis) |
| **P5** | **Komtesse.\*** (Komtesse, Komtesser) | K | Adel/Kongelig/Hof | Hovedled og label-segment | Står allerede som label-titel i markørlisten, men ikke i beskrivelsen | 529 (»2 Komtesser«) |

Målt i data:

- **P1:** ord på *-præst* i hovedledet: 116 mænd mod 4 »kvinder« blandt de
  poster, der har fået køn. Tre af de fire er *Præstekone*, *Præstedatter* og
  *Præstegaard*. Den fjerde, »Lautrup, J. H. (1798–1856), Sognepræst«, er en
  mistænkt fejl i den eksisterende kategorisering (føjes til
  `existing_label_suspects.csv`).
- **P2:** *-løjtnant* i hovedledet: 163 mænd mod 0 kvinder. *Menig* og
  *Sergent* har ingen afgjorte poster, og det er derfor, de står tilbage
  (i intervallet: 155, 156, 296, 538, 600).
- **P4:** i dag står *Lafayette, Marie Joseph Paul …, Marquis* som
  **Kvindelig** på grund af fornavnet *Marie*. P4 skal derfor ikke kun fylde
  hullerne. Den skal også **rapportere uenighed** med den eksisterende
  kategorisering (skriv til `existing_label_suspects.csv`, overskriv ikke).
- **Rolle:** *præst* og *løjtnant* findes i forvejen i
  `person_role_terms_da.csv`, og de sammensatte ord får rollen. Tilføj
  *menig, sergent, abbé, abbe, marquis, marquisen* med bucketerne ovenfor.

**Forslag til flere grader** (samme mønster, ikke bestilt: bekræft). Alle har
Militær i rolletabellen, men ingen kobling til køn. I de afgjorte poster er
de rene mænd. (*Major* og *Officer* er nu med i P2.)

| Ord | Mænd | Kvinder |
|---|---:|---:|
| kaptajn | 66 | 0 |
| oberst | 42 | 0 |
| admiral | 8 | 0 |
| kommandør | 6 | 0 |
| general | 87 | 1 (*Generalinde*, fanges af R3) |

### R5: fornavne i anden runde

Efter R0–R4, P1–P5 og B1–B2 køres fornavnene **en gang til**. Alle fornavne, der hører
til en mand med sikkerhed **> 0,7**, bliver mandlige markører i taggeren.
Det gælder uanset hvor få gange navnet er set.

1. **Frø:** alle poster med Køn = Mandlig og Kønssikkerhed > 0,7: parserens,
   og dem R1–R4, P1–P5 og B1–B2 lige har afgjort. I dag er det 4.810 mandlige poster
   med fornavn.
2. **Nøgle:** første fornavn med småt (stavevariant: Christian = Kristian)
   *og* **etnisk bøtte**. Bøtten er enten *hjem* (nationalitet tom, dansk,
   norsk, svensk, tysk, islandsk, færøsk) eller personens egen nationalitet.
3. **Nationalitetsværn:** en post med en fremmed nationalitet får kun stemme
   fra navnets egen bøtte, uden fald tilbage til *hjem*. *Andrea* er mand i
   italiensk (4/4), men kvinde i hjem-bøtten.
4. **Ingen mindstetælling.** I dag kræver parseren n ≥ 3 (n ≥ 5 i den
   generelle bøtte) og ≥ 85 % skævhed. R5 kræver kun, at navnet er set
   mindst én gang som mand > 0,7 og aldrig som kvinde > 0,7 i samme bøtte.
   Er det set som begge dele, bliver det ikke en markør.
5. **Vægt** (parserens vægt, confidence = logistisk(vægt)):

   | Navnet set som mand > 0,7 | Vægt | Confidence | Niveau |
   |---|---:|---:|---|
   | 1 gang | 0,9 | 0,71 | sandsynlig |
   | 2–4 gange | 1,2 | 0,77 | sandsynlig |
   | ≥ 5 gange | 1,7 | 0,85 | sandsynlig (parserens loft: et fornavn alene giver aldrig »høj«) |

6. **Gentag** til ingen nye poster tilkommer. Målt: runde 2 giver kun 1 post
   mere (*Beauvois, Eugène*, fransk).
7. **Kuraterede overstyringer** i `given_name_gender_overrides.csv` vinder
   fortsat (fx *María* i spansk).
8. **Skriv listen ud** som `data/normalized/given_name_markers_male.csv` med
   `name, nationality_key, gender, weight, n_M, n_K, round`, så den kan
   inspiceres, ligesom `given_name_gender_stats.csv`.

Målt med *leave-one-out* over de 7.672 poster med fornavn og sikkerhed > 0,7.
Hver posts eget navn er trukket ud af frøet, og posten er derefter forudsagt:

| | Forudsagt mand | Rigtige | Præcision |
|---|---:|---:|---:|
| I alt | 4.028 | 4.016 | **99,7 %** |
| navnet set 1 gang | 306 | 298 | 97,4 % |
| navnet set ≥ 2 gange | 3.722 | 3.718 | 99,9 % |
| hjem | 3.663 | 3.652 | 99,7 % |
| fransk / italiensk / engelsk / østrigsk | 70 / 75 / 78 / 52 | 69 / 75 / 78 / 52 | 98,6–100 % |

Forbehold:

- Frøets sikkerhed hviler for en del af posterne selv på fornavnsstatistik
  (2.337 poster er afgjort på fornavn alene). Runden kan derfor bekræfte egne
  fejl. En strengere variant, hvor frøet kun er poster afgjort af markører og
  regler, bør måles ved siden af.
- *Preussisk, østrigsk* og *holstensk* er egne bøtter. De kunne slås sammen
  med *tysk* (afgøres sammen med nationalitetsværnet).
- Samme procedure for **kvindenavne** giver 2.501 forudsigelser, hvoraf 2.493
  er rigtige (99,7 %). Opgaven nævner kun mænd, så kvindenavne er ikke med.
  Bed om det, hvis de også skal være markører.

**Effekt i intervallet:** 146 af de 648 poster har et fornavn, og 33 af dem
rammer en mandlig markør i den rigtige bøtte (fx *Antoine, Pietro, Giuseppe,
Andrea* (italiensk), *Casimir, Erneste, Svante*). 17 af de 33 er allerede mænd
ifølge R4, så R5 tilføjer 16 nye.

### Omfang for B1, B2 og P-reglerne: beskrivelsens første sætning

Listerne nedenfor gælder **beskrivelsen (kolonne N) til første punktum**. Et
punktum tæller ikke efter et tal (»4.6.1867«), et enkelt bogstav (»f.«) eller
en forkortelse (g.m., Dr., Chr., Joh.). Parenteser fjernes først.

Sætningen skal desuden **stoppe ved et relationsord**: af, til, efter, med,
hos, ved, i, fra, paa, for, under, over, forlovet, gift, hvis, »g. 1850 m.«,
»g.m.« og semikolon. Uden det stop rammer markørerne en anden person end
posten. Det er målt mod de 7.000 poster, der har fået køn:

| Ord | Hele første sætning: M / K | Stop ved relationsord: M / K |
|---|---:|---:|
| -mester | 227 / 47 | **122 / 2** |
| -læge | 147 / 26 | **106 / 0** |
| Major | 60 / 11 | **25 / 0** |
| Oberstløjtnant | 47 / 11 | **20 / 0** |

De K'er i venstre kolonne er alle »Datter af Læge«, »g.m. Major«, »Enke efter
Murermester« osv. Det samme gælder i intervallet: *Kuntze* (»forlovet med
Organist Rieffels **Datter**«), *Metella, Cæcilia* og *Vecellio, Lucia* (»g.m.
… **Officer**«) og *Jung* (»Pension for unge **Piger**«) ville ellers få
forkert køn. Hvis du mener »til første punktum uden relationsstop«, så sig
det, men det koster disse fejl.

Komma og tankestreg stopper ikke: »Hippolog, **Staldmester** og Ridelærer«
og »Fransk Filosof, **Historiker**« er med. Prototyperne for R2–R4 afgrænsede
hovedledet snævrere (stop ved komma). Brug samme omfang som her, og tæl R2–R4 om.

### B1: mandsord i beskrivelsen (M)

Et af disse ord i sætningen giver M. Ordene med bindestreg matches som
*endelse*, de øvrige som hele ord.

| Ord | Rammer også | Ikke | I intervallet |
|---|---|---|---|
| **Vært** | | *Værtinde* (K), *Værtens* | 192, 258, 383, 514 |
| **-dreng**, **dreng**, **drenge** | Bondedreng, Fiskerdreng | | 8, 17, 149, 409, 453, 457, 466, 521 |
| **-søn**, **søn** | Kongesøn, Brodersøn, Dattersøn, Sønnesøn | | 190, 304, 375, 487, 546, 573, 602, 616, 633 |
| **kok** | | *Kokkepige* (K) | 553 |
| **-historiker** | Litteraturhistoriker, Musikhistoriker | | 53, 219, 590 |
| **filosof** | | | 474, 590 |
| **-læge** | Overlæge, Badelæge, Øjenlæge | | 223, 379, 390, 519, 606 |
| **-bonde** | Vinbonde | *Husbonde* (se nedenfor) | 615 |
| **-mester** | Kapelmester, Hofmester, Malermester, Stormester | | 46, 144, 171, 191, 208, 230, 321, 325, 429, 491, 498, 559, 630, 631, 637 |
| **-svend** | Skomagersvend | | 351 |

Målt mod de poster, der har fået køn (stop ved relationsord):

| Ord | M | K | Niveau |
|---|---:|---:|---|
| vært | 4 | 0 | høj |
| dreng | 10 | 0 | høj |
| søn | 1.075 | 2 | høj |
| læge | 106 | 0 | høj |
| filosof | 13 | 0 | høj |
| mester | 122 | 2 | sandsynlig (98,4 %) |
| historiker | 60 | 1 | sandsynlig (98,4 %) |
| kok, svend, bonde | 0–3 | 0–1 | sandsynlig (for lidt data) |

De få afgjorte »K'er« ser ud til at være fejl i den eksisterende
kategorisering eller poster, hvor beskrivelsen står for en anden person
(»Forstmester« på »Paschwitz, Frue«). **-bonde** må ikke ramme *Husbonde*
(»Margrete I, Dronning«: »Rigets Frue, Husbonde og …«): brug `\w*bonde` med
undtagelsen *husbonde*.

### B2: kvindeord i beskrivelsen (K)

| Ord | Rammer også | Ikke | I intervallet |
|---|---|---|---|
| **Pige** | Piger, Tjenestepige, Barnepige | | 646 |
| **Frøknerne** | | *Frøknerne X's* (genitiv: ejeren, ikke gruppen: række 99) | 313, 558 |
| **Værtinde** | | | 380 |
| **Hetære** | | | 346 |
| **Jomfru(en\|erne)?** | Jomfruen (»Jomfruen fra Orléans«), Jomfruerne | *Jomfruens Egede*, *Jomfruland* (steder). Mønstret er `Jomfru(en\|erne)?`, ikke `Jomfru.*` | 293 |
| **.\*datter** | Søsterdatter, Svigerdatter, Præstedatter | | 49, 142, 281 |

Målt: datter 1.110 K / 2 M, pige 6 / 0, værtinde 4 / 0, frøknerne 1 / 0. De to
M'er under *datter* er beskrivelser, der står på den forkerte post.
*.\*datter* gælder kun, hvis ordet står i sætningens hovedled efter
relationsstoppet (derfor rammes *Kuntze* ikke).

B2 overlapper R2's K-ord (Pige, Værtinde, Datter). Implementér dem som én liste.

**Rolle** (kun for ord med rolle i opgaven): *Komtesse.\** → K og Adel/Kongelig/Hof (P5); *Marquis, Pasha, Emir* → M og Adel/Kongelig/Hof (P4); *Major, Oberstløjtnant, Officer.\*, .\*korporal.\** → M og Militær (P2). B1 og B2 sætter kun køn.

### Hvorfor R4 er tilladt, men R2-lignende gæt ikke altid

Præcisionen er målt mod de poster, hvis køn er afgjort **uden** hjælp fra
beskrivelsen (kun fornavn eller label-titel; 3.256 poster). Ordet er talt som
ord, hvor hovedledet *ender på* det:

| Ord | Mænd | Kvinder | Kvindeform i registret |
|---|---:|---:|---|
| forfatter | 129 | 2 | forfatterinde (85) |
| digter | 114 | 1 | digterinde (10) |
| maler | 126 | 0 | malerinde (16) |
| lærer | 30 | 0 | lærerinde (10) |
| skuespiller | 83 | 1 | skuespillerinde (112) |
| komponist | 61 | 0 | – |
| præst | 65 | 0 | – |
| sanger | 29 | 1 | sangerinde (8) |
| officer | 10 | 1 | – |
| oversætter | 16 | 3 | oversætterinde (13) |

Konsekvenser:

- Ordene med en attesteret *-inde*-form (forfatter, digter, maler, lærer,
  skuespiller, sanger) er de sikre. Kvinder står med *-inde*, så ordet uden
  *-inde* er en mand. Præcisionen er 98–100 %.
- **Oversætter** (16/3) og **officer** (10/1) er svagere og bør kun bruges
  som niveau `sandsynlig`.
- Et ord må ikke bruges som blot *endelse* uden en liste. Ellers rammer
  *Lærereksamen* (125), *Præstegaard* (103), *Landmandsmødet* (289) og
  *Tidemand* (595) fejlagtigt.
- **R3** har nul modeksempler: blandt de 6.828 poster med afgjort køn har
  ingen mand et ord på *-inde* eller *-esse* i hovedledet. *-ske* må ikke
  bruges, fordi det rammer adjektivernes flertal (»danske«, »svenske«).
  Det er den samme regel som i dag, blot udvidet fra første ord til hele
  hovedledet.
- R1 og R2 er vurderet manuelt i intervallet, ikke målt uafhængigt.

### Placering i kaskaden

I `_lean_category`, **før** S3 (LR-mand) og før enkeltnavn-/formreglerne
(punkt 3–4 i dag):

```
R0 (Irrelevant)  →  S2 (titel i beskrivelse → fornavn → erhverv)
  →  R1  →  R2  →  R3  →  P1–P5  →  B1/B2  →  R4  →  R5 (fornavne, anden runde)  →  S3 …
```

- R3 går før P1–P5, så *Generalinde* og *Præstekone* bliver K og ikke M.
- B1 og B2 giver niveauet `høj` for ord med ≥ 99 % målt præcision og `sandsynlig` for resten (tabellerne ovenfor).
- R5 går sidst af reglerne, fordi den bruger de mænd, de andre regler lige har
  fundet, som frø.
- R1–R3 og P1–P5 giver niveauet `høj` (regel).
- R4 giver `høj` for de seks ord med *-inde*-form og `sandsynlig` for resten.
- R5 giver altid `sandsynlig`.
- `metode` = `regel (R1)` osv., og `evidens` skal citere ordet, fx
  `erhverv »skuespilforfatter« (hovedled; skuespillerinde forekommer 112 ×)`.
- Brug samme ordlister i hele pipelinen, ikke kun i intervallet.

### Forventet effekt på de 648

| | Poster |
|---|---:|
| R0 → Irrelevant (»og Frue«) | 8 |
| R1 → K (titel i label) | 8 |
| R2 → K / M | 17 / 10 |
| R3 → K | 5 |
| R4 → M | 71 (3 er også R2: 149, 466, 521) |
| P1–P4 → M (ud over R4) | 9 (91, 128, 155, 156, 296, 434, 515, 538, 600) |
| B1, B2 og de udvidede P-regler | 69 poster, heraf 49 ud over R1–R4 og P1–P4 |
| R5 → M | 33 poster (16 ud over R4) |
| Konflikter → manuelt | 1 (174) |
| **Poster med køn i alt (distinkte)** | **180 (28 %)** |
| Irrelevante (R0) | 8 |
| Forbliver til manuelt gennemsyn | ca. 460 |

Rækkerne i midten overlapper hinanden. De 180 er tallet for den samlede
mængde, talt én gang pr. post. I de 116 poster med »sandsynligvis mand« (G 0,60–0,70) rammer P1–P4
yderligere 9 (656, 670, 675, 676, 679, 688, 700, 733, 750), og B1 rammer 6 (søn 2,
historiker 1, mester 3). De flyttes til `høj` eller `sandsynlig`.

De sidste ca. 500 er ren efternavn eller sted (»Breitenburg 4.11.1840«,
»Altona 4.6.1867«) uden nogen kønsbærende ord. De kan ikke afgøres uden
kilden.

### Oplæg til ordlister

Før reglerne bygges, skal en reasoning-model (eller en manuel gennemgang)
køre over **alle hovedledsord i kolonne N** og sortere dem:

1. kvindespecifikke (tjenestepige, værtinde, mætresse …)
2. mandsspecifikke (dreng, svoger …)
3. umarkerede erhverv med en attesteret *-inde*-form (R4, `høj`)
4. umarkerede erhverv uden *-inde*-form (R4, `sandsynlig`, kun med målt
   præcision)
5. køns-neutrale (ven, vært, kunstner, passager)

Listen gemmes som `data/curated/gender_head_terms_da.csv` med kolonnerne
`term, gender, role_bucket, level, n_M, n_K, notes`, og skal kunne overstyres manuelt som
`given_name_gender_overrides.csv`.

---

### Opdeling af familiegrupper (opgave til et senere berigelsestrin)

**Opgave:** poster, der samler flere personer, skal **deles i én post pr.
person**, før kønsfordelingen bruges til noget. Kønnet hører til den enkelte
person, ikke til gruppen. Indtil delingen er gennemført er kønnet på sådan en
post foreløbigt, og posten må ikke tælles som én person i en facet.

**Markering nu:** kolonne **S, Familiegruppe**, i
`hca-personregister-redesign_gender-review.xlsx` (bygget af
`build_gender_review_excel.py`; logikken er `family_group()` i
`gender_inference_experiments.py`). Kolonnen har type og grundlag, fx
`ægtepar | label: »og Frue«`. Der er også en optælling på arket »Optælling«.
Kun label og beskrivelsens indledning tæller. »Ven af Familien Livingstone«
midt i en beskrivelse udløser ingenting.

| Type | Regel | Poster | Eksempler (Excel-række) |
|---|---|---:|---|
| ægtepar | label har »og Frue / Fru / Hustru / Mand / Hr. / Kone« | 10 | 70, 236, 251, 256, 441 |
| forældre/børn | »og Børn«, »med Datter«, »Forældre«, »og dennes Børn«, »Søster og Søsterdatter« | 9 | 49, 143, 185, 232, 405 |
| søskende | label eller beskrivelsens første ord er Brødrene, Søstrene, Frøknerne, Frøkner, Komtesser, Baronesser, Døtre, Sønner (ikke efterfulgt af et navn: »Frøknerne Rossings Pensionat« er ejeren) | 41 | 313, 444, 529, 558, 1364 |
| familie | label har »Familie(n)« eller kurateret som `family` i `person_entity_types.tsv` | 38 | 9596, 9618, 9633 |
| gruppe | kurateret som `group` | 10 | 9653, 9776, 9787 |
| flere personer | to leveårspar i label, eller »A og B« uden komma | 0 | |
| **I alt** | | **108** | |

De 108 poster har i dag disse køn: 78 *Irrelevant*, 20 *kræver manuelt
gennemsyn*, 8 *Kvindelig*, 2 *Mandlig*.

**Hvordan delingen bør gøres** (skal besluttes, når trinnet bygges):

- **ægtepar:** to poster. Efternavnet tages fra label. Manden får M og
  hustruen får K (*Frue* → K). Nye ids mintes, og den oprindelige post bliver
  stående som henvisning, jf. split-tilfældet i
  [`index-maintenance.md`](index-maintenance.md) og
  [`fused-and-duplicated-rows.md`](fused-and-duplicated-rows.md) (kun hvor der
  ikke allerede findes en post at dele ud i).
- **søskende og forældre/børn:** kan kun deles, hvis personerne er nævnt ved
  navn eller leveår (*Oxholm, de yngre Frøkner*: Mary Ann (1842–1911) …;
  *Augustenborg, Prinsesserne*: Pauline, Amalie, Sophie …). Ellers står
  antallet uvist, og posten bliver en gruppepost uden køn.
- **familie og gruppe:** deles ikke. Medlemmerne er ukendte. Posterne bliver
  ved med at være `family` / `group` og køn er *Irrelevant*.
- **Kønsregler før delingen:** R0 gælder fortsat: par og blandede grupper er
  *Irrelevant*, grupper af ét køn (Frøknerne, Komtesser) får K via B2. Kolonne
  S viser, at kønnet er foreløbigt.
- **Rækkefølge:** delingen sker **efter** R0–R5, ellers bliver de nye poster
  køngivet to gange.

---

## 3. Passager i diktatet, der ikke kunne tolkes sikkert

Disse er skrevet efter bedste skøn i afsnit 1. Bekræft eller ret dem:

1. **»Bussens MISSES«**: læst som »de, hvor *Misses* står som fornavn«
   (række 468).
2. **»Karina«** efter *tjenestepige*: læst som »en kvinde«.
3. **»Margerica. Lucy, som er fælles elskede«**: læst som *Margherita* (380,
   373 Luti) og *Elskede*, hvor ejeren er en mand (Rafael, Petrarca).
4. **»Forfatter eller som lærer mand inklusion skuespilsforfatter«**: læst
   som »forfatter og lærer, inklusive skuespilforfatter, er mænd«.
5. **»50 % Der er lede efter, så vil det jo foregå gennemgå«**: kan ikke
   tolkes. Muligvis »i denne gruppe på 0,5 er der noget at lede efter, og
   resten kræver gennemgang«.
6. **»17 den her slags sløvt ikke så grundigt gennemsnit af«**: kan ikke
   tolkes. »17« kan være række 17 (*Alfonso*, »Fiskerdreng«), og så er
   pointen, at *Dreng* er mand (R2). Det er et gæt.

---

## Bilag: det oprindelige diktat (uredigeret)

> Og har vi den der står som et fornavn egentlig en titel.
> Bussens MISSES. Det er også kvinder.
> Og i beskrivelsen så er der så niecer.
> En en kvinde.
> I den her.
> 50% Der er lede efter, så vil det jo foregå gennemgå.
> Professionsbeskrivelsen, altså kolonne n.
> Og så.
> Eventuelt ud fra.
> En reasing model så sig hvad Det er for nogle professioner Vi har og så prøve at udlede klare.
> Eller køns.
> Specifik felt, for eksempel tjenestepige, er jo altid en.
> Karina.
> Og.
> Forfatter eller som lærer mand inklusion skuespilsforfatter fordi at registret konsekvent ellers omtæller kvinder som forfatter inder altså der kan vi bruge noget negativt.
> Vi har også.
> Margerica.
> Lucy, som er fælles elskede.
> Det er så også en kvinde.
> Og en pige bliver også Sådan en kvinde.
> 17 den her slags sløvt ikke så grundigt gennemsnit af.
> Der hvor man har.
> I den nye usikre interval.
> Vi har også nogle titler som står på phonavnet og Sådan en jomfru.
> Dem skal vi også bruge til.
> Jo kvindelige former og inklusiv også for eksempel hvert ene, altså alt alle professionsformer, Der er sluttet på indeløb, skal have affyret kvindelige.
> Kategorisering.
