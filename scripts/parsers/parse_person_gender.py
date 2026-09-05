#!/usr/bin/env python3
"""
parse_person_gender.py
----------------------
Foreslår en kønskategorisering (Mandlig | Kvindelig | Endnu ubestemt) for
hver post i PERSON-REGISTRET, med en confidence score og en eksplicit liste
over de indikatorer, resultatet bygger på.

Resultatet er en FACET-kategorisering, ikke en påstand om den enkelte
persons identitet, og det skriver ikke til registrets øvrige datafelter.
"Endnu ubestemt" er en gyldig kategori — den markerer, at grundlaget ikke
rækker, ikke at der er sket en fejl.

────────────────────────────────────────────────────────────────────────────
Metode: tre gennemløb, hvor navneviden UDLEDES af registret selv
────────────────────────────────────────────────────────────────────────────

Opgaven forbyder en simpel universel navneliste og kræver, at fornavne
vurderes i national/sproglig kontekst og efter hyppighed. Derfor bruger
denne parser ingen indbygget navneliste. I stedet:

  Gennemløb 1 — strukturelle og leksikalske markører, der IKKE kræver
    navneviden: titler i label (Grevinde/Greve, Komtesse, Dronning …),
    "Datter af …"/"Søn af …" som beskrivelsens indledning, "f. <Efternavn>"
    (født/pigenavn) i label, -inde-professioner, civilstand (Enke,
    Enkemand), slægtsord og pronominer.

  Gennemløb 2 — navnestatistik udledes af gennemløb 1's sikre poster,
    bucket'et efter personens egen nationalitet (fra
    person_ethnic_descriptors.csv, kun leading+subject) plus en generel
    bucket. Et fornavn bliver først en brugbar indikator, når det har
    tilstrækkelig dækning og en tydelig skævhed i den pågældende kontekst.
    Statistikken skrives ud, så den kan inspiceres og korrigeres.

  Gennemløb 3 — alle indikatorer kombineres additivt til en samlet score.

Fordelen ved at udlede navnestatistikken frem for at hardkode den: den er
per konstruktion tilpasset netop dette registers navneskik og periode
(dansk 1800-tal med tysk/fransk/svensk islæt), den er inspicerbar, og den
kan genberegnes, når markørvægtene justeres efter intern revision.

Statistikken kan overstyres pr. (navn, nationalitet) i
data/curated/given_name_gender_overrides.csv — det er dér krydskulturelle
tilfælde som spansk "María" i mandsnavne håndteres.

────────────────────────────────────────────────────────────────────────────
Scoringsmodel
────────────────────────────────────────────────────────────────────────────

Hver indikator bidrager med en vægt i én retning. Vægtene summeres:

    score      = Σ(kvindelige vægte) − Σ(mandlige vægte)
    konflikt   = min(Σ kvindelige, Σ mandlige)
    confidence = logistisk(|score|)  ∈ [0,5 ; 1,0]

Ved reel modstrid (begge retninger har stærk evidens) dæmpes confidence
eksplicit, så posten kan ende som "Endnu ubestemt", selv om en enkelt
indikator isoleret set var stærk — netop det, opgaven kræver. Confidence
skal ikke skjule usikkerhed.

Tærskler (eksperimentelle, justeres efter evaluering):
    ≥ 0,90  høj sikkerhed
    0,70–0,89  sandsynlig
    < 0,70  Endnu ubestemt / menneskelig kontrol

Kør:
    python scripts/parsers/parse_person_gender.py
    python scripts/parsers/parse_person_gender.py --review-limit 400

Kun standardbiblioteket.
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTITIES = os.path.join(ROOT, "data", "normalized", "entities.csv")
ETHNIC = os.path.join(ROOT, "data", "normalized", "person_ethnic_descriptors.csv")
MARKERS = os.path.join(ROOT, "data", "curated", "gender_markers_da.csv")
NAME_OVERRIDES = os.path.join(ROOT, "data", "curated", "given_name_gender_overrides.csv")

OUT_GENDER = os.path.join(ROOT, "data", "normalized", "person_gender.csv")
OUT_REVIEW = os.path.join(ROOT, "data", "normalized", "person_gender_review.csv")
OUT_NAMESTATS = os.path.join(ROOT, "data", "normalized", "given_name_gender_stats.csv")

FEMALE, MALE, UNKNOWN = "Kvindelig", "Mandlig", "Endnu ubestemt"

HIGH_CONF = 0.90
PROBABLE_CONF = 0.70

# Ved hvor meget modstridende evidens confidence dæmpes, og hvor hårdt.
CONFLICT_TRIGGER = 1.5
CONFLICT_DAMPING = 0.45

# Navnestatistik: hvornår et fornavn overhovedet må bruges som indikator.
NAME_MIN_N_NAT = 3       # i en nationalitetsbucket
NAME_MIN_N_GENERAL = 5   # i den generelle bucket
NAME_MIN_SKEW = 0.85     # andel af den dominerende retning
NAME_MAX_WEIGHT = 1.7    # et fornavn alene må aldrig nå "høj sikkerhed"


# ───────────────────────────────────────────────────────────────────────────
# Indlæsning
# ───────────────────────────────────────────────────────────────────────────

def load_markers():
    if not os.path.exists(MARKERS):
        sys.exit(f"Mangler {MARKERS}")
    out = []
    with open(MARKERS, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.append({
                "category": r["category"].strip(),
                "term": r["term"].strip(),
                "gender": r["gender"].strip().upper(),
                "weight": float(r["weight"]),
                "match": r["match"].strip(),
            })
    return out


def title_terms_from(markers):
    """Titelord (fra label_title/title-markørerne) i små bogstaver.

    Bruges af split_label til at skelne "Efternavn, Frøken" (titel, intet
    fornavn) fra "Efternavn, Frederikke" (rigtigt fornavn)."""
    return frozenset(
        m["term"].lower() for m in markers
        if m["category"] in ("label_title", "title")
    )


def load_name_overrides():
    """{(navn_lower, nationality_key): (gender, weight)}"""
    out = {}
    if not os.path.exists(NAME_OVERRIDES):
        return out
    with open(NAME_OVERRIDES, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[(r["name"].strip().lower(), r["nationality_key"].strip().lower())] = (
                r["gender"].strip().upper(), float(r["weight"])
            )
    return out


def load_nationalities():
    """{entity_id: nationality_key} — kun personens EGEN nationalitet.

    position_type=leading + referent_hint=subject er den delmængde, hvor
    adjektivet beskriver posten selv ("Svensk rejsende…"), ikke en anden
    person nævnt i beskrivelsen ("g. m. den tyske maler…"). Se
    docs/data-model/person-ethnic-descriptors.md."""
    out = {}
    if not os.path.exists(ETHNIC):
        return out
    with open(ETHNIC, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("position_type") == "leading" and r.get("referent_hint") == "subject":
                out.setdefault(r["entity_id"], r["nationality_key"].strip().lower())
    return out


# ───────────────────────────────────────────────────────────────────────────
# Label-parsing
# ───────────────────────────────────────────────────────────────────────────

DATE_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")
NEE_RE = re.compile(r"\bf\.\s*([A-ZÆØÅ][\wÀ-ÿ'’-]*)")
INITIAL_RE = re.compile(r"^[A-ZÆØÅ]\.?$")
NAME_PARTICLES = {
    "von", "van", "de", "der", "den", "du", "di", "da", "del", "della",
    "le", "la", "af", "zu", "ten", "ter", "dos", "das", "y", "of",
}


def split_label(label, title_terms=frozenset()):
    """Registrets label har formen "Efternavn, Fornavn(e)[, Titel|f. X] (år–år)".

    Returnerer (efternavn, [fornavne], [øvrige segmenter]). Årstalsparentesen
    fjernes først, så den ikke forveksles med et navnesegment.

    264 poster har en TITEL stående i fornavnspositionen ("Ahlefeldt,
    Frøken", "Aldridge, Mrs.", "Ahlefeldt, Greve") — der er ingen fornavn
    registreret. Uden title_terms ville "Frøken" blive talt som et fornavn:
    kategorien ville tilfældigvis blive rigtig, men af den forkerte grund,
    indikatorteksten ville lyve ("fornavnet Frøken"), og navnestatistikken
    ville få titelord som selvstændige "navne". De flyttes derfor over i
    titel-segmenterne, hvor titel-markøren håndterer dem korrekt."""
    core = DATE_TAIL_RE.sub("", label).strip()
    parts = [p.strip() for p in core.split(",") if p.strip()]
    if not parts:
        return "", [], []
    surname = parts[0]
    given, rest = [], []
    if len(parts) > 1:
        rest = list(parts[2:])
        for tok in parts[1].split():
            t = tok.strip(".,")
            if not t or INITIAL_RE.match(tok) or t.lower() in NAME_PARTICLES:
                continue
            if t.lower() in title_terms:
                rest.append(t)
                continue
            given.append(t)
    return surname, given, rest


# ───────────────────────────────────────────────────────────────────────────
# Gennemløb 1: markører uden navneviden
# ───────────────────────────────────────────────────────────────────────────

# -inde er en stærk kvindelig endelse i dansk, MEN -minde er stednavne
# ("Kerteminde", "Brahesminde") og skal ikke matche. Ordet skal desuden
# have en vis længde, så tilfældige forekomster ikke rammer.
INDE_RE = re.compile(r"\b([A-Za-zÆØÅæøåÀ-ÿ]{5,}inde)\b")
INDE_EXCLUDE_SUFFIX = ("minde",)
# Nogle -inde-ord beskriver en relation frem for posten selv og har derfor
# større risiko for at referere til en tredjeperson i beskrivelsen.
INDE_RELATIONAL = {"veninde", "beundrerinde", "elskerinde", "svigerinde"}


# "Vor Frue Kirke"/"Frue Plads" er STEDNAVNE, ikke en kvinde. Målt i
# korpuset: 12 poster — alle mandlige sognepræster — ville ellers få en
# kvindelig Fru-markør fra deres embedsbeskrivelse. Frasen fjernes fra
# beskrivelsen før markørsøgningen i stedet for at gøre Fru-mønstret så
# snævert, at det holder op med at fange »Fru«/»Fruen« om en person.
PLACE_NOISE_RE = re.compile(
    r"\b(?:Vor\s+)?Frue\s+(?:Kirke|K\.|Plads|Sogn|Kirkes)\b|\bVor\s+Frue\b",
    re.IGNORECASE,
)


# ── Referent: hvem handler markøren om? ────────────────────────────────────
# Den vigtigste fejlkilde i dette register er markører, der beskriver en
# PÅRØRENDE frem for posten selv. Målt på beskrivelserne:
#
#   "Broder til Fru Therese Henriques, Typograf."   ← posten er broderen (M);
#                                                     »Fru« hører til søsteren
#   "hans Moder var Søster til William Howitt"      ← moderen er tredjepart
#
# Uden denne skelnen blev korrekt bestemte mænd (Broder til …) trukket i
# konflikt af et »Fru«, der slet ikke handlede om dem, og endte som
# "Endnu ubestemt". To regler følger af mønstret:
#
#   1) Slægtsord tæller kun som "X til …" eller som beskrivelsens indledning
#      — og ikke efter et ejestedord ("hans Moder").
#   2) Titler (Fru/Frøken/Madame) tæller kun PRÆDIKATIVT, altså når de ikke
#      står foran et egennavn og ikke er en LEDSAGER. "Frue i Aarhus, hos
#      hvem …" beskriver posten; "Fru Therese Henriques" navngiver en
#      anden; "Dansk Turist med Frue og Børn" ledsages af en — »med Frue«
#      betyder »sammen med [sin] hustru«, ikke »er en frue«. Fundet ved
#      Reg0058070 ("Fog", mand, fejlklassificeret Kvindelig af netop dette
#      mønster) — én forekomst i korpuset i dag, men mønsterklassen
#      (ledsagelse via "med") er den samme referentfejl som possessiv- og
#      slægtsordsværnet nedenfor, og rettes derfor generelt, ikke som en
#      punktrettelse af den ene post.
POSSESSIVE_RE = re.compile(r"\b(hans|hendes|sin|sine|deres|vor|min|dennes|med)\s+$", re.I)


def _relation_hits(desc, term):
    """»<Slægtsord> til …« eller slægtsordet som beskrivelsens første ord."""
    hits = []
    for mo in re.finditer(r"\b" + re.escape(term) + r"\w{0,2}\b", desc, re.IGNORECASE):
        if POSSESSIVE_RE.search(desc[:mo.start()]):
            continue
        if re.match(r"\s+til\b", desc[mo.end():mo.end() + 6]) or mo.start() <= 2:
            hits.append(mo)
    return hits


def _predicative_title_hits(desc, term):
    """Titel, der IKKE står foran et egennavn — altså om posten selv."""
    hits = []
    for mo in re.finditer(r"\b" + re.escape(term) + r"e?\b", desc, re.IGNORECASE):
        if POSSESSIVE_RE.search(desc[:mo.start()]):
            continue
        if re.match(r"\s*[A-ZÆØÅ]", desc[mo.end():mo.end() + 30]):
            continue  # efterfulgt af egennavn → en anden person
        hits.append(mo)
    return hits


def scan_markers(label, desc, markers, title_terms=frozenset()):
    """Alle markør-baserede indicier for én post.

    Returnerer en liste af (gender, weight, kategori, forklarende tekst)."""
    found = []
    surname, given, rest = split_label(label, title_terms)
    rest_l = [s.lower() for s in rest]
    desc = PLACE_NOISE_RE.sub(" ", desc or "")

    for m in markers:
        term_l = m["term"].lower()
        if m["match"] == "label_segment":
            # Titlen står som eget komma-segment i label, evt. med tilføjelse
            # ("Konge af –", "Prins af Slesvig-Holsten-…").
            for seg in rest_l:
                if seg == term_l or seg.startswith(term_l + " "):
                    found.append((m["gender"], m["weight"], "Titel (label)",
                                  f"Titel i label: {m['term']}"))
                    break
        elif m["match"] == "desc_prefix":
            if re.match(r"\s*" + re.escape(m["term"]) + r"\b", desc, re.IGNORECASE):
                found.append((m["gender"], m["weight"], "Slægtsrelation",
                              f"Beskrivelsen indledes med »{m['term']} af …«"))
        elif m["match"] == "desc_word":
            mo = re.search(r"\b" + re.escape(m["term"]) + r"\w{0,2}\b", desc, re.IGNORECASE)
            if mo and not POSSESSIVE_RE.search(desc[:mo.start()]):
                found.append((m["gender"], m["weight"], m["category"].capitalize(),
                              f"Ordet »{m['term']}« i beskrivelsen"))
        elif m["match"] == "desc_relation":
            if _relation_hits(desc, m["term"]):
                found.append((m["gender"], m["weight"], "Slægtsrelation",
                              f"»{m['term']} til …« — beskriver posten selv"))
        elif m["match"] == "desc_title_pred":
            if _predicative_title_hits(desc, m["term"]):
                found.append((m["gender"], m["weight"], "Titel",
                              f"»{m['term']}« brugt om posten selv (ikke foran et egennavn)"))
        elif m["match"] == "desc_word_cased":
            if re.search(r"\b" + re.escape(m["term"]) + r"\b", desc):
                found.append((m["gender"], m["weight"], "Pronomen",
                              f"Pronomen »{m['term']}« i beskrivelsen"))

    # "f. <Efternavn>" i label = født/pigenavn. Kræver stort begyndelses-
    # bogstav efter f., ellers rammer vi "f. 1808" (fødselsår).
    for seg in rest:
        mo = NEE_RE.search(seg)
        if mo:
            found.append(("K", 3.0, "Navneændring",
                          f"»f. {mo.group(1)}« i label — pigenavn/fødenavn angivet"))
            break

    # -inde-professioner. Trækkes ud som egne indicier, så evalueringen kan
    # se præcis hvilket ord der bar signalet.
    for mo in INDE_RE.finditer(desc):
        word = mo.group(1)
        wl = word.lower()
        if wl.endswith(INDE_EXCLUDE_SUFFIX):
            continue
        # Samme referent-regel som for titler: står -inde-ordet umiddelbart
        # foran et egennavn, beskriver det en ANDEN person — "Fader til
        # Fyrstinde Caroline", "Søn af Ærkehertuginde Sophie" handler begge
        # om en mand. \s+ (ikke \s*) er bevidst: efter "Forfatterinde. Datter
        # af …" står der punktum før det store bogstav, og dér er -inde-ordet
        # netop posten selv.
        if re.match(r"\s+[A-ZÆØÅ]", desc[mo.end():mo.end() + 30]):
            continue
        if POSSESSIVE_RE.search(desc[:mo.start()]):
            continue
        if wl in INDE_RELATIONAL:
            found.append(("K", 1.3, "Morfologi (-inde)",
                          f"»{word}« — kvindelig form, men relationsord (kan omtale tredjepart)"))
        else:
            found.append(("K", 2.0, "Morfologi (-inde)",
                          f"»{word}« — kvindeligt markeret professionsform"))

    return found


# ───────────────────────────────────────────────────────────────────────────
# Scoring
# ───────────────────────────────────────────────────────────────────────────

def score(indicators):
    """indicators: [(gender, weight, kategori, tekst)] → (køn, confidence, konflikt)."""
    fem = sum(w for g, w, _, _ in indicators if g == "K")
    mal = sum(w for g, w, _, _ in indicators if g == "M")
    net = fem - mal
    conflict = min(fem, mal)

    if abs(net) < 1e-9:
        # Ingen evidens, eller perfekt modstrid — begge dele er "ubestemt".
        return UNKNOWN, 0.5, conflict

    conf = 1.0 / (1.0 + math.exp(-abs(net)))
    if conflict >= CONFLICT_TRIGGER:
        # Modstridende stærk evidens må ikke skjules bag en høj score.
        conf = 0.5 + (conf - 0.5) * CONFLICT_DAMPING

    gender = FEMALE if net > 0 else MALE
    if conf < PROBABLE_CONF:
        gender = UNKNOWN
    return gender, conf, conflict


# ───────────────────────────────────────────────────────────────────────────
# Gennemløb 2: udled navnestatistik
# ───────────────────────────────────────────────────────────────────────────

def build_name_stats(seed_rows):
    """seed_rows: [(fornavne, nationality_key, køn)] fra sikre poster.

    Returnerer {(navn, nat|'_general'): Counter({'K':n,'M':n})}."""
    stats = defaultdict(Counter)
    for given, nat, gender in seed_rows:
        if gender not in (FEMALE, MALE):
            continue
        g = "K" if gender == FEMALE else "M"
        for i, name in enumerate(given):
            # Kun det ledende fornavn bærer statistik: mellemnavne i dette
            # register er ofte slægtsnavne eller opkaldelser efter en
            # person af modsat køn og ville støje statistikken til.
            if i > 0:
                break
            nl = name.lower()
            stats[(nl, "_general")][g] += 1
            if nat:
                stats[(nl, nat)][g] += 1
    return stats


def name_indicator(given, nat, stats, overrides):
    """Fornavnsindikator med nationalitetskontekst. Returnerer indicium eller None."""
    if not given:
        return None
    name = given[0]
    nl = name.lower()

    # Kurateret overstyring vinder over den udledte statistik.
    for key in ((nl, nat or ""), (nl, "*")):
        if key in overrides:
            g, w = overrides[key]
            if w <= 0:
                return ("K", 0.0, "Fornavn",
                        f"»{name}« neutraliseret i {nat or 'ukendt'} kontekst "
                        f"(kurateret overstyring — krydskulturelt navn)")
            return (g, w, "Fornavn",
                    f"»{name}« → kurateret overstyring for {nat or 'ukendt'} kontekst")

    # Nationalitetsspecifik statistik foretrækkes; ellers den generelle med
    # lavere vægt, fordi konteksten så er ukendt.
    for bucket, min_n, scale, label in (
        (nat, NAME_MIN_N_NAT, 1.0, f"{nat} kontekst"),
        ("_general", NAME_MIN_N_GENERAL, 0.75, "generel kontekst (nationalitet ukendt)"),
    ):
        if not bucket:
            continue
        c = stats.get((nl, bucket))
        if not c:
            continue
        total = c["K"] + c["M"]
        if total < min_n:
            continue
        top_g, top_n = ("K", c["K"]) if c["K"] >= c["M"] else ("M", c["M"])
        skew = top_n / total
        if skew < NAME_MIN_SKEW:
            continue
        # Vægt vokser med både skævhed og datamængde, men loftet sikrer, at
        # et fornavn ALENE aldrig kan give "høj sikkerhed".
        w = min(NAME_MAX_WEIGHT, (skew - 0.5) * 2.4 + math.log10(total) * 0.5) * scale
        if w <= 0.15:
            continue
        return (top_g, round(w, 3), "Fornavn",
                f"»{name}« → {'kvindeligt' if top_g == 'K' else 'mandligt'} i {label} "
                f"({top_n}/{total} sikre poster)")
    return None


SPOUSE_RE = re.compile(r"\bg(?:ift)?\.?\s*(?:\d{4}\s*)?m(?:ed)?\.?\s+([A-ZÆØÅ][\wÀ-ÿ'’-]+)")


def spouse_indicator(desc, nat, stats, overrides):
    """»g. 1856 m. John A.« — ægtefællens fornavn peger modsat.

    Andenordens slutning: den bygger på navnestatistikken og kan derfor
    forstærke en fejl dér. Derfor lav vægt og eksplicit mærkning."""
    mo = SPOUSE_RE.search(desc or "")
    if not mo:
        return None
    sp = mo.group(1)
    ind = name_indicator([sp], nat, stats, overrides)
    if not ind or ind[1] <= 0:
        return None
    g, w, _, _ = ind
    opposite = "M" if g == "K" else "K"
    return (opposite, min(1.0, w * 0.6), "Ægteskab",
            f"»gift med {sp}« — ægtefællens fornavn peger modsat (afledt, lav vægt)")


# ───────────────────────────────────────────────────────────────────────────
# Hovedprogram
# ───────────────────────────────────────────────────────────────────────────

def classify(row, markers, stats, overrides, nats, use_names=True, titles=frozenset()):
    label = row["label"]
    desc = row.get("description") or ""
    nat = nats.get(row["entity_id"])
    _, given, _ = split_label(label, titles)

    inds = scan_markers(label, desc, markers, titles)
    if use_names:
        ni = name_indicator(given, nat, stats, overrides)
        if ni and ni[1] > 0:
            inds.append(ni)
        si = spouse_indicator(desc, nat, stats, overrides)
        if si:
            inds.append(si)
    gender, conf, conflict = score(inds)
    return gender, conf, conflict, inds, nat


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review-limit", type=int, default=300,
                    help="Antal poster i review-CSV'en (default 300)")
    args = ap.parse_args()

    if not os.path.exists(ENTITIES):
        sys.exit(f"Mangler {ENTITIES} — kør scripts/normalization/hca_xlsx_to_csv.py først.")

    markers = load_markers()
    titles = title_terms_from(markers)
    overrides = load_name_overrides()
    nats = load_nationalities()
    with open(ENTITIES, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["entity_type"] == "person"]

    print(f"Indlæst {len(rows):,} personer, {len(markers)} markører, "
          f"{len(nats):,} med egen nationalitet, {len(overrides)} navne-overstyringer.")

    # ── Gennemløb 1 ────────────────────────────────────────────────────────
    seed = []
    seed_hits = 0
    for r in rows:
        g, conf, _, _, nat = classify(r, markers, {}, overrides, nats,
                                      use_names=False, titles=titles)
        if g in (FEMALE, MALE) and conf >= HIGH_CONF:
            _, given, _ = split_label(r["label"], titles)
            seed.append((given, nat, g))
            seed_hits += 1
    print(f"  Gennemløb 1 (kun markører): {seed_hits:,} poster med høj sikkerhed "
          f"→ grundlag for navnestatistik.")

    # ── Gennemløb 2 ────────────────────────────────────────────────────────
    stats = build_name_stats(seed)
    usable = 0
    with open(OUT_NAMESTATS, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["navn", "kontekst", "kvindelig", "mandlig", "i_alt", "skævhed", "anvendes"])
        for (nl, bucket), c in sorted(stats.items(), key=lambda kv: -(kv[1]["K"] + kv[1]["M"])):
            tot = c["K"] + c["M"]
            top = max(c["K"], c["M"])
            skew = top / tot if tot else 0
            min_n = NAME_MIN_N_GENERAL if bucket == "_general" else NAME_MIN_N_NAT
            ok = tot >= min_n and skew >= NAME_MIN_SKEW
            usable += 1 if ok else 0
            w.writerow([nl, bucket, c["K"], c["M"], tot, f"{skew:.2f}", "ja" if ok else "nej"])
    print(f"  Gennemløb 2: {len(stats):,} (navn, kontekst)-par udledt, "
          f"{usable:,} opfylder tærsklerne → {os.path.relpath(OUT_NAMESTATS, ROOT)}")

    # ── Gennemløb 3 ────────────────────────────────────────────────────────
    results = []
    for r in rows:
        g, conf, conflict, inds, nat = classify(r, markers, stats, overrides, nats,
                                                titles=titles)
        results.append({
            "entity_id": r["entity_id"],
            "label": r["label"],
            "nationalitet": nat or "",
            "koen": g,
            "confidence": round(conf, 3),
            "konflikt": round(conflict, 2),
            "antal_indikatorer": len(inds),
            "indikatorer": " | ".join(f"{k}: {t}" for _, _, k, t in inds),
            "forklaring": forklaring(g, conf, conflict, inds),
        })

    with open(OUT_GENDER, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"  Gennemløb 3: skrev {os.path.relpath(OUT_GENDER, ROOT)}")

    write_review(results, args.review_limit)
    report(results)


def forklaring(gender, conf, conflict, inds):
    if not inds:
        return ("Ingen kønsmarkerende oplysninger fundet i post eller beskrivelse. "
                "Kræver menneskelig vurdering.")
    n = len(inds)
    dirs = {("K" if g == "K" else "M") for g, w, _, _ in inds if w > 0}
    if gender == UNKNOWN and len(dirs) > 1:
        return (f"{n} indikator(er), men modstridende retninger "
                f"(konfliktstyrke {conflict:.1f}) — bevidst efterladt ubestemt "
                f"frem for at skjule usikkerheden bag en score.")
    if gender == UNKNOWN:
        return (f"{n} indikator(er), men samlet for svagt grundlag "
                f"(confidence {conf:.2f} under tærsklen 0,70).")
    retning = "kvindelig" if gender == FEMALE else "mandlig"
    if n == 1:
        return f"Én indikator peger på {retning}."
    if conflict > 0:
        return (f"{n} indikatorer peger overvejende på {retning}, "
                f"men der er også modevidens (konfliktstyrke {conflict:.1f}).")
    return f"{n} uafhængige indikatorer peger på {retning}."


def write_review(results, limit):
    """Prioriteret kø til menneskelig kontrol.

    Rækkefølgen afspejler, hvor mest udbytte ligger: modstridende evidens
    først (dér er parseren i tvivl, men har noget at gå på), derefter poster
    tæt på tærsklen, hvor en lille justering flytter kategorien."""
    def priority(r):
        if r["konflikt"] >= CONFLICT_TRIGGER:
            return (0, -r["konflikt"])
        if r["koen"] == UNKNOWN and r["antal_indikatorer"] > 0:
            return (1, -r["confidence"])
        if PROBABLE_CONF <= r["confidence"] < HIGH_CONF:
            return (2, -r["confidence"])
        return (3, 0)

    queue = [r for r in results if priority(r)[0] < 3]
    queue.sort(key=priority)
    queue = queue[:limit]
    with open(OUT_REVIEW, "w", encoding="utf-8", newline="") as f:
        cols = ["entity_id", "label", "nationalitet", "koen", "confidence", "konflikt",
                "indikatorer", "forklaring", "menneskelig_vurdering", "kommentar"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in queue:
            row = {k: r.get(k, "") for k in cols}
            # Tomme kolonner til redaktøren — udfyldes i hånden og bliver
            # senere evalueringsgrundlag (opgavens punkt 12).
            row["menneskelig_vurdering"] = ""
            row["kommentar"] = ""
            w.writerow(row)
    print(f"  Review-kø: {len(queue):,} poster → {os.path.relpath(OUT_REVIEW, ROOT)}")


def report(results):
    """Intern revision — opgavens punkt 11."""
    n = len(results)
    by = Counter(r["koen"] for r in results)
    print("\n" + "=" * 70)
    print("INTERN REVISION")
    print("=" * 70)
    print(f"\n1–3. Fordeling ({n:,} personer):")
    for k in (MALE, FEMALE, UNKNOWN):
        print(f"       {k:16} {by[k]:6,}  ({by[k]/n:5.1%})")

    print("\n4. Featurebidrag (hvor ofte indgår kategorien i en afgjort post):")
    cat = Counter()
    for r in results:
        if r["koen"] == UNKNOWN:
            continue
        for part in r["indikatorer"].split(" | "):
            if part:
                cat[part.split(":")[0]] += 1
    for k, v in cat.most_common():
        print(f"       {k:22} {v:6,}")

    print("\n6. Modstridende indikatorer:")
    confl = [r for r in results if r["konflikt"] >= CONFLICT_TRIGGER]
    print(f"       {len(confl):,} poster med konfliktstyrke ≥ {CONFLICT_TRIGGER}")
    unresolved = [r for r in confl if r["koen"] == UNKNOWN]
    print(f"       heraf {len(unresolved):,} efterladt som »{UNKNOWN}«")

    print("\n7. Dækning pr. nationalitet (top 10 efter antal):")
    per_nat = defaultdict(lambda: Counter())
    for r in results:
        per_nat[r["nationalitet"] or "(ukendt)"][r["koen"]] += 1
    for nat, c in sorted(per_nat.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
        tot = sum(c.values())
        det = tot - c[UNKNOWN]
        print(f"       {nat:14} {tot:6,} poster, {det/tot:5.1%} afgjort")

    print("\n9–10. Dækning ved forskellige cutoffs:")
    for cut in (0.70, 0.80, 0.90, 0.95):
        k = sum(1 for r in results if r["koen"] != UNKNOWN and r["confidence"] >= cut)
        print(f"       ≥ {cut:.2f}: {k:6,} poster ({k/n:5.1%} af registret)")

    print("\n5/8. Fejlkilder kan først opgøres, når review-CSV'en er udfyldt")
    print("     manuelt — se punkt 12 i opgaven. Stikprøven nedenfor er")
    print("     udgangspunktet for den kontrol.\n")


if __name__ == "__main__":
    main()
