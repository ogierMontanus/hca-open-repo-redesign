#!/usr/bin/env python3
"""
extract_collin_work_index.py
------------------------------
Digitizes the printed I. VÆRK-REGISTER (works index) from the register
volume of H. C. Andersens Brevveksling med Edvard og Henriette Collin,
PDF pages 50-57 of andersen-hc_breve-collin_6.pdf (0-indexed; page 50
opens "I. VÆRK-REGISTER", page 58 opens "II. SAG-REGISTER"). Entries are
Andersen's own works, grouped under category headers ("Eventyr.",
"Digte.", "Rejseskildringer.", ...) that closely match this project's
own H3 work-category taxonomy for the Bibliotek wing.

Line-start heuristic (same as extract_collin_place_index.py): a work
title starts a new entry, its citation runs until the next title. Titles
don't share the place-index's "definite-article-inversion" problem, but
DO share its false-positive risk from short, capitalized-looking
citation fragments -- handled the same way (GARBLED_ROMAN exclusion).

Output: data/curated/collin_letters_work_index.csv (title, category
header the entry falls under, publication year if printed, citation).

Run from the repo root:
  python scripts/correspondence/extract_collin_work_index.py
"""

import csv
import os
import re
import sys

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF required:  pip install pymupdf")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDF_PATH = r"C:\Users\nh\Documents\GitHub\breve-data\andersen-hc_breve-collin_6.pdf"
OUT_CSV = os.path.join(ROOT, "data", "curated", "collin_letters_work_index.csv")

PAGE_LO, PAGE_HI = 50, 57  # 0-indexed = "I. VÆRK-REGISTER"
PAGE_W = 450.85

CATEGORY_RE = re.compile(r"^[A-ZÆØÅ][a-zæøå .\-]{2,35}\.\s*$")
GARBLED_ROMAN = re.compile(r"^(Ill|HI|H1|Il|IH|II|IV|VI)[,.\s]")
ENTRY_START = re.compile(r"^[A-ZÆØÅÖ][\wæøåÆØÅöäü’]")
YEAR_RE = re.compile(r"^\((\d{4})(?:\s*ff?\.?)?\)")
SEE_RE = re.compile(r"^(.*?),\s*se\s+(.+?)\.?\s*$")

# Section/sub-section labels within VÆRK-REGISTER's own internal layout,
# not works -- CATEGORY_RE's line-start heuristic misses these because
# some carry a parenthetical or lack a clean trailing period after OCR.
# Verified by direct inspection against the PDF, not guessed; extend this
# set if a future re-run's output CSV surfaces more of the same shape
# (short line, no citation, no year, reads as a label not a title).
KNOWN_HEADERS = {
    "Samlede og blandede Skrifter",
    "Eventyrene. (I Alm.)",
    "Eventyrene",
    "Oversættelser",
    "Eventyr-Samlinger (kronologisk)",
    "Enkelte Eventyr (alfabetisk)",
    "Enkelte Digte",
}


def is_noise_block(b, page_h=565.2):
    x0, y0, x1, y1, _ = b[:5]
    w = x1 - x0
    return (w < 30 and y0 < 60) or (w < 30 and y1 > page_h - 45)


def extract_lines():
    doc = fitz.open(PDF_PATH)
    lines = []
    for idx in range(PAGE_LO, PAGE_HI + 1):
        blocks = doc[idx].get_text("blocks")
        left, right = [], []
        for b in blocks:
            if is_noise_block(b):
                continue
            (left if b[0] < PAGE_W / 2 else right).append((b[1], b[4]))
        left.sort(); right.sort()
        page_text = "".join(t for _, t in left) + "".join(t for _, t in right)
        lines.extend(l for l in page_text.split("\n") if l.strip())
    doc.close()
    return lines


def split_entries(lines):
    entries, current, category = [], None, None
    for ln in lines:
        s = ln.strip()
        if s.startswith("I. VÆRK-REGISTER"):
            continue
        if CATEGORY_RE.match(s) and " " not in s.rstrip(".").split()[-1:] or (CATEGORY_RE.match(s) and len(s.split()) <= 4):
            # Heading candidates are short, end in a period, and (unlike a
            # citation-trailing entry) carry no digits at all.
            if not re.search(r"\d", s):
                category = s.rstrip(".")
                continue
        if ENTRY_START.match(s) and not GARBLED_ROMAN.match(s):
            if current is not None:
                entries.append((category, current))
            current = [s]
        else:
            if current is None:
                current = [s]
            else:
                current.append(s)
    if current is not None:
        entries.append((category, current))
    return entries


def parse_entry(category, raw_lines):
    text = " ".join(l.strip() for l in raw_lines)
    text = re.sub(r"\s+", " ", text).strip()

    sm = SEE_RE.match(text)
    if sm and not re.search(r"\d", sm.group(1)):
        return {
            "category": category or "", "title": sm.group(1).strip(),
            "year": "", "citation_raw": "", "see_also": sm.group(2).strip(),
            "issue_type": "",
        }

    ym = re.search(r"\((\d{4})\s*(f[fr]?\.?)?\)", text)
    year, title, citation, issue_type = "", text, "", ""
    if ym:
        title = text[:ym.start()].strip()
        citation = text[ym.end():].strip()
        year = ym.group(1)
        if ym.group(2):  # "(YYYY ff.)" / OCR "fr." -- an ongoing/multi-volume
            issue_type = "omnibus_collection"
    else:
        cm = re.search(r"\b(I|II|III|IV|V|VI),\s*\d", text)
        if cm:
            title = text[:cm.start()].strip()
            citation = text[cm.start():].strip()

    title = title.rstrip(",")
    if title in KNOWN_HEADERS:
        return None  # verified section/sub-section label, not a work

    # Serial/fascicle citation: title itself ends in a bare volume,issue
    # number ("Nye Eventyr og Historier 1,1" / "II,1" / "III, 1") rather
    # than a real title -- the printed index cites the installment, not a
    # story; no story-level match target exists on the site.
    if re.search(r"\b(?:\d{1,2}|I|II|III|IV|V)\s*,\s*\d\s*$", title):
        issue_type = "serial_installment"

    if not citation and not year and not issue_type and len(title) < 60:
        issue_type = "possible_fragment"  # likely a line-wrap split, unverified

    return {
        "category": category or "",
        "title": title,
        "year": year,
        "citation_raw": citation,
        "see_also": "",
        "issue_type": issue_type,
    }


def main():
    print(f"Reading {PDF_PATH} …")
    lines = extract_lines()
    entries = split_entries(lines)
    print(f"  {len(entries)} entries split")

    rows = [parse_entry(cat, raw) for cat, raw in entries]
    rows = [r for r in rows if r and r["title"]]

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {os.path.relpath(OUT_CSV, ROOT)}  ({len(rows)} rows)")
    cats = sorted(set(r["category"] for r in rows if r["category"]))
    print("Categories found:", cats)


if __name__ == "__main__":
    main()
