#!/usr/bin/env python3
"""
extract_collin_letter_pages.py
--------------------------------
Extracts every letter heading ("<N>. Fra/Til <Person>.") across the four
LETTER volumes (I-IV, 1828-43/1844-60/1861-66/1867-75) of H. C.
Andersens Brevveksling med Edvard og Henriette Collin, with its printed
page range and dateline where one is printed near the heading.

Only 4 of the 6 physical volumes carry letter text -- confirmed from
each PDF's own title page, not assumed: vol. V is "BIND V . KOMMENTAR"
(a line-by-line annotation/commentary volume, organized by letter
number but containing explanatory notes, not the letters themselves)
and vol. VI is "BIND VI . REGISTRE" (the index/register volume this
project already digitized separately -- see collin-place-index.md /
collin-person-index.md). Both were checked directly and have zero
"<N>. Fra/Til <Person>." headings, as expected.

This is the per-letter table that match_collin_letter_ids.py samples
from and interpolates over -- see that script and
~/.claude/skills/letter_edition_boundaries.md for the methodology
(heading pattern, printed-page-number extraction, known OCR quirks)
this reuses from lookup_collin_letter_by_page.py.

Output: data/curated/collin_letter_pages.csv -- one row per letter:
  volume, letter_no, direction (Fra/Til), person, pdf_page_start,
  printed_page_start, printed_page_end, dateline_iso (blank if none
  printed near the heading)

Run from the repo root:
  python scripts/correspondence/extract_collin_letter_pages.py
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
VOL_DIR = (r"C:\Users\nh\Syddansk Universitet\HCA-MS - Documents"
           r"\forskning_HCA\BEC Breve til Edvard og Henriette Collin")
VOL_FILE = "andersen-hc_breve-collin_{n}.pdf"
OUT_CSV = os.path.join(ROOT, "data", "curated", "collin_letter_pages.csv")

PAREN_YEAR_RE = re.compile(r"\(1[78]\d\d\)")
PAGE_NO_RE = re.compile(r"^[il](\d+)$|^(\d+)$")

GARBLED_NUMBER = {"II": "11"}
HEADING_RE = re.compile(
    r"^(?P<num>[IVXLC]+|\d+)\.\s+(?P<dir>Fra|Til)\s+(?P<person>.+?)\.?\s*$",
    re.MULTILINE)

DATELINE_RE = re.compile(
    r"^(?P<place>[A-ZÆØÅ][\w. ]{1,25}?)[:.,]?\s+(?:den\s+|d\.?\s*)?"
    r"(?P<day>\d{1,2})(?:te|de|\.)?\s*"
    r"(?P<month>Jan\w*|Febr\w*|Marts|April|Maj|Jun\w*|Jul\w*|Aug\w*|"
    r"Sept\w*|Okt\w*|Nov\w*|Dec\w*)\.?\s*(?P<year>1[78]\d\d)\.?\s*$",
    re.MULTILINE)

MONTHS = {"jan": 1, "febr": 2, "marts": 3, "april": 4, "maj": 5, "jun": 6,
          "jul": 7, "aug": 8, "sept": 9, "okt": 10, "nov": 11, "dec": 12}


def month_num(name):
    key = name.lower()[:4].rstrip(".")
    for prefix, n in MONTHS.items():
        if key.startswith(prefix):
            return n
    return None


def parse_page_number(line):
    stripped = PAREN_YEAR_RE.sub("", line).strip()
    if not stripped:
        return None
    m = PAGE_NO_RE.match(stripped)
    if not m:
        return None
    digits = m.group(1) or m.group(2)
    if m.group(1):
        digits = "1" + digits
    num = int(digits)
    # A bare (unparenthesized) year -- e.g. a period-marker line reading
    # just "1830" -- matches the same digits-only shape as a page number
    # but isn't one; no volume here exceeds ~503 printed pages, so
    # anything in the plausible-year range is rejected rather than
    # accepted as a page number.
    if 1700 <= num <= 1999:
        return None
    return num


def dateline_to_iso(m):
    mn = month_num(m.group("month"))
    if not mn:
        return None
    return f"{m.group('year')}-{mn:02d}-{int(m.group('day')):02d}"


def process_volume(vol):
    path = os.path.join(VOL_DIR, VOL_FILE.format(n=vol))
    doc = fitz.open(path)
    page_texts = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()

    # Printed-page-number index, from each page's own running header.
    printed_of = {}
    for i, text in enumerate(page_texts):
        head = [l.strip() for l in text.split("\n")[:3] if l.strip()]
        for line in head:
            num = parse_page_number(line)
            if num is not None:
                printed_of[i] = num
                break

    def nearest_printed(pdf_idx):
        for i in range(pdf_idx, -1, -1):
            if i in printed_of:
                return printed_of[i]
        return None

    headings = []  # (pdf_idx, num, direction, person)
    for i, text in enumerate(page_texts):
        for m in HEADING_RE.finditer(text):
            num = GARBLED_NUMBER.get(m.group("num"), m.group("num"))
            headings.append((i, num, m.group("dir"), m.group("person").strip()))

    letters = []
    for idx, (pdf_idx, num, direction, person) in enumerate(headings):
        next_pdf_idx = headings[idx + 1][0] if idx + 1 < len(headings) else len(page_texts) - 1
        # Dateline: search the heading's own page, then the page(s) up to
        # (not including) the next heading -- covers both "date leads"
        # and "date closes near the signature" placements.
        dateline_iso = ""
        for search_idx in range(pdf_idx, min(next_pdf_idx + 1, len(page_texts))):
            dm = DATELINE_RE.search(page_texts[search_idx])
            if dm:
                iso = dateline_to_iso(dm)
                if iso:
                    dateline_iso = iso
                    break
        letters.append({
            "volume": vol,
            "letter_no": num,
            "direction": direction,
            "person": person,
            "pdf_page_start": pdf_idx,
            "printed_page_start": nearest_printed(pdf_idx) or "",
            "printed_page_end": nearest_printed(next_pdf_idx) or "",
            "dateline_iso": dateline_iso,
        })
    return letters


def main():
    all_letters = []
    for vol in range(1, 5):
        print(f"Volume {vol} …")
        letters = process_volume(vol)
        print(f"  {len(letters)} letter headings found")
        all_letters.extend(letters)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_letters[0].keys()))
        w.writeheader()
        w.writerows(all_letters)
    print(f"\nwrote {os.path.relpath(OUT_CSV, ROOT)}  ({len(all_letters)} total letters)")
    with_date = sum(1 for l in all_letters if l["dateline_iso"])
    print(f"{with_date} of {len(all_letters)} have a resolved dateline ({100*with_date//len(all_letters)}%)")


if __name__ == "__main__":
    main()
