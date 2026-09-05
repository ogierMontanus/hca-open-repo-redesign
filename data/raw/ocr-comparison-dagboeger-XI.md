# OCR-sammenligning: H.C. Andersens Dagbøger XI (Personregister)

**Filer sammenlignet**
1. `andersen-hc_dagboeger_11.pdf` (444 sider) — OCR'et med **ABBYY FineReader PDF 15**, 2023-03-27.
2. `dagbog-bd-11-3408_Claus-OCR test ABBYY.pdf` (445 sider) — OCR'et med en **ældre/anden ABBYY FineReader PDF**-version (ingen versionsnummer i producer-metadata), 2026-09-01. Titel-metadata har en tastefejl ("H. **A.** Andersens" i stedet for "H. C. Andersens").

Begge er scanninger af samme bind (Personregister, spalte 1–796), ikke bind 12 som oprindeligt antaget — filnavnene er misvisende, men indholdet er identisk værk.

## A) Rå sammenligning og layout-mapping

Fil 2 har ét ekstra forside ("Claus Rønlevs bibliotek"-side), hvilket giver en konstant **side-offset på +1** (side *n* i fil 1 ≈ side *n+1* i fil 2). Offsettet er verificeret stabilt gennem hele bogen (`difflib`-similaritet 0,96–0,998 på stikprøver fra side 10 til 443). Efter offset-korrektion er sideindholdet praktisk talt identisk i struktur; gennemsnitlig tegn-similaritet over alle 444 sider er **0,967**.

Lave similaritetsscorer (~0,02–0,7) er koncentreret om **stamtavle-opslagene** (Collin, Melchior m.fl., ca. side 26–42 og enkelte senere opslag) — foldeud-genealogitabeller med grafisk layout, hvor begge motorer har markant sværere ved at fastholde læserækkefølge og gengiver specialtegnet "β" (gift med) helt forskelligt og fejlagtigt (fil 1: "P"; fil 2: "(3"/"/3"/"13"). Disse sider er ikke egnede til tegn-for-tegn sammenligning og er udeladt af tal-kvalitetsvurderingen nedenfor.

## C) Stikprøve: talgenkendelse (spaltehenvisninger)

Det egentlige register (person-opslag med spaltetal, fx "VIII 104 106 128…") er hvor talkvaliteten betyder mest. Stikprøver verificeret mod sidebilleder:

| Side | Fil 1 (2023, v15) | Fil 2 (2026, "test") | Facit (billede) |
|---|---|---|---|
| 57/58 | `SOS-OO 402-03`, `88 05 07 00 100` | `398-99 402-03`, `88 95 97 99 100` | Fil 2 korrekt |
| 57/58 | `III 330-40` | `III 339-40` | Fil 2 korrekt |
| 57/58 | `I 400` | `I 499` | Fil 2 korrekt |
| 117/118 (VIII) | `704 706 728 729 131 733 736 139 747 743 744…` | `104 106 128 129 131 133 136 139 141 143 144…` | Fil 2 korrekt (fil 1: næsten hvert ledende "1" → "7") |
| 117/118 (IX) | `IX 76 139` | `IX 16 139` | Fil 2 korrekt |
| 117/118 (VI) | `740 260` | `140 260` | Fil 2 korrekt |

Systematisk optælling af korte diff-segmenter, hvor den ene side giver et "rent" tal og den anden ikke, over hele bogen (stamtavle-sider udelukket): **41 tilfælde hvor fil 2 er korrekt / kun 21 hvor fil 1 er "korrekt"** — og de fleste af de 21 viser sig ved nærmere eftersyn selv at være fejl i fil 1 (bogstav i stedet for ciffer, fx "l"/"I" for "1", "S" for "3"), som blot ikke blev fanget af det numeriske filter.

**Konklusion om cifferfejl:** Den frygtede "1 vs. 7"-forveksling (og beslægtet "0 vs. 9", "3 vs. S") er reel og hyppig — men den rammer overvejende **fil 1** (den 2023-processerede ABBYY v15-fil), ikke fil 2. På side 117 alene mister fil 1 ni spaltehenvisninger til denne fejltype i én kolonne.

## D) Relative styrker

- **Fil 2 ("test ABBYY", 2026)**: markant bedre cifferpræcision i det løbende register — det kritiske indhold for opslag/søgning. Har én ekstra reklameside og en titel-metadata-tastefejl (kosmetisk, ikke tekstlag).
- **Fil 1 (v15, 2023)**: renere metadata og korrekt titel; ingen systematisk fordel fundet i selve registerteksten. Begge motorer klarer stamtavle-siderne dårligt og forskelligt.

## E) Anbefaling til høstning af det bedste fra begge

1. **Brug fil 2's tekstlag som primær kilde** for personregisterets spaltetal (side 43 og frem i fil 1-nummerering, dvs. efter stamtavlerne) — det er den mere pålidelige kilde for netop den information, registret findes for.
2. **Byg en offset-korrigeret, side-for-side merge**: json/tsv med `(side, fil1_tekst, fil2_tekst)`, side-forskudt med +1 som fastlagt ovenfor. Brug fil 1 kun til metadata (titel, forfatter) og som fallback hvor fil 2 mangler en side.
3. **Automatisk konfliktdetektion** frem for blind overtagelse: kør et regex-baseret "tal-sandsynligheds"-filter (som brugt i denne analyse — flag chunks hvor det ene tekstlag er rent numerisk og det andet ikke) og lad de ca. 300 flagede segmenter gennemgås manuelt eller ved en tredje uafhængig OCR-kørsel (fx Tesseract eller Google Document AI) som "tie-breaker" på uenige, begge-numeriske tilfælde (fx `11` vs. `77` på side 50).
4. **Undlad at stole på nogen af tekstlagene for stamtavle-siderne**; disse bør enten transskriberes manuelt eller udelades fra automatisk tal-udtræk, da begge OCR-lag fejler på samme grafiske layout.
5. **Rekør fil 2 gennem en nyere ABBYY-version (v15/v16)** hvis muligt — dens højere grundkvalitet på almindelig tekst kombineret med v15's typisk bedre lagdelte layoutgenkendelse kunne formentlig lukke det sidste hul på stamtavle-siderne.
