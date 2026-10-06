#!/usr/bin/env python3
"""
gender_head_rules.py
--------------------
Ordregler for de poster, parseren efterlader som »Endnu ubestemt«, efter
docs/gender-unclear-dictations.md, afsnit 2:

    R0  par og blandede grupper → Irrelevant; grupper af ét køn får kønnet
    R1  titel i label (Jomfru, Mile, Misses, Madame …)               K
    R2  slægts- og rolleord i hovedleddet (Søster, Datter, Broder …)  K / M
    R3  kvindelig form på -inde / -esse                               K
    P1–P5  ord, der sætter både køn og rolle (præst, løjtnant, Abbé,
           Marquis, Komtesse)                                         K / M + rolle
    B1/B2  rene kønsord i hovedleddet (-søn, -mester, -pige, -datter) K / M
    R4  umarkeret erhverv (Forfatter, Maler …; kvinder står med -inde) M
    R5  fornavne i anden runde: navne set som mand > 0,7 og aldrig som
        kvinde > 0,7 i samme etniske bøtte                           M

Rækkefølgen er prioriteten, og S2-kaskaden (titel → fornavn → erhverv) går
forrest. Første regel med svar vinder; giver to regler modsat køn, kræver
posten manuelt gennemsyn. Ordlisterne står i data/curated/gender_head_terms_da.csv
(R3 og R5 er kode).

Modulet er et bibliotek; det bruges af gender_inference_experiments.py og
build_gender_review_excel.py.
"""

import csv
import os
import re
from collections import Counter, defaultdict

import gender_inference_experiments as G

P = G.P
K, M = G.K, G.M
TERMS = os.path.join(G.ROOT, "data", "curated", "gender_head_terms_da.csv")
RULE_ORDER = ("S2", "R1", "R2", "R3", "P1", "P2", "P3", "P4", "P5", "B1", "B2", "R4")
LEVEL_CONF = {"høj": 0.95, "sandsynlig": 0.80}
# R5: vægt og confidence (logistisk(vægt)) efter, hvor mange gange navnet er set.
R5_STEPS = ((5, 1.7, 0.85), (2, 1.2, 0.77), (1, 0.9, 0.71))

TOKEN_RE = re.compile(r"[A-Za-zÆØÅæøåÀ-ÿ]+(?:'[a-z]+)?")


# ───────────────────────────────────────────────────────────────────────────
# Hovedleddet
# ───────────────────────────────────────────────────────────────────────────

# Et punktum afslutter ikke sætningen efter et tal (»4.6.1867«), et enkelt
# bogstav (»f.«, »J. H.«) eller en forkortelse.
ABBREV = {"dr", "chr", "joh", "jac", "wilh", "heinr", "frdr", "fr", "hr", "nr", "st", "jr",
          "sr", "ca", "cand", "stud", "theol", "jur", "phil", "med", "mag", "polyt", "art",
          "kgl", "fhv", "tit", "prof", "geh", "etc", "bl", "ass", "aug", "forf", "pseud",
          "kapt", "ltn", "sen", "jun", "dav", "dansk", "kbh", "nov", "dec", "okt", "sept",
          "jan", "febr", "aarh", "gl", "egl", "o", "s", "p"}
# Relationsord: herfra handler teksten om en anden person end posten
# (»forlovet med Organist Rieffels Datter«, »Pension for unge Piger«).
STOP_RE = re.compile(
    r"\b(?:af|til|efter|med|hos|ved|i|fra|paa|på|for|under|over|forlovet|gift|hvis|se)\b"
    # »g. 1850 m.«, »g. 1° 1779 m.«, »g.1823-28 m.«, »g.m.«
    r"|\bg\.\s*(?:[\d°–-]+\s*)*m\b|;", re.I)


def first_sentence(desc):
    d = re.sub(r"\([^)]*\)", " ", desc or "")
    d = P.PLACE_NOISE_RE.sub(" ", d)
    for mo in re.finditer(r"\.", d):
        before = re.search(r"([\wÀ-ÿ]+)$", d[:mo.start()])
        w = before.group(1) if before else ""
        if not w or w.isdigit() or len(w) == 1 or w.lower() in ABBREV:
            continue
        rest = d[mo.end():]
        if not rest.strip() or re.match(r"\s+[A-ZÆØÅ»]", rest):
            return d[:mo.start()]
    return d


def head_clause(desc):
    """Beskrivelsens første sætning, stoppet ved første relationsord. Tom, hvis
    beskrivelsen begynder med et citat (så beskriver den ikke posten)."""
    if (desc or "").lstrip().startswith(("»", "«", '"')):
        return ""
    s = first_sentence(desc)
    mo = STOP_RE.search(s)
    return s[:mo.start()] if mo else s


def clause_tokens(desc):
    return [t.lower().split("'")[0] for t in TOKEN_RE.findall(head_clause(desc))]


def label_tokens(label, titles):
    """Fornavnsfelt og label-segmenter efter efternavnet (titler, »Abbé de l'«).
    Segmenter med »f. X« (pigenavn: »Rahbek, f. Major«) tæller ikke."""
    _, given, rest = P.split_label(label, titles)
    toks = [g.lower().strip(".") for g in given]
    for seg in rest:
        if P.NEE_RE.search(seg) or seg.strip().lower().startswith("f."):
            continue
        toks += [t.lower().split("'")[0] for t in TOKEN_RE.findall(seg)]
    return toks


# ───────────────────────────────────────────────────────────────────────────
# Ordlister
# ───────────────────────────────────────────────────────────────────────────

def load_terms(path=TERMS):
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f)]


def _match(tok, term, how):
    if how == "exact":
        return tok == term
    if how == "suffix":
        return tok.endswith(term)
    if how == "prefix":
        return tok.startswith(term)
    if how == "contains":
        return term in tok
    raise ValueError(how)


# Ord, der ser ud som en regel, men ikke er det.
NOT_A_TERM = {"husbonde", "værtens", "kokkepige", "minde", "blinde", "linde", "kinde",
              "vinde", "finde", "binde", "tinde", "skinde", "adresse", "interesse",
              "messe", "presse", "delikatesse"}
INDE_RE = re.compile(r"^[a-zæøåà-ÿ]{3,}inde$")
ESSE_RE = re.compile(r"^[a-zæøåà-ÿ]{3,}esse$")


def r3_hit(tok, in_label):
    if tok in NOT_A_TERM or tok.endswith("minde"):
        return False
    return bool(INDE_RE.match(tok)) or (not in_label and bool(ESSE_RE.match(tok)))


def fem_form_counts(persons):
    """Hvor mange gange hvert -inde-ord står i registrets beskrivelser (til
    R4's begrundelse: »skuespillerinde forekommer 112 ×«)."""
    c = Counter()
    for p in persons:
        for t in TOKEN_RE.findall(p["desc"]):
            t = t.lower()
            if t.endswith("inde"):
                c[t] += 1
    return c


class Context:
    def __init__(self, persons, titles, overrides, name_lookup=None, terms=None):
        self.titles = titles
        self.overrides = overrides
        self.name_lookup = name_lookup
        self.terms = terms or load_terms()
        self.by_rule = defaultdict(list)
        for t in self.terms:
            self.by_rule[t["rule"]].append(t)
        self.fem = fem_form_counts(persons)


# ───────────────────────────────────────────────────────────────────────────
# R0 og grupper af ét køn
# ───────────────────────────────────────────────────────────────────────────

GROUP_F = re.compile(r"\b(?:Frøknerne|Frøkner|Søstrene|Søstre|Komtesserne|Komtesser|"
                     r"Baronesserne|Baronesser|Døtre|Prinsesserne|Damerne|Piger)\b")
GROUP_M = re.compile(r"\b(?:Brødrene|Brødre|Sønner|Prinserne|Herrerne|Drenge)\b")


def single_gender_group(label, desc):
    """K/M for en gruppe af ét køn (»Hierta, Frøknerne«, »Grimm, Brødrene«), ellers None.
    Kun etiketten og beskrivelsens begyndelse tæller; »Frøknerne Rossings
    Pension« (genitiv) er ejeren, ikke gruppen."""
    head = (desc or "").strip()[:40]
    hits = set()
    for txt in (label or "", head):
        for rx, g in ((GROUP_F, K), (GROUP_M, M)):
            mo = rx.search(txt)
            if mo and not re.match(r"\s+[A-ZÆØÅ][\wÀ-ÿ]*s\b", txt[mo.end():]):
                if txt is head and mo.start() > 12:
                    continue
                hits.add(g)
    return hits.pop() if len(hits) == 1 else None


def r0_reason(fam_kind, fam_ground):
    """Par og blandede grupper er irrelevante for køn (R0)."""
    if fam_kind == "ægtepar":
        return "R0: ægtepar (" + fam_ground + ")"
    if fam_kind == "forældre/børn" and "Søster og Søsterdatter" not in fam_ground:
        return "R0: forældre og børn (" + fam_ground + ")"
    if fam_kind == "søskende" and "Søskende" in fam_ground:
        return "R0: søskende af begge køn (" + fam_ground + ")"
    return None


# ───────────────────────────────────────────────────────────────────────────
# Regelstemmer
# ───────────────────────────────────────────────────────────────────────────

def _find(t, ctoks, ltoks, raw):
    """(ord, sted) for første ord, der rammer termen t, ellers None."""
    scopes = {"desc": [ctoks], "label": [ltoks], "both": [ctoks, ltoks]}[t["scope"]]
    for toks in scopes:
        for tok in toks:
            if tok in NOT_A_TERM or not _match(tok, t["term"], t["match"]):
                continue
            if t["gender"] == M and r3_hit(tok, False):
                continue  # Generalinde, Majorinde: R3 vinder
            if tok == "frøknerne" and re.search(r"Frøknerne\s+[A-ZÆØÅ][\wÀ-ÿ]*s\b", raw):
                continue  # genitiv: ejeren, ikke gruppen
            return tok, "label" if toks is ltoks else "hovedled"
    return None


def _term_votes(rule, ctoks, ltoks, ctx, raw):
    out = []
    for t in ctx.by_rule[rule]:
        hit = _find(t, ctoks, ltoks, raw)
        if not hit:
            continue
        tok, where = hit
        ev = f"»{tok}« ({where})"
        if rule == "R4" and t["level"] == "høj":
            n = ctx.fem.get(t["term"] + "inde", 0)
            ev = f"erhverv »{tok}« ({where}; {t['term']}inde forekommer {n} ×)"
        out.append((t["gender"], rule, t["level"], ev, t["role_bucket"]))
    return out


def rule_votes(p, ctx, s2=None):
    """Alle regelstemmer for posten i prioritetsorden:
    [(køn, regel, niveau, evidens, rolle)]. s2 = (køn, grundlag) fra S2."""
    votes = []
    if s2 and s2[0]:
        votes.append((s2[0], "S2", "høj", s2[1], ""))
    raw = head_clause(p["desc"])
    ctoks = clause_tokens(p["desc"])
    ltoks = label_tokens(p["label"], ctx.titles)
    g = single_gender_group(p["label"], p["desc"])
    if g:
        votes.append((g, "B2" if g == K else "B1", "høj", "gruppe af ét køn", ""))
    r3 = r3_find(raw, ltoks)
    for rule in RULE_ORDER[1:]:
        if rule == "R3":
            if r3:
                votes.append((K, "R3", "høj", f"kvindelig form »{r3}«", ""))
            continue
        if rule == "R4" and r3:
            continue  # »Forfatterinde og Oversætter«: det umarkerede ord er sekundært
        votes += _term_votes(rule, ctoks, ltoks, ctx, raw)
    return votes


def r3_find(raw, ltoks):
    """Første -inde/-esse-ord i hovedleddet (ikke foran et egennavn: »Grevinde
    Elise Moltke-Hvitfeldts Sjælesørger« handler om en anden) eller -inde i
    label-segmenterne."""
    for mo in TOKEN_RE.finditer(raw):
        tok = mo.group(0).lower().split("'")[0]
        if r3_hit(tok, False) and not re.match(r"\s+[A-ZÆØÅ]", raw[mo.end():]):
            return tok
    return next((t for t in ltoks if r3_hit(t, True)), None)


def settle(votes):
    """(køn, niveau, metode, grundlag, rolle) eller None; ('konflikt', …) ved uenighed."""
    if not votes:
        return None
    roles = "; ".join(dict.fromkeys(v[4] for v in votes if v[4]))
    if len({v[0] for v in votes}) > 1:
        return ("konflikt", "", "regler uenige",
                "; ".join(f"{v[1]} {v[0]}: {v[3]}" for v in votes), roles)
    first = votes[0]
    extra = [f"{v[1]}: {v[3]}" for v in votes[1:]]
    why = f"{first[1]}: {first[3]}" + (" (også " + "; ".join(extra) + ")" if extra else "")
    return first[0], first[2], f"regel ({first[1]})", why, roles


# ───────────────────────────────────────────────────────────────────────────
# R5: fornavne i anden runde
# ───────────────────────────────────────────────────────────────────────────

def bucket(nat):
    return "hjem" if (nat or "") in G.HOME_NATS else nat


NAME_RE = re.compile(r"^[A-ZÆØÅÀ-Þ][a-zæøåß-ÿ'’-]+$")


def name_key(p):
    """(fornavnsvariant, bøtte); kun for et ord, der ligner et fornavn (ikke
    »(1816–1893)« eller »(Pseud« fra en løs parentes i labelen)."""
    if not p["given"] or not NAME_RE.match(p["given"][0]):
        return None
    return G.variant(p["given"][0]), bucket(p["nat"])


def overridden(p, overrides):
    nl = p["given"][0].lower()
    for key in ((nl, p["nat"] or ""), (nl, "*")):
        if key in overrides:
            g, w = overrides[key]
            return g != "M" or w <= 0
    return False


def r5_lookup(p, seed_m, seed_k, overrides):
    k = name_key(p)
    if not k or overridden(p, overrides):
        return None
    n_m, n_k = seed_m.get(k, 0), seed_k.get(k, 0)
    if n_m < 1 or n_k > 0:
        return None
    for lo, w, conf in R5_STEPS:
        if n_m >= lo:
            return w, conf, n_m


# ───────────────────────────────────────────────────────────────────────────
# Afgørelse af de ubestemte
# ───────────────────────────────────────────────────────────────────────────

def _cat(g, conf):
    if conf >= G.LEAN_BELOW:
        return P.FEMALE if g == K else P.MALE
    return G.CAT_LEAN_F if g == K else G.CAT_LEAN_M


def decide_unknowns(persons, todo, pred, ctx, manual_below=0.60, female_min=1.01,
                    base_rate_male=False):
    """Kategori for hver ubestemt post i `todo` (entity_id'er).

    pred: {entity_id: forudsigelsesrække fra G.infer_unknown} (kan mangle for
    poster uden for modellens grundlag). Returnerer ({eid: dict}, r5_rows)."""
    by_id = {p["id"]: p for p in persons}
    out = {}

    def put(eid, cat, conf, how, why, role=""):
        out[eid] = {"kategori": cat, "sikkerhed": round(conf, 4), "metode": how,
                    "grundlag": why, "rolle": role}

    # 1. S2 + R1–R4, P1–P5, B1/B2
    for eid in todo:
        p, r = by_id[eid], pred.get(eid)
        s2 = None
        if r and r["S2_kaskade"]:
            s2 = (r["S2_kaskade"], r["S2_grundlag"])
        res = settle(rule_votes(p, ctx, s2))
        if r and r["S2_grundlag"].startswith("konflikt"):
            res = ("konflikt", "", "regler uenige", r["S2_grundlag"], "")
        if res is None:
            continue
        g, level, how, why, role = res
        if g == "konflikt":
            put(eid, G.CAT_MANUAL, G.MANUAL_CONF, how, why, role)
        else:
            conf = LEVEL_CONF[level]
            put(eid, _cat(g, conf), conf, how, why, role)

    # 2. R5: frøet er alle sikre mænd (> 0,7) og — til udelukkelse — alle
    #    sikre kvinder, både parserens og dem, reglerne lige har afgjort.
    seed_m, seed_k = Counter(), Counter()
    for p in persons:
        k = name_key(p)
        if not k:
            continue
        d = out.get(p["id"])
        if p["existing"] and p["existing_conf"] > 0.7:
            (seed_m if p["existing"] == M else seed_k)[k] += 1
        elif d and d["sikkerhed"] > 0.7 and d["kategori"] in (P.MALE, P.FEMALE):
            (seed_m if d["kategori"] == P.MALE else seed_k)[k] += 1
    first_round = {k: 0 for k in seed_m}
    rnd = 0
    while True:
        rnd += 1
        new = []
        for eid in todo:
            if eid in out:
                continue
            p = by_id[eid]
            hit = r5_lookup(p, seed_m, seed_k, ctx.overrides)
            if hit:
                w, conf, n = hit
                new.append(p)
                put(eid, _cat(M, conf), conf, "regel (R5)",
                    f"R5: fornavn »{p['given'][0]}« set som mand {n} × "
                    f"(bøtte {bucket(p['nat'])}, runde {rnd}, vægt {w})")
        for p in new:
            k = name_key(p)
            seed_m[k] += 1
            first_round.setdefault(k, rnd)
        if not new:
            break
    r5_rows = []
    for (name, b), n_m in sorted(seed_m.items()):
        if seed_k.get((name, b), 0) == 0:
            w = next(w for lo, w, _ in R5_STEPS if n_m >= lo)
            r5_rows.append({"name": name, "nationality_key": b, "gender": "M", "weight": w,
                            "n_M": n_m, "n_K": 0, "round": first_round.get((name, b), 0)})

    # 3. Det, reglerne ikke afgør: S3-modellen og grundraten som før.
    for eid in todo:
        if eid in out:
            continue
        p, r = by_id[eid], pred.get(eid)
        if r is None:
            put(eid, G.CAT_MANUAL, G.MANUAL_CONF, "ingen evidens",
                "uden for modellens grundlag og ingen regel slog til")
            continue
        cat, conf, how, why = G.lean_category(p, r, ctx.name_lookup, None, None,
                                              manual_below, female_min, base_rate_male)
        put(eid, cat, conf, how, why)
    return out, r5_rows


def disagreements(persons, ctx, irrelevant=()):
    """Poster, parseren har afgjort (≥ 0,70), hvor en ordregel siger det
    modsatte (fx »Lafayette, Marie Joseph Paul …, Marquis« som Kvindelig).
    Overskriver intet; skrives ud til kontrol."""
    rows = []
    for p in persons:
        if not p["existing"] or p["id"] in irrelevant:
            continue
        votes = [v for v in rule_votes(p, ctx) if v[0] != p["existing"]]
        if votes:
            rows.append({"entity_id": p["id"], "label": p["label"], "beskrivelse": p["desc"][:140],
                         "eksisterende_køn": p["existing"],
                         "regler_siger": "; ".join(f"{v[1]} {v[0]}: {v[3]}" for v in votes)})
    return rows


def measure_terms(persons, ctx):
    """Hver ordregel målt mod de poster, parseren har afgjort (n_M, n_K)."""
    cnt = defaultdict(Counter)
    for p in persons:
        if not p["existing"]:
            continue
        raw = head_clause(p["desc"])
        ctoks = clause_tokens(p["desc"])
        ltoks = label_tokens(p["label"], ctx.titles)
        r3 = r3_find(raw, ltoks)
        for rule in RULE_ORDER[1:]:
            if rule == "R3":
                if r3:
                    cnt[("R3", "-inde/-esse")][p["existing"]] += 1
                continue
            if rule == "R4" and r3:
                continue
            for t in ctx.by_rule[rule]:
                if _find(t, ctoks, ltoks, raw):
                    cnt[(rule, t["term"])][p["existing"]] += 1
    gender = {(t["rule"], t["term"]): t["gender"] for t in ctx.terms}
    gender[("R3", "-inde/-esse")] = K
    return [{"regel": r, "term": t, "køn": gender[(r, t)], "n_M": c[M], "n_K": c[K],
             "præcision": round(c[gender[(r, t)]] / (c[M] + c[K]), 4)}
            for (r, t), c in sorted(cnt.items())]
