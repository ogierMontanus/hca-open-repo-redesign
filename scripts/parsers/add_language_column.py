#!/usr/bin/env python3
"""Append `probable_language` (ISO 639-1) and `language_confidence` columns
to any parsed TSV produced by the register parsers.

Detection input: concatenation of `04_main_title` + creator column for
maximum signal. Norwegian Bokmål (nb) is remapped to da — written Bokmål
and Danish are near-identical, and both route to REX/KB for OPAC lookup.

Language set covers the languages present in the registers:
  da Danish        nb Norwegian Bokmål (→ da)
  de German        sv Swedish
  fr French        nl Dutch
  en English       it Italian
  la Latin         es Spanish
  pt Portuguese

Usage:
    python add_language_column.py <input.tsv> [output.tsv]
"""

import argparse
import csv
import pathlib
from collections import Counter

from lingua import Language, LanguageDetectorBuilder


LANGUAGES = [
    Language.DANISH, Language.BOKMAL,
    Language.GERMAN, Language.SWEDISH,
    Language.FRENCH, Language.DUTCH,
    Language.ENGLISH, Language.ITALIAN,
    Language.LATIN, Language.SPANISH,
    Language.PORTUGUESE,
]

DETECTOR = LanguageDetectorBuilder.from_languages(*LANGUAGES).build()

TITLE_COL = "04_main_title"
CREATOR_COLS = ["06_creator", "05_creator"]

REMAP = {"nb": "da"}


def detect(title: str, creator: str) -> tuple[str, float]:
    text = " ".join(filter(None, [title.strip(), creator.strip()]))
    if not text:
        return "und", 0.0
    lang = DETECTOR.detect_language_of(text)
    if lang is None:
        return "und", 0.0
    conf_values = DETECTOR.compute_language_confidence_values(text)
    top_conf = sorted(conf_values, key=lambda x: x.value, reverse=True)[0].value
    code = lang.iso_code_639_1.name.lower()
    return REMAP.get(code, code), round(top_conf, 2)


def main_run(src: pathlib.Path, dst: pathlib.Path | None) -> None:
    dst_path = dst or src.with_stem(src.stem + "_lang")

    with open(src, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    creator_col = next((c for c in CREATOR_COLS if c in fieldnames), "")
    out_fields = fieldnames + ["probable_language", "language_confidence"]

    enriched = []
    for r in rows:
        title = r.get(TITLE_COL, "")
        creator = r.get(creator_col, "") if creator_col else ""
        lang, conf = detect(title, creator)
        r["probable_language"] = lang
        r["language_confidence"] = conf
        enriched.append(r)

    with open(dst_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, delimiter="\t")
        w.writeheader()
        w.writerows(enriched)

    counts = Counter(r["probable_language"] for r in enriched)
    low_conf = sum(1 for r in enriched if float(r["language_confidence"]) < 0.35)

    print(f"Written : {dst_path}")
    print(f"Rows    : {len(enriched)}")
    print(f"Language distribution:")
    for lang, n in counts.most_common():
        print(f"  {lang:<4}  {n}")
    print(f"Low confidence (< 0.35): {low_conf} rows — review manually")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=pathlib.Path)
    ap.add_argument("output", type=pathlib.Path, nargs="?", default=None)
    args = ap.parse_args()
    main_run(args.input, args.output)


if __name__ == "__main__":
    main()
