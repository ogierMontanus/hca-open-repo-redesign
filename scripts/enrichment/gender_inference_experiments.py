#!/usr/bin/env python3
"""
gender_inference_experiments.py
-------------------------------
Eksperimentfase: hvilke eksisterende datafeatures kan bedst forudsige
kønskategorien for de ~3.200 personer, som parse_person_gender.py efterlader
som "Endnu ubestemt"?

Dette er et ANALYSESCRIPT, ikke et pipeline-trin. Det skriver intet til
data/normalized/ og rører ikke den eksisterende kategorisering. Resultaterne
lander i data/review/gender_inference/ og fortolkes i
docs/reports/gender-inference-experiment.md.

────────────────────────────────────────────────────────────────────────────
Det centrale metodeproblem: "ground truth" er selv infereret
────────────────────────────────────────────────────────────────────────────

De ~2/3 kategoriserede personer er IKKE en uafhængig registrering. De er
output fra parse_person_gender.py, som bl.a. bruger fornavnet. 2.305 poster
er kategoriseret på fornavnet ALENE. At måle en fornavnsmodel mod dem er at
måle parseren mod sig selv.

Derfor evalueres hver feature-familie kun mod REFERENCEETIKETTER, der står
uden den familie: parserens indikatorer genberegnes for hver post, familien
fjernes, og etiketten bruges kun, hvis den resterende evidens stadig giver
samme køn med confidence ≥ 0,90. Familier:

    NAME     fornavne (og ægtefællens fornavn)
    LABEL    titel/født-navn i label  ("Grevinde", "f. Hansen")
    DESC     ord i beskrivelsen        ("Datter af", "Skuespillerinde", "hun")

Efternavn, nationalitet, roller og henvisningsmetadata indgår ikke i
parserens evidens og evalueres mod alle sikre etiketter.

Kør:
    python scripts/enrichment/gender_inference_experiments.py

Kræver pandas, numpy og scikit-learn (ikke i requirements.txt, fordi
scriptet ikke er et pipeline-trin).
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, KFold

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parse_person_gender as P  # noqa: E402

ROOT = P.ROOT
OUT = os.path.join(ROOT, "data", "review", "gender_inference")
ROLE = os.path.join(ROOT, "data", "normalized", "person_role.csv")
REFS = os.path.join(ROOT, "data", "normalized", "references.csv")

K, M = "K", "M"
TMAP = {}
# Nationaliteter, hvis navneskik fornavnsleksikonet faktisk er lært af.
HOME_NATS = {"", "dansk", "norsk", "svensk", "tysk", "islandsk", "færøsk"}
SEED = 20261005
THRESHOLDS = (0.70, 0.80, 0.90, 0.95, 0.98, 0.99)
N_FOLDS = 5

os.makedirs(OUT, exist_ok=True)


# ───────────────────────────────────────────────────────────────────────────
# Normalisering
# ───────────────────────────────────────────────────────────────────────────

def strip_accents(s):
    s = s.lower().replace("æ", "ae").replace("ø", "o").replace("å", "aa")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def exact(s):
    return strip_accents(s)


VARIANT_RULES = [("ph", "f"), ("th", "t"), ("ch", "k"), ("ck", "k"), ("c", "k"),
                 ("w", "v"), ("y", "i"), ("z", "s"), ("q", "k")]


def variant(s):
    """Stavevariantnøgle: Christian=Kristian, Sophie=Sofie, Frederikke=Frederike.
    Målt effekt rapporteres; nøglen er bevidst grov."""
    s = strip_accents(s)
    for a, b in VARIANT_RULES:
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


# ───────────────────────────────────────────────────────────────────────────
# Indlæsning og referenceetiketter
# ───────────────────────────────────────────────────────────────────────────

FAMILY = {
    "Fornavn": "NAME", "Ægteskab": "NAME",
    "Titel (label)": "LABEL", "Navneændring": "LABEL",
}
STUB_RE = re.compile(r"(?:,|^|\s)\s*se(?: også)?:?\s+[A-ZÆØÅ]", re.I)
ENTITY_TYPES = os.path.join(P.ROOT, "data", "curated", "person_entity_types.tsv")
NOT_A_PERSON = {"crossReference", "crossReferenceMalformed", "family", "group",
                "organisation", "relationalPlaceholder", "animal"}
GROUP_RE = re.compile(
    r"\b(Frøknerne|Familien|Brødrene|Søstrene|Prinsesserne|Prinserne|Damerne|"
    r"Herrerne|frères|Børnene|Kvartetsangere|Selskab|Firma)\b", re.I)
PLURAL_DESC_RE = re.compile(r"^\s*(Døtre|Sønner|Brødre|Søstre|Børn)\b")


def load_entity_types():
    out = {}
    if os.path.exists(ENTITY_TYPES):
        with open(ENTITY_TYPES, encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                out[r["RegistryTitle"].strip()] = r["29_entityType"].strip()
    return out


def exclusion_reason(label, desc, given, etypes):
    """Poster, hvor et køn ikke giver mening: ikke en enkeltperson, eller en
    henvisning/fejlsegmenteret række. De udelades fra både træning,
    evaluering og inferens og bør markeres som 'ikke relevant'."""
    et = etypes.get(label.strip())
    if et in NOT_A_PERSON:
        return "kurateret: " + et
    if label.lstrip().startswith(("–", "-")):
        return "fejlsegmenteret/relationel label"
    if STUB_RE.search(label) and not desc.strip():
        return "henvisningsstub"
    if GROUP_RE.search(label) or PLURAL_DESC_RE.search(desc) or \
            re.search(r"\s(og|&)\s", " ".join(given)):
        return "gruppe/flere personer"
    return None
YEARS_RE = re.compile(r"\((?:[^)]*\d{3,4}[^)]*)\)\s*$")


def family_of(cat):
    return FAMILY.get(cat, "DESC")


# Referenceetiketter kræver samme sikkerhed, som parseren selv bruger til at
# kategorisere (0,70). Et fornavn alene kan pr. konstruktion højst give 0,845,
# så et krav på 0,90 ville udelukke alle navne-etiketter. REF_CONF kan sættes
# til 0,90 for en følsomhedsanalyse (--strict).
REF_CONF = P.PROBABLE_CONF


def label_from(inds, min_conf=None):
    g, conf, _ = P.score(inds)
    if g == P.UNKNOWN or conf < (REF_CONF if min_conf is None else min_conf):
        return None
    return K if g == P.FEMALE else M


def direction(inds):
    """Retningen alene, uden tærskel (til sammenligning af evidensfamilier)."""
    fem = sum(w for g, w, _, _ in inds if g == "K")
    mal = sum(w for g, w, _, _ in inds if g == "M")
    return None if fem == mal else (K if fem > mal else M)


def load():
    markers = P.load_markers()
    titles = P.title_terms_from(markers)
    overrides = P.load_name_overrides()
    nats = P.load_nationalities()
    with open(P.ENTITIES, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["entity_type"] == "person"]
    with open(P.OUT_GENDER, encoding="utf-8") as f:
        existing = {r["entity_id"]: r for r in csv.DictReader(f)}
    roles = {}
    with open(ROLE, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            roles[r["entity_id"]] = [x for x in r["roller"].split("|") if x.strip()]
    nref, vols = Counter(), defaultdict(set)
    with open(REFS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            nref[r["entity_id"]] += 1
            vols[r["entity_id"]].add(r["vol"])

    # Genskab parserens navnestatistik præcis som den køres (gennemløb 1+2).
    seed = []
    for r in rows:
        g, conf, _, _, nat = P.classify(r, markers, {}, overrides, nats,
                                        use_names=False, titles=titles)
        if g in (P.FEMALE, P.MALE) and conf >= P.HIGH_CONF:
            seed.append((P.split_label(r["label"], titles)[1], nat, g))
    stats = P.build_name_stats(seed)

    etypes = load_entity_types()
    persons = []
    mismatch = 0
    for r in rows:
        eid = r["entity_id"]
        g, conf, _, inds, nat = P.classify(r, markers, stats, overrides, nats, titles=titles)
        ex = existing[eid]
        if g != ex["koen"]:
            mismatch += 1
        surname, given, rest = P.split_label(r["label"], titles)
        fams = {family_of(c) for _, w, c, _ in inds if w > 0}
        ref_all = label_from(inds)
        ref_wo = {fam: label_from([i for i in inds if family_of(i[2]) != fam])
                  for fam in ("NAME", "LABEL", "DESC")}
        # Kun-markør-etiket (parserens gennemløb 1): uafhængig af alle navne.
        ref_markers = label_from([i for i in inds if family_of(i[2]) != "NAME"])
        persons.append({
            "id": eid, "label": r["label"], "desc": r["description"] or "",
            "existing": {"Mandlig": M, "Kvindelig": K}.get(ex["koen"]),
            "existing_conf": float(ex["confidence"]),
            "surname": surname, "given": given, "rest": rest,
            "nat": nat or "", "roles": roles.get(eid, []),
            "nref": nref.get(eid, 0), "nvol": len(vols.get(eid, ())),
            "has_years": bool(YEARS_RE.search(r["label"])),
            "excluded": exclusion_reason(r["label"], r["description"] or "", given, etypes),
            "families": fams, "ref_all": ref_all, "ref_wo": ref_wo,
            "ref_markers": ref_markers, "inds": inds,
        })
        persons[-1]["stub"] = persons[-1]["excluded"] is not None
    return persons, mismatch, markers, stats


# ───────────────────────────────────────────────────────────────────────────
# Featureudtræk
# ───────────────────────────────────────────────────────────────────────────

# Hovedleddet af beskrivelsen = det, der står FØR første relationsord.
# "Datter af Proprietær X" → hoved "Datter" (maskeres), så faderens erhverv
# ikke læres som et kvindeligt træk. Det er den vigtigste lækagekilde for
# beskrivelsesfeatures.
HEAD_CUT_RE = re.compile(
    r"\b(af|til|efter|med|hos|for|g\.|gift|e\.|enke|søn|datter|broder|søster|"
    r"fader|moder|hustru|svigerfader|svigermoder|svigersøn|svigerdatter)\b",
    re.I)
TOKEN_RE = re.compile(r"[A-Za-zÆØÅæøåÀ-ÿ]{3,}")
PRONOUNS = {"han", "hans", "hun", "hendes"}


def marker_terms(markers):
    return {m["term"].lower() for m in markers}


def desc_head(desc):
    d = P.PLACE_NOISE_RE.sub(" ", desc)
    mo = HEAD_CUT_RE.search(d)
    head = d[:mo.start()] if mo else d
    # første sætning (punktum efterfulgt af stort bogstav) — "cand. theol." bevares
    head = re.split(r"\.\s+(?=[A-ZÆØÅ])", head, maxsplit=1)[0]
    return head


def head_tokens(desc, mterms, nat_words):
    out = []
    for t in TOKEN_RE.findall(desc_head(desc)):
        tl = t.lower()
        if tl in mterms or tl in PRONOUNS or tl in nat_words:
            continue
        if tl.endswith("inde") and not tl.endswith("minde"):
            continue  # -inde er en markør (DESC); maskeres for at undgå cirkularitet
        out.append(tl)
    return out


def occupation(desc, mterms, nat_words):
    toks = head_tokens(desc, mterms, nat_words)
    return toks[0] if toks else None


def title_gender_map(markers):
    """Titelord fra markørlisten (label_title) — bruges her på BESKRIVELSEN,
    hvor parseren kun leder efter Fru/Frøken/Jomfru/Madame. "Komtesse
    (1812–…)", "Greve, fransk Legationssekretær" og "Fransk Dronning" er
    derfor endt som ubestemte."""
    return {m["term"].lower(): m["gender"] for m in markers if m["category"] == "label_title"}


def desc_title(desc, tmap):
    head = desc_head(desc)
    for mo in TOKEN_RE.finditer(head):
        t = mo.group(0).lower()
        if t not in tmap:
            continue
        if re.match(r"\s+[A-ZÆØÅ]", head[mo.end():mo.end() + 30]):
            continue  # foran et egennavn → en anden person
        if P.POSSESSIVE_RE.search(head[:mo.start()]):
            continue
        return t
    return None


def nat_words_from(persons):
    w = set()
    for p in persons:
        if p["nat"]:
            w.add(p["nat"].lower())
    w |= {"dansk", "tysk", "fransk", "engelsk", "svensk", "norsk", "italiensk",
          "russisk", "amerikansk", "hollandsk", "flamsk", "spansk", "polsk",
          "græsk", "østrigsk", "preussisk", "skotsk", "irsk", "schweizisk",
          "belgisk", "ungarsk", "portugisisk", "finsk", "islandsk", "jødisk",
          "fhv", "senere", "kgl", "ved", "det", "den", "der", "som", "og"}
    return w


# Ét "feature" = funktion person → nøgle (eller None = mangler).
def build_single_features(mterms, nat_words, title_terms):
    def first(p, f):
        return f(p["given"][0]) if p["given"] else None

    def suffix(k):
        def fn(p):
            if not p["given"]:
                return None
            n = exact(p["given"][0])
            return n[-k:] if len(n) >= k else None
        return fn

    def surname_suffix(p):
        s = exact(p["surname"].split()[-1]) if p["surname"] else ""
        for suf in ("datter", "dotter", "dottir", "sen", "son", "ova", "ska", "ina", "a"):
            if s.endswith(suf):
                return suf
        return None

    def label_rest(p):
        toks = [s.lower() for s in p["rest"]
                if s.lower() not in title_terms and not P.NEE_RE.search(s)]
        return toks[0] if toks else None

    return [
        # navn (NAME)
        ("fornavn (eksakt)", "NAME", lambda p: first(p, exact)),
        ("fornavn (stavevariant)", "NAME", lambda p: first(p, variant)),
        ("sidste fornavn", "NAME", lambda p: exact(p["given"][-1]) if p["given"] else None),
        ("fornavnsendelse 3 tegn", "NAME", suffix(3)),
        ("fornavnsendelse 2 tegn", "NAME", suffix(2)),
        ("fuldt navn (efternavn+fornavne)", "NAME",
         lambda p: exact(p["surname"] + "|" + " ".join(p["given"])) if p["given"] else None),
        # efternavn (bruges ikke af parseren)
        ("efternavn", "SURNAME", lambda p: exact(p["surname"]) if p["surname"] else None),
        ("efternavnsendelse", "SURNAME", surname_suffix),
        # label-titel ud over markørlisten
        ("label-segment (ikke-markør)", "LABEL", label_rest),
        # beskrivelse
        ("erhverv (første ord i beskrivelsens hoved)", "DESC",
         lambda p: occupation(p["desc"], mterms, nat_words)),
        ("rolle (person_role.csv)", "DESC", lambda p: p["roles"][0] if p["roles"] else None),
        ("titel i beskrivelsens hoved", "DESC", lambda p: desc_title(p["desc"], TMAP)),
        # øvrige metadata
        ("nationalitet", "NAT", lambda p: p["nat"] or None),
        ("har leveår i label", "META", lambda p: "ja" if p["has_years"] else "nej"),
        ("antal bind med henvisninger", "META",
         lambda p: str(min(p["nvol"], 4)) + ("+" if p["nvol"] >= 4 else "")),
        ("har fornavn i label", "META", lambda p: "ja" if p["given"] else "nej"),
    ]


def ref_for(p, fam):
    """Referenceetiket, der er uafhængig af familien fam."""
    if fam in ("NAME", "LABEL", "DESC"):
        return p["ref_wo"][fam]
    return p["ref_all"]


def group_key(p):
    g = p["given"][0] if p["given"] else ""
    return exact(p["surname"]) + "|" + variant(g)


# ───────────────────────────────────────────────────────────────────────────
# Evaluering
# ───────────────────────────────────────────────────────────────────────────

def lookup_fit(keys, ys, alpha=1.0):
    c = defaultdict(lambda: [0, 0])
    for k, y in zip(keys, ys):
        if k is None:
            continue
        c[k][0 if y == K else 1] += 1
    return {k: ((v[0] + alpha) / (v[0] + v[1] + 2 * alpha), v[0] + v[1]) for k, v in c.items()}


def lookup_predict(table, k, min_n=1):
    if k is None or k not in table:
        return None
    pk, n = table[k]
    if n < min_n:
        return None
    return pk


def metrics(y_true, p_k, n_total, thr=0.5):
    """y_true: K/M; p_k: P(K) eller None (= afstår). Returnerer målinger ved
    confidence-tærskel thr (confidence = max(pK, 1-pK))."""
    tp = Counter()
    pred_n = Counter()
    true_n = Counter(y_true)
    covered = correct = 0
    for y, pk in zip(y_true, p_k):
        if pk is None:
            continue
        conf = max(pk, 1 - pk)
        if conf < thr or pk == 0.5:
            continue
        pred = K if pk > 0.5 else M
        covered += 1
        pred_n[pred] += 1
        if pred == y:
            correct += 1
            tp[pred] += 1
    res = {
        "n_eval": n_total, "coverage_n": covered,
        "coverage": covered / n_total if n_total else 0,
        "precision": correct / covered if covered else float("nan"),
        "errors": covered - correct,
    }
    for c in (K, M):
        res[f"prec_{c}"] = tp[c] / pred_n[c] if pred_n[c] else float("nan")
        res[f"recall_{c}"] = tp[c] / true_n[c] if true_n[c] else float("nan")
        res[f"pred_{c}"] = pred_n[c]
    return res


def reliability(y_true, p_k, bins=(0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 1.0001)):
    rows = []
    pairs = [(y, pk) for y, pk in zip(y_true, p_k) if pk is not None]
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        sel = [(y, pk) for y, pk in pairs if lo <= max(pk, 1 - pk) < hi]
        if not sel:
            continue
        conf = sum(max(pk, 1 - pk) for _, pk in sel) / len(sel)
        acc = sum(1 for y, pk in sel if (K if pk > 0.5 else M) == y) / len(sel)
        ece += len(sel) / max(len(pairs), 1) * abs(conf - acc)
        rows.append({"bin": f"{lo:.2f}–{min(hi, 1):.2f}", "n": len(sel),
                     "mean_conf": round(conf, 4), "accuracy": round(acc, 4)})
    return rows, ece


def wilson_lower(k, n, z=1.96):
    if n == 0:
        return 0.0
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    a = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (c - a) / d


def cv_splits(items, groups, by="group", seed=SEED):
    idx = np.arange(len(items))
    if by == "random":
        return list(KFold(N_FOLDS, shuffle=True, random_state=seed).split(idx))
    # GroupKFold er deterministisk; bland gruppe-id'erne, så foldene ikke
    # bliver alfabetiske udsnit af registret.
    rng = np.random.RandomState(seed)
    uniq = sorted(set(groups))
    mapping = dict(zip(uniq, rng.permutation(len(uniq))))
    gnum = np.array([mapping[g] for g in groups])
    return list(GroupKFold(N_FOLDS).split(idx, groups=gnum))


def oof_lookup(persons, fn, fam, by="group", min_n=1):
    """Out-of-fold P(K) for én feature på dens uafhængige evalueringssæt."""
    ev = [p for p in persons if ref_for(p, fam) is not None and not p["stub"]]
    y = [ref_for(p, fam) for p in ev]
    keys = [fn(p) for p in ev]
    if by == "group":
        groups = [group_key(p) for p in ev]
    elif by == "name":
        groups = [variant(p["given"][0]) if p["given"] else "∅" + p["id"] for p in ev]
    else:
        groups = None
    pk = [None] * len(ev)
    for tr, te in cv_splits(ev, groups, by="random" if by == "random" else "group"):
        table = lookup_fit([keys[i] for i in tr], [y[i] for i in tr])
        for i in te:
            pk[i] = lookup_predict(table, keys[i], min_n)
    return ev, y, keys, pk


# ───────────────────────────────────────────────────────────────────────────
# Kombinerede modeller
# ───────────────────────────────────────────────────────────────────────────

def feat_dict(p, mterms, nat_words, title_terms, use=("name", "surname", "desc", "nat", "meta")):
    d = {}
    if "name" in use and p["given"]:
        f0 = p["given"][0]
        d["fn=" + variant(f0)] = 1
        e = exact(f0)
        for k in (2, 3, 4):
            if len(e) >= k:
                d[f"suf{k}=" + e[-k:]] = 1
        for g in p["given"][1:]:
            d["gn=" + variant(g)] = 0.5
    if "surname" in use and p["surname"]:
        s = exact(p["surname"])
        d["sn=" + s] = 1
        d["ssuf3=" + s[-3:]] = 1
    if "desc" in use:
        for t in head_tokens(p["desc"], mterms, nat_words)[:6]:
            d["dh=" + t] = 1
        for r in p["roles"]:
            d["role=" + r] = 1
        for s in p["rest"]:
            sl = s.lower()
            if sl not in title_terms and not P.NEE_RE.search(s):
                d["rest=" + sl] = 1
    if "nat" in use and p["nat"]:
        d["nat=" + p["nat"]] = 1
    if "meta" in use:
        d["has_given"] = 1 if p["given"] else 0
        d["has_years"] = 1 if p["has_years"] else 0
        d["log_nref"] = math.log1p(p["nref"])
        d["nvol"] = p["nvol"]
    return d


def make_lr(calibrated):
    lr = LogisticRegression(C=1.0, max_iter=3000)
    if not calibrated:
        return lr
    return CalibratedClassifierCV(lr, method="isotonic", cv=5)


def em_prior(p, pi_t, iters=200):
    """Estimer klasseprioren i en ny population og juster P(K) derefter
    (Saerens, Latinne & Decaestecker 2002). p: kalibrerede P(K) under
    træningsprioren pi_t."""
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    pi = pi_t
    for _ in range(iters):
        a = (pi / pi_t) * p
        b = ((1 - pi) / (1 - pi_t)) * (1 - p)
        adj = a / (a + b)
        new = float(adj.mean())
        if abs(new - pi) < 1e-7:
            break
        pi = new
    return pi, adj


def target_encode(train_keys, train_y, apply_keys, alpha=2.0, prior=0.5):
    c = defaultdict(lambda: [0, 0])
    for k, y in zip(train_keys, train_y):
        if k is not None:
            c[k][0] += y
            c[k][1] += 1
    out = []
    for k in apply_keys:
        if k is None or k not in c:
            out.append((prior, 0))
        else:
            s, n = c[k]
            out.append(((s + alpha * prior) / (n + alpha), n))
    return out


def dense_matrix(tr_ps, tr_y, ap_ps, keyfns, inner_oof):
    """Target-encodede kolonner. inner_oof=True: encodings for træningsrækker
    beregnes out-of-fold, så GBM ikke lærer sine egne etiketter."""
    ybin = [1 if y == K else 0 for y in tr_y]
    cols = []
    for fn in keyfns:
        tr_keys = [fn(p) for p in tr_ps]
        if inner_oof:
            enc = [None] * len(tr_ps)
            for a, b in KFold(5, shuffle=True, random_state=SEED).split(tr_ps):
                e = target_encode([tr_keys[i] for i in a], [ybin[i] for i in a],
                                  [tr_keys[i] for i in b])
                for j, i in enumerate(b):
                    enc[i] = e[j]
        else:
            enc = target_encode(tr_keys, ybin, [fn(p) for p in ap_ps])
        cols.append([e[0] for e in enc])
        cols.append([math.log1p(e[1]) for e in enc])
    return np.array(cols).T


def evaluate_combined(persons, mterms, nat_words, title_terms, eval_set, by="group"):
    """eval_set: 'markers' — etiketter fra markører alene (uafhængige af navn);
    beskrivelsesfeatures er maskeret til hovedleddet."""
    ev = [p for p in persons if p["ref_markers"] is not None and not p["stub"]]
    y = [p["ref_markers"] for p in ev]
    yb = np.array([1 if v == K else 0 for v in y])
    if by == "name":
        groups = [variant(p["given"][0]) if p["given"] else "∅" + p["id"] for p in ev]
    else:
        groups = [group_key(p) for p in ev]
    splits = cv_splits(ev, groups)

    keyfns = [
        lambda p: variant(p["given"][0]) if p["given"] else None,
        lambda p: exact(p["given"][0])[-3:] if p["given"] and len(p["given"][0]) >= 3 else None,
        lambda p: exact(p["given"][0])[-2:] if p["given"] and len(p["given"][0]) >= 2 else None,
        lambda p: exact(p["surname"]) if p["surname"] else None,
        lambda p: occupation(p["desc"], mterms, nat_words),
        lambda p: p["nat"] or None,
    ]

    results = {}
    configs = {
        "LR navne": (("name",), False),
        "LR navne+efternavn": (("name", "surname"), False),
        "LR alle features": (("name", "surname", "desc", "nat", "meta"), False),
        "LR uden metadata": (("name", "surname", "desc", "nat"), False),
        "LR uden metadata, isotonisk kalibreret": (("name", "surname", "desc", "nat"), True),
        "LR alle features, isotonisk kalibreret": (("name", "surname", "desc", "nat", "meta"), True),
    }
    for name, (use, cal) in configs.items():
        pk = np.full(len(ev), np.nan)
        for tr, te in splits:
            dv = DictVectorizer()
            Xtr = dv.fit_transform([feat_dict(ev[i], mterms, nat_words, title_terms, use) for i in tr])
            Xte = dv.transform([feat_dict(ev[i], mterms, nat_words, title_terms, use) for i in te])
            m = make_lr(cal).fit(Xtr, yb[tr])
            pk[te] = m.predict_proba(Xte)[:, 1]
        results[name] = pk

    # Mere avanceret: gradient boosting på out-of-fold target-encodings
    pk = np.full(len(ev), np.nan)
    for tr, te in splits:
        Xtr = dense_matrix([ev[i] for i in tr], [y[i] for i in tr], None, keyfns, True)
        Xte = dense_matrix([ev[i] for i in tr], [y[i] for i in tr], [ev[i] for i in te], keyfns, False)
        g = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                           max_leaf_nodes=15, random_state=SEED)
        g.fit(Xtr, yb[tr])
        pk[te] = g.predict_proba(Xte)[:, 1]
    results["Gradient boosting (target-encoding)"] = pk
    return ev, y, results


# ───────────────────────────────────────────────────────────────────────────
# Regelkaskade (gennemsigtig, opslagsbaseret)
# ───────────────────────────────────────────────────────────────────────────

def build_rule_table(keys, ys, min_n, min_lower):
    """Behold kun nøgler med n ≥ min_n og Wilson-nedre-grænse ≥ min_lower."""
    c = defaultdict(Counter)
    for k, y in zip(keys, ys):
        if k is not None:
            c[k][y] += 1
    table = {}
    for k, cnt in c.items():
        n = cnt[K] + cnt[M]
        top = K if cnt[K] >= cnt[M] else M
        lb = wilson_lower(cnt[top], n)
        if n >= min_n and lb >= min_lower:
            table[k] = (top, cnt[top], n, lb)
    return table


def rule_eval(persons, fn, fam, min_n, min_lower):
    ev = [p for p in persons if ref_for(p, fam) is not None and not p["stub"]]
    y = [ref_for(p, fam) for p in ev]
    keys = [fn(p) for p in ev]
    groups = [group_key(p) for p in ev]
    cov = cor = 0
    errs = []
    for tr, te in cv_splits(ev, groups):
        t = build_rule_table([keys[i] for i in tr], [y[i] for i in tr], min_n, min_lower)
        for i in te:
            if keys[i] in t:
                cov += 1
                if t[keys[i]][0] == y[i]:
                    cor += 1
                else:
                    errs.append((ev[i]["label"], ev[i]["desc"][:80], keys[i], t[keys[i]][0], y[i]))
    return {"n_eval": len(ev), "coverage_n": cov, "coverage": cov / len(ev),
            "precision": cor / cov if cov else float("nan"), "errors": cov - cor}, errs


# ───────────────────────────────────────────────────────────────────────────
# Hovedprogram
# ───────────────────────────────────────────────────────────────────────────

def fmt(x, pct=True):
    if isinstance(x, float) and math.isnan(x):
        return "–"
    return f"{x:.1%}" if pct else f"{x}"


def write_csv(name, rows, cols=None):
    path = os.path.join(OUT, name)
    if not rows:
        return path
    cols = cols or list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    return path


def main():
    global REF_CONF, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="referenceetiketter kræver confidence ≥ 0,90 (følsomhedsanalyse)")
    args = ap.parse_args()
    if args.strict:
        REF_CONF = P.HIGH_CONF
        OUT = os.path.join(OUT, "strict")
        os.makedirs(OUT, exist_ok=True)
    persons, mismatch, markers, stats = load()
    mterms = marker_terms(markers)
    title_terms = P.title_terms_from(markers)
    nat_words = nat_words_from(persons)
    summary = {}

    # ── 1. Datagrundlag ────────────────────────────────────────────────────
    unk = [p for p in persons if p["existing"] is None]
    known = [p for p in persons if p["existing"] is not None]
    summary["n_persons"] = len(persons)
    summary["parser_reproduction_mismatch"] = mismatch
    summary["existing"] = Counter(p["existing"] or "?" for p in persons)
    summary["excluded_total"] = Counter(p["excluded"] for p in persons if p["excluded"])
    summary["excluded_unknown"] = Counter(p["excluded"] for p in unk if p["excluded"])
    summary["excluded_known"] = Counter((p["excluded"], p["existing"]) .__str__()
                                        for p in known if p["excluded"])
    summary["label_basis"] = Counter(
        "+".join(sorted(p["families"])) or "ingen" for p in known)
    summary["name_only_labels"] = sum(1 for p in known if p["families"] == {"NAME"})
    summary["ref_markers"] = Counter(p["ref_markers"] for p in persons if p["ref_markers"])
    for fam in ("NAME", "LABEL", "DESC"):
        summary[f"ref_wo_{fam}"] = Counter(p["ref_wo"][fam] for p in persons if p["ref_wo"][fam])
    summary["unknown_profile"] = {
        "total": len(unk),
        "udelukket (ikke enkeltperson/henvisning)": sum(p["stub"] for p in unk),
        "har fornavn": sum(1 for p in unk if p["given"]),
        "har beskrivelse": sum(1 for p in unk if p["desc"].strip()),
        "har erhvervsord i beskrivelsens hoved": sum(
            1 for p in unk if occupation(p["desc"], mterms, nat_words)),
        "hverken fornavn eller erhvervsord": sum(
            1 for p in unk if not p["given"] and not occupation(p["desc"], mterms, nat_words)
            and not p["stub"]),
        "har leveår": sum(1 for p in unk if p["has_years"]),
        "har egen nationalitet": sum(1 for p in unk if p["nat"]),
    }

    # Uenighed mellem uafhængige evidensfamilier = estimat af etiketstøj:
    # poster, hvor BÅDE navnet alene og markørerne alene giver en sikker etiket.
    noise = Counter()
    noise_rows = []
    for p in persons:
        mk = p["ref_markers"]
        nm = direction([i for i in p["inds"] if i[2] == "Fornavn"])
        if mk and nm:
            noise["enige" if mk == nm else "uenige"] += 1
            if mk != nm:
                noise_rows.append({"entity_id": p["id"], "label": p["label"],
                                   "beskrivelse": p["desc"][:120], "markører_siger": mk,
                                   "fornavn_siger": nm, "eksisterende": p["existing"] or ""})
    summary["label_noise_name_vs_markers"] = noise
    write_csv("label_noise_name_vs_markers.csv", noise_rows)
    summary["dup"] = {}
    keys = Counter(group_key(p) for p in persons if p["given"])
    summary["dup"]["navnenøgler med >1 post (efternavn+fornavnsvariant)"] = sum(1 for v in keys.values() if v > 1)
    summary["dup"]["poster i sådanne grupper"] = sum(v for v in keys.values() if v > 1)
    lk = Counter((exact(p["label"]), exact(p["desc"])) for p in persons)
    summary["dup"]["eksakte dubletter (label+beskrivelse)"] = sum(v - 1 for v in lk.values() if v > 1)

    # ── 2. Enkeltfeatures ──────────────────────────────────────────────────
    global TMAP
    TMAP = title_gender_map(markers)
    feats = build_single_features(mterms, nat_words, title_terms)
    single_rows = []
    rel_rows = []
    for name, fam, fn in feats:
        for by in ("group", "random") if name.startswith("fuldt navn") or name.startswith("fornavn (eksakt)") else ("group",):
            ev, y, keys, pk = oof_lookup(persons, fn, fam, by=by)
            # dækning på de ukendte (tabel trænet på hele evalueringssættet)
            table = lookup_fit(keys, y)
            unk_keys = [fn(p) for p in unk if not p["stub"]]
            unk_pk = [lookup_predict(table, k) for k in unk_keys]
            for thr in (0.5,) + THRESHOLDS:
                m = metrics(y, pk, len(ev), thr)
                ucov = sum(1 for q in unk_pk if q is not None and max(q, 1 - q) >= max(thr, 0.5001))
                single_rows.append({
                    "feature": name, "familie": fam, "cv": by, "tærskel": thr,
                    "n_eval": m["n_eval"], "eval_K": y.count(K), "eval_M": y.count(M),
                    "dækning_n": m["coverage_n"], "dækning": m["coverage"],
                    "præcision": m["precision"], "fejl": m["errors"],
                    "præc_K": m["prec_K"], "recall_K": m["recall_K"],
                    "præc_M": m["prec_M"], "recall_M": m["recall_M"],
                    "forudsagt_K": m["pred_K"], "forudsagt_M": m["pred_M"],
                    "ukendte_dækket_n": ucov,
                    "ukendte_dækket": ucov / len(unk_keys),
                    "feature_tilstede_ukendte": sum(1 for k in unk_keys if k is not None),
                })
            if by == "group":
                rr, ece = reliability(y, pk)
                for r in rr:
                    rel_rows.append({"model": name, **r})
                rel_rows.append({"model": name, "bin": "ECE", "n": "", "mean_conf": "",
                                 "accuracy": round(ece, 4)})
    write_csv("single_features.csv", single_rows)

    # Fornavn: navne-disjunkt CV (= navne, modellen aldrig har set)
    fn_variant = [f for f in feats if f[0] == "fornavn (stavevariant)"][0][2]
    fn_suf3 = [f for f in feats if f[0] == "fornavnsendelse 3 tegn"][0][2]
    disjoint = {}
    for name, fn in (("fornavn (stavevariant)", fn_variant), ("fornavnsendelse 3 tegn", fn_suf3)):
        ev, y, keys, pk = oof_lookup(persons, fn, "NAME", by="name")
        disjoint[name] = {thr: metrics(y, pk, len(ev), thr) for thr in (0.5, 0.9, 0.95)}
    summary["name_disjoint"] = disjoint

    # Min-n: fornavnets præcision efter, hvor mange gange navnet er set
    ev, y, keys, _ = oof_lookup(persons, fn_variant, "NAME")
    groups = [group_key(p) for p in ev]
    by_n = defaultdict(lambda: [0, 0])
    unseen = [0]
    for tr, te in cv_splits(ev, groups):
        c = defaultdict(Counter)
        for i in tr:
            if keys[i]:
                c[keys[i]][y[i]] += 1
        for i in te:
            k = keys[i]
            if not k or k not in c:
                unseen[0] += 1
                continue
            n = c[k][K] + c[k][M]
            purity = max(c[k][K], c[k][M]) / n
            pred = K if c[k][K] >= c[k][M] else M
            bucket = ("1" if n == 1 else "2" if n == 2 else "3–4" if n < 5 else
                      "5–9" if n < 10 else "10–19" if n < 20 else "20+")
            pb = "renhed=1" if purity == 1 else "renhed≥0,9" if purity >= 0.9 else "renhed<0,9"
            for b in (bucket, f"{bucket} / {pb}"):
                by_n[b][0] += pred == y[i]
                by_n[b][1] += 1
    summary["firstname_by_n"] = {k: {"n": v[1], "præcision": v[0] / v[1] if v[1] else None}
                                 for k, v in sorted(by_n.items())}
    summary["firstname_unseen_in_fold"] = {"n": unseen[0], "af": len(ev)}

    # Fornavnsoversigt (trænet på alle navne-uafhængige etiketter)
    c = defaultdict(Counter)
    for p, yy in zip(ev, y):
        if p["given"]:
            c[variant(p["given"][0])][yy] += 1
            c[variant(p["given"][0])]["_form:" + p["given"][0]] += 1
    unk_names = Counter(variant(p["given"][0]) for p in unk if p["given"])
    name_rows = []
    for k, cnt in c.items():
        n = cnt[K] + cnt[M]
        top = K if cnt[K] >= cnt[M] else M
        lb = wilson_lower(cnt[top], n)
        forms = [f.split(":", 1)[1] for f, _ in cnt.most_common() if f.startswith("_form:")][:4]
        share = cnt[top] / n
        sex = "kvinde" if top == K else "mand"
        if n < 3:
            cls = "sjælden (n<3)"
        elif share < 0.9:
            cls = "tvetydig"
        elif n >= 5 and share >= 0.95:
            cls = "meget sikker " + sex
        else:
            cls = "sandsynlig " + sex
        name_rows.append({"navnenøgle": k, "former": " / ".join(forms), "K": cnt[K], "M": cnt[M],
                          "n": n, "andel_top": round(cnt[top] / n, 3), "wilson_nedre": round(lb, 3),
                          "klasse": cls, "forekomster_blandt_ukendte": unk_names.get(k, 0)})
    name_rows.sort(key=lambda r: (-r["n"], r["navnenøgle"]))
    write_csv("firstname_overview.csv", name_rows)
    summary["firstname_classes"] = Counter(r["klasse"] for r in name_rows)
    summary["unknown_firstname_in_lexicon"] = {
        "ukendte med fornavn": sum(unk_names.values()),
        "fornavn set ≥1 gang": sum(v for k, v in unk_names.items() if k in c),
        "fornavn set ≥5 gange": sum(v for k, v in unk_names.items() if k in c and sum(
            c[k][x] for x in (K, M)) >= 5),
        "fornavn i 'meget sikker'-klasse": sum(
            v for k, v in unk_names.items()
            if k in {r["navnenøgle"] for r in name_rows if r["klasse"].startswith("meget")}),
    }

    # Erhvervsoversigt (trænet på DESC-uafhængige etiketter)
    fn_occ = [f for f in feats if f[0].startswith("erhverv")][0][2]
    ev_o = [p for p in persons if p["ref_wo"]["DESC"] and not p["stub"]]
    co = defaultdict(Counter)
    for p in ev_o:
        k = fn_occ(p)
        if k:
            co[k][p["ref_wo"]["DESC"]] += 1
    unk_occ = Counter(fn_occ(p) for p in unk if not p["stub"])
    occ_rows = []
    for k, cnt in co.items():
        n = cnt[K] + cnt[M]
        top = K if cnt[K] >= cnt[M] else M
        occ_rows.append({"erhvervsord": k, "K": cnt[K], "M": cnt[M], "n": n,
                         "andel_top": round(cnt[top] / n, 3),
                         "wilson_nedre": round(wilson_lower(cnt[top], n), 3),
                         "retning": top, "forekomster_blandt_ukendte": unk_occ.get(k, 0)})
    occ_rows.sort(key=lambda r: -r["n"])
    write_csv("occupation_overview.csv", occ_rows)
    unseen_occ = [{"erhvervsord": k, "forekomster_blandt_ukendte": v}
                  for k, v in unk_occ.most_common() if k and k not in co]
    write_csv("occupation_unseen_in_training.csv", unseen_occ[:300])

    # ── 3. Regelbaseret kaskade ───────────────────────────────────────────
    rule_rows = []
    rule_errs = {}
    for fname, fam, fn in [("fornavn (stavevariant)", "NAME", fn_variant),
                           ("fornavnsendelse 3 tegn", "NAME", fn_suf3),
                           ("erhverv (første ord i beskrivelsens hoved)", "DESC", fn_occ)]:
        for min_n, lb in ((3, 0.80), (5, 0.85), (5, 0.90), (10, 0.95), (20, 0.97)):
            r, errs = rule_eval(persons, fn, fam, min_n, lb)
            ev_all = [p for p in persons if ref_for(p, fam) is not None and not p["stub"]]
            t = build_rule_table([fn(p) for p in ev_all], [ref_for(p, fam) for p in ev_all], min_n, lb)
            ucov = [p for p in unk if not p["stub"] and fn(p) in t]
            rule_rows.append({"regel": fname, "min_n": min_n, "wilson_nedre_min": lb, **r,
                              "ukendte_dækket_n": len(ucov),
                              "ukendte_dækket_K": sum(1 for p in ucov if t[fn(p)][0] == K),
                              "ukendte_dækket_M": sum(1 for p in ucov if t[fn(p)][0] == M)})
            rule_errs[(fname, min_n, lb)] = errs
    write_csv("rule_tables.csv", rule_rows)

    # ── 4. Kombinerede modeller ───────────────────────────────────────────
    comb_rows, comb_rel = [], []
    combined_preds = {}
    for by in ("group", "name"):
        ev_c, y_c, res = evaluate_combined(persons, mterms, nat_words, title_terms, "markers", by)
        for mname, pk in res.items():
            pkl = [float(v) for v in pk]
            if by == "group":
                combined_preds[mname] = (ev_c, y_c, pkl)
            for thr in (0.5,) + THRESHOLDS:
                m = metrics(y_c, pkl, len(ev_c), thr)
                comb_rows.append({"model": mname, "cv": by, "tærskel": thr, "n_eval": len(ev_c),
                                  "dækning": m["coverage"], "dækning_n": m["coverage_n"],
                                  "præcision": m["precision"], "fejl": m["errors"],
                                  "præc_K": m["prec_K"], "recall_K": m["recall_K"],
                                  "præc_M": m["prec_M"], "recall_M": m["recall_M"]})
            if by == "group":
                rr, ece = reliability(y_c, pkl)
                for r in rr:
                    comb_rel.append({"model": mname, **r})
                comb_rel.append({"model": mname, "bin": "ECE", "accuracy": round(ece, 4)})
                ll = -np.mean([math.log(max(1e-6, p if yy == K else 1 - p)) for yy, p in zip(y_c, pkl)])
                br = np.mean([((1 if yy == K else 0) - p) ** 2 for yy, p in zip(y_c, pkl)])
                comb_rel.append({"model": mname, "bin": "logloss/brier",
                                 "mean_conf": round(float(ll), 4), "accuracy": round(float(br), 4)})
    write_csv("combined_models.csv", comb_rows)
    write_csv("calibration.csv", rel_rows + comb_rel,
              ["model", "bin", "n", "mean_conf", "accuracy"])

    # Kombinationseffekt: præcision for kombineret model stratificeret efter
    # hvilke features posten har
    ev_c, y_c, pk = combined_preds["LR alle features, isotonisk kalibreret"]
    strat = defaultdict(lambda: [0, 0, 0])
    for p, yy, q in zip(ev_c, y_c, pk):
        s = ("fornavn" if p["given"] else "intet fornavn") + " / " + \
            ("erhverv" if occupation(p["desc"], mterms, nat_words) else "intet erhverv")
        strat[s][2] += 1
        if max(q, 1 - q) >= 0.95:
            strat[s][1] += 1
            strat[s][0] += (K if q > 0.5 else M) == yy
    summary["combined_by_availability_at_0.95"] = {
        k: {"n": v[2], "dækket": v[1], "præcision": v[0] / v[1] if v[1] else None}
        for k, v in strat.items()}

    # ── 5. Ikke-navnefeatures målt på NAVNE-mærkede poster ────────────────
    # Poster kategoriseret på fornavnet alene ligner de ukendte mest: ingen
    # markører, kun navn + beskrivelse. Deres etiket er uafhængig af
    # beskrivelse, efternavn og metadata, så en model UDEN navnefeatures kan
    # evalueres ærligt på dem. Træning: alle sikre etiketter (CV-grupperet).
    pool = [p for p in persons if p["ref_all"] and not p["stub"]]
    y_pool = [p["ref_all"] for p in pool]
    yb_pool = np.array([1 if v == K else 0 for v in y_pool])
    is_name_only = np.array([p["families"] == {"NAME"} for p in pool])
    splits = cv_splits(pool, [group_key(p) for p in pool])
    nonname_rows = []
    nonname_preds = {}
    for mname, use in (("beskrivelse (hovedled+rolle)", ("desc",)),
                       ("beskrivelse+nationalitet", ("desc", "nat")),
                       ("beskrivelse+nationalitet+efternavn+metadata", ("desc", "nat", "surname", "meta"))):
        pk = np.full(len(pool), np.nan)
        for tr, te in splits:
            dv = DictVectorizer()
            Xtr = dv.fit_transform([feat_dict(pool[i], mterms, nat_words, title_terms, use) for i in tr])
            m = make_lr(True).fit(Xtr, yb_pool[tr])
            pk[te] = m.predict_proba(dv.transform(
                [feat_dict(pool[i], mterms, nat_words, title_terms, use) for i in te]))[:, 1]
        nonname_preds[mname] = pk
        sel = np.where(is_name_only)[0]
        yy = [y_pool[i] for i in sel]
        for thr in (0.5,) + THRESHOLDS:
            m = metrics(yy, [float(pk[i]) for i in sel], len(sel), thr)
            nonname_rows.append({"model": mname, "evalsæt": "kun-fornavn-etiketter",
                                 "tærskel": thr, "n_eval": len(sel), "eval_K": yy.count(K),
                                 "eval_M": yy.count(M), **{k: m[k] for k in (
                                     "coverage", "coverage_n", "precision", "errors",
                                     "prec_K", "recall_K", "prec_M", "recall_M", "pred_K", "pred_M")}})
        rr, ece = reliability(yy, [float(pk[i]) for i in sel])
        for r in rr:
            comb_rel.append({"model": "ikke-navn: " + mname + " (kun-fornavn-etiketter)", **r})
        comb_rel.append({"model": "ikke-navn: " + mname + " (kun-fornavn-etiketter)",
                         "bin": "ECE", "accuracy": round(ece, 4)})
    write_csv("nonname_models_on_name_labels.csv", nonname_rows)
    write_csv("calibration.csv", rel_rows + comb_rel, ["model", "bin", "n", "mean_conf", "accuracy"])

    # ── 6. Endelige kandidatstrategier ───────────────────────────────────
    unk_live = [p for p in unk if not p["stub"]]

    # Fornavnsleksikon. Optællingerne bygger KUN på markør-etiketter, så
    # navne-etiketterne ikke tæller navnet med sig selv. Optalt både generelt
    # og pr. nationalitet (til nationalitetsværnet).
    def name_counts(rows, label_of):
        cnt, cnt_nat = defaultdict(Counter), defaultdict(Counter)
        for p in rows:
            if p["given"]:
                k = variant(p["given"][0])
                cnt[k][label_of(p)] += 1
                cnt_nat[(k, p["nat"])][label_of(p)] += 1
        return cnt, cnt_nat

    def name_rule(p, cnt, cnt_nat, guard, min_n=3, min_share=0.95):
        if not p["given"]:
            return None
        k = variant(p["given"][0])
        c = cnt.get(k)
        if not c:
            return None
        n = c[K] + c[M]
        top = K if c[K] >= c[M] else M
        if n < min_n or c[top] / n < min_share:
            return None
        if guard and p["nat"] not in HOME_NATS:
            cn = cnt_nat.get((k, p["nat"]), Counter())
            if cn[top] < 1 or cn[K if top == M else M] > 0:
                return None  # navnet er ikke belagt i personens egen navneskik
        return top, f"fornavn »{p['given'][0]}« {c[top]}/{n}"

    # Evaluering af nationalitetsværnet på markør-etiketter (CV)
    ev_name = [p for p in persons if p["ref_wo"]["NAME"] and not p["stub"]]
    guard_eval = {}
    for guard in (False, True):
        cov = cor = cov_f = cor_f = 0
        for tr, te in cv_splits(ev_name, [group_key(p) for p in ev_name]):
            cnt, cnt_nat = name_counts([ev_name[i] for i in tr], lambda p: p["ref_wo"]["NAME"])
            for i in te:
                q = ev_name[i]
                r = name_rule(q, cnt, cnt_nat, guard)
                if r:
                    ok = r[0] == q["ref_wo"]["NAME"]
                    cov += 1
                    cor += ok
                    if q["nat"] not in HOME_NATS:
                        cov_f += 1
                        cor_f += ok
        guard_eval["med værn" if guard else "uden værn"] = {
            "dækning_n": cov, "dækning": cov / len(ev_name), "præcision": cor / cov if cov else None,
            "fremmed_nationalitet_dækket": cov_f,
            "fremmed_nationalitet_præcision": cor_f / cov_f if cov_f else None}
    summary["name_rule_guard_eval"] = guard_eval

    cnt, cnt_nat = name_counts(ev_name, lambda p: p["ref_wo"]["NAME"])

    def s1(p):
        return name_rule(p, cnt, cnt_nat, guard=True)

    # Erhvervsleksikon: n ≥ 5 og Wilson-nedre ≥ 0,90, optalt på etiketter,
    # der ikke afhænger af beskrivelsen.
    tB = build_rule_table([fn_occ(p) for p in ev_o], [p["ref_wo"]["DESC"] for p in ev_o], 5, 0.90)

    def cascade(p):
        """S2: titel i beskrivelse → fornavn → erhverv. Uenighed → ubestemt."""
        votes = []
        t = desc_title(p["desc"], TMAP)
        if t:
            votes.append((TMAP[t], f"titel »{t}« i beskrivelsen"))
        a = s1(p)
        if a:
            votes.append(a)
        b = tB.get(fn_occ(p))
        if b and not a:
            votes.append((b[0], f"erhverv »{fn_occ(p)}« {b[1]}/{b[2]}"))
        if not votes:
            return None, ""
        if len({v[0] for v in votes}) > 1:
            return None, "konflikt: " + "; ".join(v[1] for v in votes)
        return votes[0][0], "; ".join(v[1] for v in votes)

    # Kaskadens samlede præcision på uafhængige etiketter: hvert led måles på
    # de etiketter, der ikke afhænger af leddets egen familie.
    t_rule = [p for p in persons if p["ref_wo"]["DESC"] and not p["stub"]]
    hits = [(TMAP[desc_title(p["desc"], TMAP)], p["ref_wo"]["DESC"]) for p in t_rule
            if desc_title(p["desc"], TMAP)]
    summary["desc_title_rule_eval"] = {
        "dækning_n": len(hits), "n_eval": len(t_rule),
        "præcision": sum(a == b for a, b in hits) / len(hits) if hits else None,
        "ukendte_dækket": sum(1 for p in unk_live if desc_title(p["desc"], TMAP))}

    # S3: logistisk regression uden metadata (metadata gav en falsk kvindelig
    # skævhed på efternavns-poster, se stikprøven), isotonisk kalibreret og
    # prior-korrigeret (Saerens et al. 2002): træningsetiketterne er ~45 % K,
    # de ukendte langt færre.
    use_s3 = ("name", "surname", "desc", "nat")
    yb_pool = np.array([1 if p["ref_all"] == K else 0 for p in pool])
    dvc = DictVectorizer()
    Xc = dvc.fit_transform([feat_dict(p, mterms, nat_words, title_terms, use_s3) for p in pool])
    mc = make_lr(True).fit(Xc, yb_pool)
    pc_raw = mc.predict_proba(dvc.transform(
        [feat_dict(p, mterms, nat_words, title_terms, use_s3) for p in unk_live]))[:, 1]
    pi_t = float(yb_pool.mean())
    pi_u, pc = em_prior(pc_raw, pi_t)
    summary["prior"] = {"træning_andel_K": pi_t, "ukendte_estimeret_andel_K": pi_u}

    def has_evidence(p):
        return bool(p["given"] or fn_occ(p) or desc_title(p["desc"], TMAP))

    pred_rows = []
    for p, q_raw, q in zip(unk_live, pc_raw, pc):
        a = s1(p)
        g2, why2 = cascade(p)
        conf3 = float(max(q, 1 - q))
        g3 = (K if q > 0.5 else M) if has_evidence(p) else None
        pred_rows.append({
            "entity_id": p["id"], "label": p["label"], "beskrivelse": p["desc"][:160],
            "nationalitet": p["nat"],
            "S1_fornavn": a[0] if a else "", "S1_grundlag": a[1] if a else "",
            "S2_kaskade": g2 or "", "S2_grundlag": why2,
            "S3_lr": g3 or "", "S3_p_kvinde_rå": round(float(q_raw), 4),
            "S3_p_kvinde": round(float(q), 4), "S3_konf": round(conf3, 4),
            "har_evidens": has_evidence(p),
        })
    write_csv("unknown_predictions.csv", pred_rows)

    def final(r, thr=0.98):
        """Anbefalet kombination: S2 først. LR må kun udfylde MANDLIGE poster
        med evidens — dens kvindelige forudsigelser holdt ikke i stikprøven
        (romanske mandsnavne på -ine/-a/-e læses som kvindelige), og et
        LR-veto over S2 fjernede kun korrekte mænd (Jean-Marie, Antoine)."""
        if r["S2_kaskade"]:
            return r["S2_kaskade"], "S2"
        if r["S3_lr"] == M and r["S3_konf"] >= thr and not r["S2_grundlag"].startswith("konflikt"):
            return M, "S3"
        return None, ""

    cov = {"ukendte i alt": len(unk), "udelukket (ikke enkeltperson/henvisning)": len(unk) - len(unk_live),
           "ukendte ekskl. udelukkede": len(unk_live)}
    for key, col in (("S1 fornavn (med værn)", "S1_fornavn"), ("S2 titel→fornavn→erhverv", "S2_kaskade")):
        sel = [r for r in pred_rows if r[col]]
        cov[key] = {"n": len(sel), "andel": len(sel) / len(unk_live),
                    "K": sum(r[col] == K for r in sel), "M": sum(r[col] == M for r in sel)}
    cov["S2 konflikter (efterlades ubestemt)"] = sum(
        1 for r in pred_rows if r["S2_grundlag"].startswith("konflikt"))
    for thr in THRESHOLDS:
        for lab, col in (("S3 LR rå", "S3_p_kvinde_rå"), ("S3 LR prior-korrigeret", "S3_p_kvinde")):
            sel = [r for r in pred_rows if r["har_evidens"] and max(r[col], 1 - r[col]) >= thr]
            cov[f"{lab} ≥ {thr}"] = {"n": len(sel), "andel": len(sel) / len(unk_live),
                                     "K": sum(1 for r in sel if r[col] > 0.5),
                                     "M": sum(1 for r in sel if r[col] < 0.5)}
    for thr in (0.95, 0.98, 0.99):
        fin = Counter(final(r, thr) [1] for r in pred_rows)
        g = Counter(final(r, thr)[0] for r in pred_rows)
        cov[f"Anbefalet (S2 + S3-mand ≥ {thr})"] = {
            "n": g[K] + g[M], "andel": (g[K] + g[M]) / len(unk_live), "K": g[K], "M": g[M],
            "fra S2": fin["S2"], "fra S3": fin["S3"]}
    summary["unknown_coverage"] = cov
    for r in pred_rows:
        g, src = final(r)
        r["anbefalet"] = g or ""
        r["anbefalet_kilde"] = src
    write_csv("unknown_predictions.csv", pred_rows)

    # Regel-tabeller som inspicerbare filer
    write_csv("rule_occupation_table.csv",
              [{"erhvervsord": k, "køn": v[0], "k": v[1], "n": v[2], "wilson_nedre": round(v[3], 3)}
               for k, v in sorted(tB.items(), key=lambda kv: -kv[1][2])])

    # Mulige fejl i den EKSISTERENDE kategorisering: kvinder, hvis eneste
    # evidens er fornavnet, men hvis erhverv er (næsten) udelukkende mandligt.
    male_occ = {r["erhvervsord"] for r in occ_rows
                if r["n"] >= 10 and r["andel_top"] >= 0.97 and r["retning"] == M}
    write_csv("existing_label_suspects.csv", [
        {"entity_id": p["id"], "label": p["label"], "beskrivelse": p["desc"][:120],
         "erhvervsord": fn_occ(p), "eksisterende_køn": "Kvindelig",
         "mistanke": "kun fornavn som evidens, men mandsdomineret erhverv"}
        for p in persons if not p["stub"] and p["existing"] == K
        and p["families"] == {"NAME"} and fn_occ(p) in male_occ])

    # Fejleksempler fra regelkaskaden (til dokumentation)
    errs = rule_errs[("fornavn (stavevariant)", 5, 0.90)] + \
        rule_errs[("erhverv (første ord i beskrivelsens hoved)", 5, 0.90)]
    write_csv("rule_errors.csv", [{"label": e[0], "beskrivelse": e[1], "nøgle": e[2],
                                   "forudsagt": e[3], "reference": e[4]} for e in errs])

    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=lambda o: dict(o) if isinstance(o, Counter) else str(o))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=lambda o: dict(o) if isinstance(o, Counter) else str(o)))


if __name__ == "__main__":
    main()
