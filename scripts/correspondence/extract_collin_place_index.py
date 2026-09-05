#!/usr/bin/env python3
"""
extract_collin_place_index.py
------------------------------
Digitizes the printed STED-REGISTER (place-name index) from the register
volume of H. C. Andersens Brevveksling med Edvard og Henriette Collin
(ed. H. Topsøe-Jensen), pp. 64-77 of the printed index = PDF pages 70-83
of andersen-hc_breve-collin_6.pdf (a fixed 6-page front-matter offset,
confirmed from the printed page numbers embedded in the OCR text itself:
PDF page 70 carries no visible number -- it is the section's opening page
-- PDF page 71 carries "65", ... PDF page 83 carries "77", immediately
followed on PDF page 84 by "IV. PERSON-REGISTER").

This is step 1 of the queued task recorded in this project's memory
(2026-08-24): digitize the PLACE-NAME index only. It deliberately does
NOT attempt to map these entries onto the six volumes of the letter
edition itself -- the citations (e.g. "II, 33, 37") are preserved exactly
as printed, not resolved or verified against the source volumes. That is
future work.

Source PDF: C:\\Users\\nh\\Documents\\GitHub\\breve-data\\andersen-hc_breve-collin_6.pdf
  (a sibling checkout, not part of this repo -- same shape as breve-data's
  role in docs/data-model/correspondence-integration.md).
  ABBYY FineReader PDF 15 OCR layer, two-column layout, 450x565pt pages.

Output: data/curated/collin_letters_place_index.csv -- see the module
docstring in that file's own header row / docs/data-model/
collin-place-index.md for the column meanings and the cleaning approach.

Run from the repo root:
  python scripts/correspondence/extract_collin_place_index.py
"""

import csv
import os
import re
import sys
import unicodedata

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF required:  pip install pymupdf")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PDF_PATH = r"C:\Users\nh\Documents\GitHub\breve-data\andersen-hc_breve-collin_6.pdf"
OUT_CSV = os.path.join(ROOT, "data", "curated", "collin_letters_place_index.csv")
OUT_REVIEW = os.path.join(ROOT, "data", "curated", "collin_letters_place_index_review.csv")

PAGE_LO, PAGE_HI = 69, 82   # 0-indexed PDF pages = printed pp. 64-77
PAGE_W = 450.85

# ── Layout extraction ────────────────────────────────────────────────────

def is_noise_block(b, page_h=565.2):
    """Page-number footers/headers and printer's signature marks (a tiny
    bottom-margin annotation used for collating printed sheets, seen on 2
    of the 14 pages, e.g. "VI,5") -- neither is index content."""
    x0, y0, x1, y1, _ = b[:5]
    w = x1 - x0
    if w < 30 and y0 < 60:
        return True
    if w < 30 and y1 > page_h - 45:
        return True
    return False


def extract_column_text():
    """Column-then-column reading order per page (left column top-to-bottom,
    then right column top-to-bottom), matching how a two-column alphabetical
    index is actually read -- verified against the real file by checking
    that a page's last right-column entry is alphabetically adjacent to the
    next page's first left-column entry (Baden-Baden -> Bamberg across the
    page 69/70 boundary)."""
    doc = fitz.open(PDF_PATH)
    if doc.page_count <= PAGE_HI:
        sys.exit(f"PDF only has {doc.page_count} pages, expected at least {PAGE_HI + 1}")

    chunks = []
    header_note = None
    for idx in range(PAGE_LO, PAGE_HI + 1):
        blocks = doc[idx].get_text("blocks")
        left, right = [], []
        for b in blocks:
            if is_noise_block(b):
                continue
            text = b[4]
            # Section title + caveat line, present once on the section's
            # opening page only. Captured separately as documentation, not
            # fed into the entry stream -- they are not index entries.
            if idx == PAGE_LO and re.match(r"^(III\.\s*STED-REGISTER|K.benhavn ikke medtaget)", text.strip()):
                if "medtaget" in text:
                    header_note = text.strip()
                continue
            (left if b[0] < PAGE_W / 2 else right).append((b[1], text))
        left.sort(); right.sort()
        chunks.append("".join(t for _, t in left) + "".join(t for _, t in right))
    doc.close()
    return "".join(chunks), header_note


# ── Entry splitting ──────────────────────────────────────────────────────

# A garbled "III" (Ill / HI / H1 / Il / IH) is the one Capital+lowercase-
# shaped token that is NOT a real place-name start; found by checking every
# raw line against the entry-start pattern and inspecting the one hit
# ("Ill, 8, 16, 19, 82..." -- a continuation of "Livorno").
GARBLED_III = re.compile(r"^(Ill|HI|H1|Il|IH)[,.\s]")
# Place names start with an uppercase letter followed by a lowercase one;
# roman numerals are all-caps and never match this. Covers every distinct
# entry-initial capital actually present in the source, including Ö
# (Östersund, Swedish) alongside Æ/Ø/Å (Danish).
ENTRY_START = re.compile(r"^[A-ZÆØÅÖ][a-zæøåüäöîéèêčñ]")


def split_entries(text):
    lines = [l for l in text.split("\n") if l.strip()]
    entries, current = [], None
    for ln in lines:
        if ENTRY_START.match(ln) and not GARBLED_III.match(ln):
            if current is not None:
                entries.append(current)
            current = [ln]
        else:
            current.append(ln)
    if current is not None:
        entries.append(current)
    return entries


# ── Field extraction ─────────────────────────────────────────────────────

NAME_RE = re.compile(r"^([A-ZÆØÅÖ][^,.(]*?)(?:,\s*se\s+(.+?)\.?\s*$|,|\.(?!\S)|\s+(?:I|II|III|IV|V|VI|VII)[,.]|\s*\()")
PAREN_RE = re.compile(r"\(([^)]*)\)")

# This index files a definite article at the END of a multi-word place name
# for alphabetization -- "Havre, Le" (Le Havre), "Brenets, Les" (Les
# Brenets), "Travers, Val de" (Val de Travers), "Mönch, Der" (Der Mönch) --
# the same inversion convention this project's OWN person register uses for
# "Efternavn, Fornavn". A naive first-comma split reads the article as the
# start of the citation instead. Small closed set: these are the only
# European definite articles/prefixes this particular index uses this way.
ARTICLE_TOKENS = re.compile(r"^(Le|Les|La|Der|Die|Das|Den|Det|Val de)\s*,")


def parse_entry(raw_lines):
    text = " ".join(l.strip() for l in raw_lines)
    text = re.sub(r"\s+", " ", text).strip()

    see_also = None
    m = re.match(r"^([A-ZÆØÅÖ][^,]*),\s*se\s+([^.]+)\.?\s*$", text)
    if m:
        return {
            "place_name_raw": m.group(1).strip(),
            "see_also": m.group(2).strip().rstrip("."),
            "parenthetical": None,
            "citation_raw": None,
            "full_text": text,
        }

    paren = None
    pm = PAREN_RE.search(text)
    if pm and text.index(pm.group(0)) < 40:
        paren = pm.group(1).strip()

    nm = NAME_RE.match(text)
    if nm:
        name = nm.group(1).strip()
        rest = text[nm.end(1):].lstrip()
    else:
        # Fallback: split on the first digit or roman-numeral-plus-comma.
        m2 = re.search(r"\s(?:I|II|III|IV|V|VI|VII),", text)
        name = text[:m2.start()].strip() if m2 else text
        rest = text[m2.start():].lstrip() if m2 else ""

    # Inverted-article check (see ARTICLE_TOKENS above): if what looks like
    # the citation actually starts "Le," / "Der," / etc., it is really the
    # second half of the name -- re-split one comma further along instead.
    # `rest` still carries NAME_RE's leading separator (a bare "," here,
    # since the "se" and "(" branches returned/were handled earlier), so
    # that has to come off before the article check can match at position 0.
    rest_stripped = re.sub(r"^,\s*", "", rest)
    am = ARTICLE_TOKENS.match(rest_stripped)
    if am:
        article = am.group(1)
        name = f"{name}, {article}"
        rest = rest_stripped[am.end():].lstrip()

    # Strip a leading parenthetical qualifier back out of the name for the
    # citation string, e.g. "Baden (ved Wien) II, 75..." -> name keeps the
    # qualifier (it's part of how the place is identified), citation starts
    # at the roman numeral.
    citation = re.sub(r"^,\s*", "", rest)

    return {
        "place_name_raw": name,
        "see_also": None,
        "parenthetical": paren,
        "citation_raw": citation or None,
        "full_text": text,
    }


# ── OCR quality heuristics ───────────────────────────────────────────────

# Tokens that show up ONLY as OCR noise inside what should be a clean
# volume+page citation list (roman numerals, digits, commas, periods,
# hyphens, spaces). Anything else surviving in the citation string is very
# likely a misread character, not real content -- EXCEPT a single "I" or
# "V", which are themselves legitimate volume markers in this citation
# grammar (I, II, III, IV, V, VI) and must not be misflagged as noise.
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


# ── High-confidence place-name corrections ───────────────────────────────
# Each entry below was checked two ways before being applied: (1) the
# surrounding citation volume/page pattern is consistent with a real,
# well-documented Andersen visit, and (2) the corrected spelling's
# alphabetical position matches where the entry actually sits in the
# printed sequence (a printed index cannot be out of its own order, so a
# corrected reading that now sorts correctly is strong independent
# evidence, not just a plausible guess). See collin-place-index.md for the
# case-by-case reasoning. Names NOT in this table are left exactly as
# extracted, even if they look suspicious -- see NEEDS_REVIEW below for
# those, flagged rather than silently guessed at.
KNOWN_CORRECTIONS = {
    "Milona": ("Milano", "n/o transposition; Andersen's repeated, heavily-cited Milan visits match the reference volume; alphabetical position unaffected (falls correctly between Middelfart and Minden either way)"),
    "Inin": ("Irun", "alphabetical-position proof: as printed 'Inin' would sort BEFORE 'Interlaken', but it is placed AFTER Interlaken and BEFORE Ischia in the source -- 'Irun' is the only plausible reading that sorts correctly in that exact slot (Int- < Iru- < Isc-)"),
}

# Flagged, not corrected: either the alphabetical position is unexplained
# by any reading I can justify (Giion/Glasgow, Mysunde/Moen), or the OCR
# confusion is real but I have no independent check strong enough to pick
# one specific corrected spelling (Giommen).
NEEDS_REVIEW = {
    "Giion": "sorts after 'Glasgow' in the source, which no plausible reading beginning 'Gi-' or 'Gl-' explains; likely Gijón (matches the surrounding Spain/Portugal citations) but unverified against the source page image",
    "Giommen": "adjacent Norwegian entries (Drammen, Kongsvinger, Sandviken) all cite the identical page 'IV, 188', suggesting this is another stop on the same 1871 Norway itinerary, but no specific corrected spelling could be confirmed",
    "Mysunde": "prints after 'Moen' despite sorting before it alphabetically; no OCR misreading found that resolves the inversion -- may be a genuine ordering slip in the source rather than an OCR error",
}


def main():
    print(f"Reading {PDF_PATH} …")
    text, header_note = extract_column_text()
    print(f"  {len(text):,} characters extracted, pages {PAGE_LO+1}-{PAGE_HI+1} "
          f"(printed pp. 64-77)")

    entries = split_entries(text)
    print(f"  {len(entries)} entries split")

    rows = []
    review_rows = []
    corrections_applied = 0
    for raw_lines in entries:
        parsed = parse_entry(raw_lines)
        name_raw = parsed["place_name_raw"]

        name_clean = name_raw
        correction_note = ""
        if name_raw in KNOWN_CORRECTIONS:
            name_clean, correction_note = KNOWN_CORRECTIONS[name_raw]
            corrections_applied += 1

        quality, noise_chars = citation_quality(parsed["citation_raw"])

        row = {
            "place_name_raw": name_raw,
            "place_name_clean": name_clean,
            "name_corrected": "yes" if name_clean != name_raw else "",
            "correction_note": correction_note,
            "parenthetical": parsed["parenthetical"] or "",
            "see_also": parsed["see_also"] or "",
            "citation_raw": parsed["citation_raw"] or "",
            "citation_ocr_quality": quality,
            "citation_ocr_noise_chars": noise_chars,
        }
        rows.append(row)

        if name_raw in NEEDS_REVIEW or quality == "high":
            review_rows.append({
                "place_name_raw": name_raw,
                "reason": NEEDS_REVIEW.get(name_raw, f"citation OCR quality: {quality} ({noise_chars})"),
                "citation_raw": parsed["citation_raw"] or "",
            })

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {os.path.relpath(OUT_CSV, ROOT)}  ({len(rows)} rows, "
          f"{corrections_applied} name corrections applied)")

    with open(OUT_REVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(review_rows[0].keys()) if review_rows else
                            ["place_name_raw", "reason", "citation_raw"])
        w.writeheader()
        w.writerows(review_rows)
    print(f"  wrote {os.path.relpath(OUT_REVIEW, ROOT)}  ({len(review_rows)} rows flagged for human review)")

    see_also_count = sum(1 for r in rows if r["see_also"])
    print(f"  {see_also_count} entries are 'se X' redirects")
    print("Done.")


if __name__ == "__main__":
    main()
