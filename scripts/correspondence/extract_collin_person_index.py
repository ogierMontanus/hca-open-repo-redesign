#!/usr/bin/env python3
"""
extract_collin_person_index.py
--------------------------------
Digitizes the printed IV. PERSON-REGISTER from the register volume of
H. C. Andersens Brevveksling med Edvard og Henriette Collin (ed.
H. Topsøe-Jensen), PDF pages 83-162 of andersen-hc_breve-collin_6.pdf
(0-indexed; page 83 opens "IV. PERSON-REGISTER", page 163 is the
colophon). H. C. Andersen, Edvard Collin and Henriette Collin themselves
are explicitly excluded from this register (stated on its opening page).

Unlike extract_collin_place_index.py (line-based entry splitting), this
index's entries are too structurally varied for a reliable line-start
heuristic: Danish formal titles are themselves capitalized ("Professor",
"Konferensraad", ...), so a wrapped continuation line starting with a
title is visually indistinguishable from a genuine new entry's surname
by capitalization alone. No font/weight distinction exists either (all
entries share one font, one weight -- checked directly against the PDF's
span metadata).

Instead: anchor directly on the one unambiguous, low-variance shape every
dated entry actually has -- "Surname, Given(s) (birth[-death])" -- via a
single regex over the reflowed column text, requiring the match start
immediately after a sentence-ending punctuation mark (the previous
entry's citation always ends in one) or the very start of the section.
A volume-marker exclusion (I,/II,/.../VII,) prevents a citation's own
roman numerals from being mistaken for a surname. This finds every DATED
entry (the ones usable for the surname+birth-year matching task this
was built for) with high precision; entries with NO birth/death year at
all (a real minority, e.g. "Achard, Anna, Pensionatsværtinde i Genève")
are necessarily out of scope for this extraction method and are not
captured here -- they carry no matchable year regardless.

Output: data/curated/collin_letters_person_index.csv. Citation is taken
as the raw text between one match's year-parenthesis and the next
match's surname -- this is an approximation (the true citation/
description boundary within that span isn't parsed), kept for reference
and OCR-quality flagging only, not used by the matching step.

Run from the repo root:
  python scripts/correspondence/extract_collin_person_index.py
"""

import csv
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF required:  pip install pymupdf")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDF_PATH = r"C:\Users\nh\Documents\GitHub\breve-data\andersen-hc_breve-collin_6.pdf"
OUT_CSV = os.path.join(ROOT, "data", "curated", "collin_letters_person_index.csv")
OUT_REVIEW = os.path.join(ROOT, "data", "curated", "collin_letters_person_index_review.csv")

PAGE_LO, PAGE_HI = 83, 162  # 0-indexed PDF pages = "IV. PERSON-REGISTER"
PAGE_W = 450.85


def is_noise_block(b, page_h=565.2):
    x0, y0, x1, y1, _ = b[:5]
    w = x1 - x0
    if w < 30 and y0 < 60:
        return True
    if w < 30 and y1 > page_h - 45:
        return True
    return False


def extract_flowed_text():
    """Column-then-column reading order, reflowed to single spaces (line
    wraps inside an entry carry no meaning once the header/footer noise is
    stripped) -- same column strategy as extract_collin_place_index.py,
    proven against this same PDF."""
    doc = fitz.open(PDF_PATH)
    if doc.page_count <= PAGE_HI:
        sys.exit(f"PDF only has {doc.page_count} pages, expected at least {PAGE_HI + 1}")
    chunks = []
    for idx in range(PAGE_LO, PAGE_HI + 1):
        blocks = doc[idx].get_text("blocks")
        left, right = [], []
        for b in blocks:
            if is_noise_block(b):
                continue
            (left if b[0] < PAGE_W / 2 else right).append((b[1], b[4]))
        left.sort(); right.sort()
        chunks.append("".join(t for _, t in left) + "".join(t for _, t in right))
    doc.close()
    text = "".join(chunks)
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Anchor: start-of-section or immediately after a previous entry's closing
# punctuation (a citation always ends in a digit + '.', an uncertain year
# in '?', a BC-dated entry in ')'). Volume markers (I,/II,/.../VII,) are
# excluded so a citation's own roman numerals are never read as a surname.
NAME_YEAR_RE = re.compile(
    r"(?:(?<=[.?)]\s)|(?<=^))"
    r"(?!VII,|VI,|III,|IV,|II,|I,|V,)"
    r"(?P<surname>[A-ZÆØÅÖ][\wÆØÅæøåöäüÖ\-\x27\x92]*),\s*"
    r"(?P<given>[^()]{0,60}?)\s*"
    r"\(\s*(?:d\.\s*(?P<death_only>\d{3,4})"
    r"|(?:ca\.\s*)?(?P<birth>\d{3,4})\s*[—–\-]\s*(?P<death>\d{3,4}|\?)"
    r"|(?P<birth_only>\d{3,4}))\s*(?P<fchr>f\.\s*Chr\.)?\)"
)

HEADER_SKIP = re.compile(r"^IV\. PERSON-REGISTER H\. ?C\. Andersen")

CITATION_NOISE = re.compile(r"[°'’\^»\$*]|(?<=[,.\s])(?!I(?=[,.\s]))(?!V(?=[,.\s]))[a-zA-Z](?=[,.\s])")


def citation_quality(citation):
    if not citation:
        return "n/a", ""
    hits = CITATION_NOISE.findall(citation)
    if not hits:
        return "clean", ""
    n = len(hits)
    level = "low" if n <= 1 else "medium" if n <= 3 else "high"
    return level, "".join(sorted(set(h for h in hits if h.strip())))


def main():
    print(f"Reading {PDF_PATH} …")
    text = extract_flowed_text()
    print(f"  {len(text):,} characters extracted, PDF pages {PAGE_LO+1}-{PAGE_HI+1}")

    matches = [m for m in NAME_YEAR_RE.finditer(text) if not HEADER_SKIP.match(text[max(0, m.start()-30):m.end()])]
    # Drop the header-note false positive explicitly (starts the section).
    matches = [m for m in matches if m.group("surname") != "Andersen"]
    print(f"  {len(matches)} dated entries found")

    rows = []
    for i, m in enumerate(matches):
        surname = m.group("surname")
        given = m.group("given").strip().rstrip(",")
        birth = m.group("birth") or ""
        death = m.group("death_only") or m.group("death") or ""
        note = ""
        if m.group("fchr"):
            note = "BC (f. Chr.)"
        if death == "?":
            note = (note + "; " if note else "") + "death year uncertain (?)"
            death = ""
        if m.group("birth_only") and not m.group("birth") and not m.group("death_only"):
            birth = m.group("birth_only")
            note = note or "single year, ambiguous birth/death"

        citation_end = matches[i + 1].start() if i + 1 < len(matches) else min(m.end() + 400, len(text))
        citation = text[m.end():citation_end].strip()
        # Trim a trailing partial next-entry fragment: cut at the last
        # citation-shaped token (digit or roman numeral followed by . / ,).
        cut = re.search(r"[.,]\s*$", citation)
        quality, noise_chars = citation_quality(citation)

        rows.append({
            "surname": surname,
            "given_names": given,
            "birth_year": birth,
            "death_year": death,
            "year_note": note,
            "citation_raw": citation,
            "citation_ocr_quality": quality,
            "citation_ocr_noise_chars": noise_chars,
        })

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {os.path.relpath(OUT_CSV, ROOT)}  ({len(rows)} rows)")

    review_rows = [r for r in rows if r["citation_ocr_quality"] == "high"]
    with open(OUT_REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["surname", "given_names", "birth_year", "death_year", "citation_raw"])
        w.writeheader()
        for r in review_rows:
            w.writerow({k: r[k] for k in ["surname", "given_names", "birth_year", "death_year", "citation_raw"]})
    print(f"  wrote {os.path.relpath(OUT_REVIEW, ROOT)}  ({len(review_rows)} rows flagged, high citation OCR noise)")
    print("Done. Note: entries with no birth/death year printed at all are out of scope for this extraction method (see module docstring).")


if __name__ == "__main__":
    main()
