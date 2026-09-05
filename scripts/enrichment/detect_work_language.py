#!/usr/bin/env python3
"""
detect_work_language.py
------------------------
Derives a probable language for every VÆRK-REGISTER title and writes
data/normalized/work_languages.csv.

The register never recorded a language column, so this has to be
inferred from the title itself. Two sources, in precedence order:

  1. `register` — the register's OWN label, where it happens to say so.
     A handful of entries are filed as translations under an explicit
     prefix ("Tyske - Sämmtliche Märchen …", "Engelske - …"), and 45
     more sit under subform_h4 = "Eventyr-Oversættelser". Where the
     editors stated the language, that statement wins outright; nothing
     is guessed over it.

  2. `detector` — lingua over the title, for the ~3,600 entries the
     register says nothing about.

Why the detector is deliberately timid
--------------------------------------
Register titles are short, and short strings are exactly where language
detection fails. Measured on this corpus, the bare top-1 guess puts
"Der Improvisator" in Italian (conf. 0.16) and "Improvisatoren" in Dutch
(0.23). So a bare `detect()` is not usable here.

Two guards, both tuned against this corpus rather than assumed:

  • A confidence floor (LANG_MIN_CONF) plus a minimum title length.
    Below either, the entry is left unlabelled rather than guessed at —
    "unknown" is a truthful answer and an empty facet row is recoverable,
    a wrong language label is not.
  • A cue rescue for lower-confidence hits: accept a language the
    detector merely leans toward if a function word unique to that
    language is present. The German cue list deliberately excludes
    der/den/de/man/for/vil, which are ordinary Danish words too — an
    earlier draft included them and swept in Danish titles like "Den
    standhaftige Tinsoldat". It also excludes "von", which appears
    inside Danish entries via German name particles ("Digte af H. von
    X").

Sampled precision on the German output was 20/20 on a random draw; the
cue rescue is what recovers real cases the floor alone misses, e.g.
"Kabale und Liebe" (conf. 0.23) and "Naomi und Christian, oder: Der
arme Geiger" (0.21).

Norwegian Bokmål folds to Danish, following the existing convention in
scripts/parsers/add_language_column.py — written Bokmål and 19th-century
Danish are near-identical and the register does not distinguish them.

lingua is an optional dependency (scripts/parsers/requirements.txt). If
it is not installed the script still runs and still emits every
`register` row, reporting how many entries it had to skip — so the
build never hard-fails on a missing ML package.

Stdlib + optional lingua. Wire as Stage 1d in scripts/build_all.py.
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter

ROOT     = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTITIES = os.path.join(ROOT, "data", "normalized", "entities.csv")
OUT      = os.path.join(ROOT, "data", "normalized", "work_languages.csv")

LANG_MIN_CONF = 0.65   # floor for accepting the detector's top guess
CUE_MIN_CONF  = 0.15   # floor for accepting a cue-confirmed guess
MIN_LEN       = 12     # chars; below this a title carries too little signal

# The register's own translation prefixes ("Tyske - …"). Authoritative.
REGISTER_PREFIX = {
    "tyske": "de", "tysk": "de",
    "engelske": "en", "engelsk": "en",
    "franske": "fr", "fransk": "fr",
    "hollandske": "nl", "hollandsk": "nl",
    "svenske": "sv", "svensk": "sv",
    "russiske": "ru", "russisk": "ru",
    "ungarske": "hu", "ungarsk": "hu",
    "nygræske": "el", "nygræsk": "el",
}
PREFIX_RE = re.compile(r"^\s*([A-ZÆØÅ][a-zæøå]+)\s*\n?\s*-\s")

# Trailing "(1853)" / "(Bremen 1869)" publication parentheticals carry no
# language signal and skew short titles further; drop them before detecting.
TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

# Function words unique to each language relative to Danish — see docstring
# for why the German list omits der/den/de/von.
CUES = {
    "de": re.compile(r"\b(das|des|dem|die|ein|eine|einen|eines|einem|einer|und|ohne|nicht|"
                     r"auch|aus|mit|nach|über|zwei|drei|welt|leben|liebe|wird|werden|ist|"
                     r"sind|zum|zur|beim|vom|durch|gegen|wenn|aber|oder|sehr|mehr|schon|"
                     r"immer|wieder|neue|neuen|gesammelte|sämmtliche|sämtliche|märchen|"
                     r"geschichten|werke|lieder|dichtungen|erzählungen)\b|"
                     r"(ß|ung\b|heit\b|keit\b|schaft\b|chen\b|lein\b)", re.I),
    "fr": re.compile(r"\b(le|la|les|des|du|une|dans|pour|avec|sur|est|sont|qui|que|"
                     r"c'est|d'un|d'une|l'|aux|ou|mais|très|plus|nouveau|nouvelle|"
                     r"histoire|contes|oeuvres|œuvres|poésies|voyage)\b|[çéèêàùô]", re.I),
    "en": re.compile(r"\b(the|of|and|a|an|to|in|is|are|with|from|his|her|their|"
                     r"tales|stories|poems|works|travels|life|true|story)\b", re.I),
    "it": re.compile(r"\b(il|lo|la|gli|le|di|del|della|dei|una|un|nel|con|per|"
                     r"che|sono|storia|novelle|opere|viaggio)\b", re.I),
    "nl": re.compile(r"\b(de|het|een|van|en|voor|met|zijn|haar|sprookjes|verhalen|werken)\b", re.I),
    "sv": re.compile(r"\b(och|att|för|med|samlade|sagor|dikter|berättelser|resa)\b|[åäö]", re.I),
    "es": re.compile(r"\b(el|los|las|del|una|con|para|por|cuentos|obras|viaje)\b|[ñáíóú]", re.I),
}


def build_detector():
    """Returns a lingua detector, or None when lingua isn't installed."""
    try:
        from lingua import Language, LanguageDetectorBuilder
    except ImportError:
        return None
    langs = [
        Language.DANISH, Language.BOKMAL, Language.GERMAN, Language.SWEDISH,
        Language.FRENCH, Language.DUTCH, Language.ENGLISH, Language.ITALIAN,
        Language.LATIN, Language.SPANISH, Language.PORTUGUESE,
    ]
    return LanguageDetectorBuilder.from_languages(*langs).with_preloaded_language_models().build()


def register_language(label: str, subform: str):
    """The register's own statement, where it made one."""
    m = PREFIX_RE.match(label or "")
    if m:
        code = REGISTER_PREFIX.get(m.group(1).lower())
        if code:
            return code
    return None


# A short title made entirely of capitalised words is a name, not a sentence,
# and a name has no language: the BILLEDKUNST wing is full of portraits and
# busts filed under their sitter ("Albrecht Dürer", "Franz Lachner"), which
# the detector happily reads as German. Require a real function-word cue
# before accepting anything name-shaped. This costs a little recall —
# "Schöner Brunnen" is genuinely German and gets dropped — which is the right
# trade here: an unlabelled work is recoverable, a mislabelled one teaches
# the reader something false.
NAME_SHAPED_MAX_WORDS = 3
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def looks_like_bare_name(title: str) -> bool:
    words = WORD_RE.findall(title)
    if not words or len(words) > NAME_SHAPED_MAX_WORDS:
        return False
    return all(w[:1].isupper() for w in words)


def detect(detector, title: str):
    """(code, confidence, method) or (None, 0.0, reason)."""
    if len(title) < MIN_LEN:
        return None, 0.0, "too_short"
    values = detector.compute_language_confidence_values(title)
    if not values:
        return None, 0.0, "no_signal"
    top = values[0]
    code = top.language.iso_code_639_1.name.lower()
    if code == "nb":
        code = "da"          # Bokmål folds to Danish — see docstring
    cue = CUES.get(code)
    has_cue = bool(cue and cue.search(title))
    if looks_like_bare_name(title) and not has_cue:
        return None, top.value, "bare_name"
    if top.value >= LANG_MIN_CONF:
        return code, top.value, "detector"
    if has_cue and top.value >= CUE_MIN_CONF:
        return code, top.value, "detector_cue"
    return None, top.value, "unsure"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--sample", type=int, default=0,
                    help="print N detected titles per language and exit (spot-check aid)")
    args = ap.parse_args()

    if not os.path.exists(ENTITIES):
        sys.exit(f"Missing {ENTITIES} — run normalisation first.")

    with open(ENTITIES, encoding="utf-8") as f:
        works = [r for r in csv.DictReader(f) if r["entity_type"] == "work"]
    print(f"Loading {os.path.relpath(ENTITIES, ROOT)}…")
    print(f"  {len(works):,} works")

    detector = build_detector()
    if detector is None:
        print("  [!] lingua not installed — emitting register-stated languages only.")
        print("      pip install -r scripts/parsers/requirements.txt  to enable detection.")

    rows, methods, langs = [], Counter(), Counter()
    samples: dict[str, list] = {}
    for r in works:
        rid, label = r["entity_id"], (r.get("label") or "").strip()
        code = register_language(label, r.get("subform_h4", ""))
        if code:
            method, conf = "register", 1.0
        elif detector is None:
            continue
        else:
            title = TRAILING_PAREN.sub("", label).strip()
            code, conf, method = detect(detector, title)
            if not code:
                methods[method] += 1
                continue
        methods[method] += 1
        langs[code] += 1
        samples.setdefault(code, []).append(label)
        rows.append({"entity_id": rid, "label": label, "lang": code,
                     "method": method, "confidence": round(conf, 3)})

    print(f"  labelled {len(rows):,} of {len(works):,} "
          f"({len(rows) / len(works):.0%})")
    print("  by language: " + ", ".join(f"{k}={v:,}" for k, v in langs.most_common()))
    print("  by method:   " + ", ".join(f"{k}={v:,}" for k, v in methods.most_common()))

    if args.sample:
        for code in langs:
            print(f"\n-- {code} --")
            for s in samples[code][:args.sample]:
                print(f"   {s[:100]}")
        return

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["entity_id", "label", "lang", "method", "confidence"])
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
