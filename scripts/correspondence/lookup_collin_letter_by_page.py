#!/usr/bin/env python3
"""
lookup_collin_letter_by_page.py
--------------------------------
Given a (volume, printed page) reference into H. C. Andersens Brevveksling
med Edvard og Henriette Collin (ed. C. Behrend og H. Topsøe-Jensen,
1933-45), find:

  1. the PDF page in the corresponding volume file,
  2. the letter number + sender/addressee heading that page belongs to
     (a page can be mid-letter; the heading may be on an earlier page),
  3. a dateline near that heading, if one is printed there,
  4. the matching row in BrevBasen.csv, if the dateline's date is unique
     among letters tagged with this edition's Titel/HerkomstID.

This is prep work for a volume+page -> BrevBasen letter-id (BrevID)
mapping: the user has a printed copy with pencilled letter-id references
next to volume+page citations and will supply ~12 samples to validate
this script's output against. Nothing here is written back to any curated
CSV yet -- this only proposes matches for human verification, the same
propose/verify shape as every other cross-reference in this project
(works_wikidata.csv, breve_person_crosswalk.csv, ...).

Source PDFs (NOT part of this repo -- a location outside both this
checkout and the breve-data sibling checkout, since only volume 6 lives
in breve-data):
  C:\\Users\\nh\\Syddansk Universitet\\HCA-MS - Documents\\forskning_HCA\\
  BEC Breve til Edvard og Henriette Collin\\andersen-hc_breve-collin_{1..6}.pdf
  Digitized by Claus Rønlev (per each PDF's own title page).

BrevBasen.csv (46 MB, cp1252, ';'-delimited) lives in the breve-data
sibling checkout: C:\\Users\\nh\\Documents\\GitHub\\breve-data\\BrevBasen.csv
Letters belonging to this printed edition carry
  Titel = "H. C. Andersens Brevveksling med Edvard og Henriette Collin"
  HerkomstID = "83"
in every row checked so far (90 rows, scan of the full file) -- confirmed
against a self-verified example below, not merely asserted:
  Vol. I printed p. 17-18: letter "10. Fra E. Collin.", dateline
  "Kjøbenhavn: d 12. Junii 1830." -> BrevBasen ID=BrevID=372,
  Dato=1830-06-12, Titel/HerkomstID as above. Exactly one row matches
  that date among Collin-edition rows.

Letter-boundary pattern this script looks for (see the general writeup
at ~/.claude/skills/letter_edition_boundaries.md for the reusable
methodology beyond this one edition):
  - START: a line "<number>. Fra <sender>." or "<number>. Til <addressee>."
    Numbers are Arabic but the extracted text can render some of them as
    Roman-numeral-looking strings (e.g. "II." for "11.") because of how
    this typeface's "1" glyph extracts -- GARBLED_NUMBER below handles
    the cases seen so far; treat any unmatched leading token followed by
    "Fra"/"Til" as a signal to inspect manually rather than guess.
  - DATELINE: near the heading (immediately after it, or just before the
    closing signature) -- "<Place>. d. <day>. <month> <year>." or
    "<Place>: d <day>. <month> <year>." Month names are the old Danish
    forms (Januar..December, Junii/Juli with the -ii spelling still in
    use in 1830).
  - END: a valediction phrase ("Deres", "Deres hengivne", "Deres af
    Hjertet hengivne" ...) immediately followed by the signature name on
    its own line.
  - NOT part of the letter: small-print textual-critical footnotes at
    the foot of a page, keyed to line numbers, phrases like "Mskr. har..."
    (the manuscript has...) or "først skrevet..." (originally written...).
  - Running header on every page carries the year (parenthesized on one
    of recto/verso, not the other) and the PRINTED page number -- this
    is what lets citations like "I, 17." be resolved to a PDF page at all.

Run from the repo root:
  python scripts/correspondence/lookup_collin_letter_by_page.py --vol 1 --page 17
  python scripts/correspondence/lookup_collin_letter_by_page.py --batch samples.csv
    (samples.csv: columns vol,page[,pencil_id] -- pencil_id optional, used
     only to print a match/mismatch column when supplied)
"""

import argparse
import csv
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF not installed. Run: pip install pymupdf")

VOL_DIR = (r"C:\Users\nh\Syddansk Universitet\HCA-MS - Documents"
           r"\forskning_HCA\BEC Breve til Edvard og Henriette Collin")
VOL_FILE = "andersen-hc_breve-collin_{n}.pdf"
BREVBASEN_CSV = r"C:\Users\nh\Documents\GitHub\breve-data\BrevBasen.csv"
EDITION_TITEL = "H. C. Andersens Brevveksling med Edvard og Henriette Collin"

# Printed page number, alone on a line or sharing a line with the
# parenthesized running-header year (concatenated with no space on recto
# pages: "i6(1830)"; on separate lines on verso pages: "(1830)" then "i9").
# A leading "i" or "l" is not a prefix to strip -- it IS the digit "1",
# extracted that way from this typeface for any 10-19 page number ("i7" =
# printed page 17, not "7"). Two-digit-and-up numbers with no leading 1
# (e.g. "20") extract as plain digits.
PAREN_YEAR_RE = re.compile(r"\(1[78]\d\d\)")
PAGE_NO_RE = re.compile(r"^[il](\d+)$|^(\d+)$")


def parse_page_number(line):
    """Return an int page number from one running-header line, or None."""
    stripped = PAREN_YEAR_RE.sub("", line).strip()
    if not stripped:
        return None
    m = PAGE_NO_RE.match(stripped)
    if not m:
        return None
    digits = m.group(1) or m.group(2)
    if m.group(1):  # leading i/l stood in for "1"
        digits = "1" + digits
    return int(digits)

# Letter heading: "<num>. Fra/Til <Person>." — GARBLED_NUMBER covers the
# Roman-numeral-looking renderings of Arabic numbers seen so far (only
# "II." for "11." confirmed; extend as more are found).
GARBLED_NUMBER = {"II": "11"}
HEADING_RE = re.compile(
    r"^(?P<num>[IVXLC]+|\d+)\.\s+(?P<dir>Fra|Til)\s+(?P<person>.+?)\.?\s*$",
    re.MULTILINE)

DATELINE_RE = re.compile(
    r"^(?P<place>[A-ZÆØÅ][\w. ]{1,25}?)[:.,]?\s+d\.?\s*(?P<day>\d{1,2})\.?\s*"
    r"(?P<month>Jan\w*|Febr\w*|Marts|April|Maj|Jun\w*|Jul\w*|Aug\w*|"
    r"Sept\w*|Okt\w*|Nov\w*|Dec\w*)\.?\s*(?P<year>1[78]\d\d)\.?\s*$",
    re.MULTILINE)

MONTHS = {
    "jan": 1, "febr": 2, "marts": 3, "april": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sept": 9, "okt": 10, "nov": 11, "dec": 12,
}


def month_num(name):
    key = name.lower()[:4].rstrip(".")
    for prefix, n in MONTHS.items():
        if key.startswith(prefix):
            return n
    return None


def open_volume(vol):
    path = os.path.join(VOL_DIR, VOL_FILE.format(n=vol))
    if not os.path.exists(path):
        sys.exit(f"Volume file not found: {path}")
    return fitz.open(path)


def printed_page_index(doc, max_pages=None):
    """Map printed page number -> PDF page index, for every page whose
    running header yields an unambiguous number. Skips pages where the
    first two lines don't look like a plain page number (front matter,
    section-opening pages with no visible number, register sections in
    a different layout)."""
    index = {}
    n = max_pages or doc.page_count
    for i in range(n):
        text = doc[i].get_text()
        head = [l.strip() for l in text.split("\n")[:3] if l.strip()]
        for line in head:
            num = parse_page_number(line)
            if num is not None:
                index.setdefault(num, i)
                break
    return index


def find_letter_on_page(doc, pdf_page_idx, lookback=3):
    """Return (heading_match_dict, heading_pdf_page, dateline) for the
    letter that owns pdf_page_idx -- walking backward if the page itself
    has no heading (i.e. the page is mid-letter)."""
    for back in range(lookback + 1):
        idx = pdf_page_idx - back
        if idx < 0:
            break
        text = doc[idx].get_text()
        matches = list(HEADING_RE.finditer(text))
        if matches:
            m = matches[-1] if back > 0 else matches[0]
            num = m.group("num")
            num = GARBLED_NUMBER.get(num, num)
            # Look for a dateline on the same page as the heading, or the
            # target page itself (datelines can trail near the signature
            # instead of leading the letter).
            dateline = None
            for search_idx in {idx, pdf_page_idx}:
                dm = DATELINE_RE.search(doc[search_idx].get_text())
                if dm:
                    dateline = dm.groupdict()
                    break
            return {
                "letter_no": num,
                "direction": m.group("dir"),
                "person": m.group("person").strip(),
                "heading_pdf_page": idx,
            }, dateline
    return None, None


def dateline_to_iso(dateline):
    if not dateline:
        return None
    mn = month_num(dateline["month"])
    if not mn:
        return None
    return f"{dateline['year']}-{mn:02d}-{int(dateline['day']):02d}"


def match_brevbasen(iso_date):
    if not iso_date or not os.path.exists(BREVBASEN_CSV):
        return []
    out = []
    with open(BREVBASEN_CSV, encoding="cp1252", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("Dato") == iso_date and row.get("Titel") == EDITION_TITEL:
                out.append({"ID": row.get("ID"), "BrevID": row.get("BrevID"),
                            "HerkomstID": row.get("HerkomstID")})
    return out


def lookup(vol, page, pencil_id=None):
    doc = open_volume(vol)
    pmap = printed_page_index(doc)
    if page not in pmap:
        return {"vol": vol, "page": page, "error": "printed page not found "
                f"in running headers (have {min(pmap)}-{max(pmap)} if any)"
                if pmap else "printed page not found (no headers indexed)"}
    pdf_idx = pmap[page]
    heading, dateline = find_letter_on_page(doc, pdf_idx)
    iso_date = dateline_to_iso(dateline)
    matches = match_brevbasen(iso_date)
    result = {
        "vol": vol, "page": page, "pencil_id": pencil_id,
        "pdf_page_index_0based": pdf_idx,
        "heading": heading, "dateline": dateline, "iso_date": iso_date,
        "brevbasen_matches": matches,
    }
    doc.close()
    return result


def print_result(r):
    print(f"--- Vol. {r['vol']}, printed p. {r['page']} ---")
    if r.get("error"):
        print("  ERROR:", r["error"])
        return
    print(f"  PDF page index (0-based): {r['pdf_page_index_0based']}")
    h = r["heading"]
    if h:
        print(f"  Letter {h['letter_no']}. {h['direction']} {h['person']}."
              f" (heading on PDF page {h['heading_pdf_page']})")
    else:
        print("  No letter heading found within lookback window.")
    if r["dateline"]:
        d = r["dateline"]
        print(f"  Dateline: {d['place']}, {d['day']}. {d['month']} {d['year']}"
              f"  ->  ISO {r['iso_date']}")
    else:
        print("  No dateline found near heading.")
    bm = r["brevbasen_matches"]
    if bm:
        for m in bm:
            print(f"  BrevBasen match: ID=BrevID={m['BrevID']} "
                  f"HerkomstID={m['HerkomstID']}"
                  + (" -- unique" if len(bm) == 1 else " -- AMBIGUOUS, multiple rows share this date"))
    elif r["iso_date"]:
        print("  No BrevBasen row found for this date under the Collin edition Titel.")
    if r.get("pencil_id"):
        if bm and str(bm[0]["BrevID"]) == str(r["pencil_id"]):
            print(f"  Pencilled id {r['pencil_id']}: MATCH")
        else:
            print(f"  Pencilled id {r['pencil_id']}: NO MATCH against derived result -- needs review")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vol", type=int, help="Volume number 1-6")
    ap.add_argument("--page", type=int, help="Printed page number")
    ap.add_argument("--batch", help="CSV with columns vol,page[,pencil_id]")
    args = ap.parse_args()

    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = lookup(int(row["vol"]), int(row["page"]), row.get("pencil_id"))
                print_result(r)
                print()
    elif args.vol and args.page:
        print_result(lookup(args.vol, args.page))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
