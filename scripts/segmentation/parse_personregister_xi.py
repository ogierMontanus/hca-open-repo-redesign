#!/usr/bin/env python3
"""
parse_personregister_xi.py
---------------------------
Digitizes the printed PERSONREGISTER (person-name index, columns 1-796)
from H. C. Andersens Dagbøger XI (ed. H. Topsøe-Jensen, DSL 1977).
Genealogy fold-out pages (Collin, Drewsen, Stampe, Wulff/Koch, Henriques,
Melchior family trees, PDF pages roughly 26-42 of the source file used
here) and all front matter are out of scope -- both OCR layers fail
badly and inconsistently on those pages (see
docs/data-model/ocr-comparison-dagboeger-XI.md), and they are not
alphabetical person entries.

Source: two OCR layers of the same scan compared in
raw/ocr-comparison-dagboeger-XI.md. That comparison found the "test
ABBYY" layer measurably more reliable for register digits (e.g. it does
not confuse leading "1" with "7" the way the other layer does on a full
column of page 117/118), so it is the sole source for this parse step;
the older layer is not merged in here -- see the module docstring of
merge_personregister_ocr.py (not yet written) for how a second layer
would be reconciled if ever needed.

Page range (0-indexed PDF pages in the "test ABBYY" file, 445 pages):
  page 46 = "PERSONREGISTER" section title + usage note
  page 47 = first entry (Åberg)
  page 444 = last entry (Ørsted, Pauline), no colophon after

Column layout per page (measured): page 440.65 x 570.5pt, left column
x in [59,218], right column x in [226,384], header (repeated first/last
entry as a running head) at y<=52, footer (this register's OWN printed
column numbers) at y>=486. Both header and footer are page-navigation
aids for someone flipping the physical book, not entry content, and are
dropped -- see docs/data-model/personregister-synthesis-plan.md sec 3.2
for why counting/recording them was deliberately dropped from scope.

Entry splitting: line-start heuristics do NOT work here (verified) --
capitalized place/institution names embedded mid-description ("...i
Justitsministeriet, 1855 Lektor og...") false-trigger a naive
"Capitalized-word + comma starts a new entry" rule on hundreds of lines.
Instead: reflow each page's columns into one continuous string per
column, then find split points forward -- a split point is the END of
something that closes an entry (a volume+column citation like "IV
141 148.", a parenthetical "(...).", an uncertain-year "?.", or a "se:
X." cross-reference clause) immediately followed by something that
opens a new entry (a "Surname, Given names" head, or -- for the
minority of entries with no surname comma at all, e.g. single-name
historical figures like "Absalon (ca. 1128-1201)" -- a bare capitalized
name directly followed by "(year" or a roman-numeral citation).

What this catches that a dated-only heuristic (as used in
scripts/correspondence/extract_collin_person_index.py for the sibling
Brevveksling person-register) would miss: entries with NO year at all
(e.g. "Amiot, Bordeaux 23.8.1866. VII 175.") are common in this register
and are captured here, because the anchor is punctuation-based, not
year-based.

Output: data/parsed/personregister_xi_parsed.tsv, one row per entry
(including cross-references and sub-entries -- see 02_entry_type).
References are preserved as printed (10_references_raw) AND expanded to
atomic volume:column pairs (11_references_parsed), because the raw
range notation ("398-99" = 398-399, "106-07" = 106-107) is a real
compression -- an abbreviated final digit of the FIRST number, not a
generic "high-low" range -- and needs unambiguous expansion, not a
naive number-to-number range fill, to be queryable per volume+column.

Run from the repo root:
  python scripts/segmentation/parse_personregister_xi.py
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
PDF_PATH = os.path.join(ROOT, "data", "raw", "dagbog-bd-11-3408_Claus-OCR test ABBYY.pdf")
OUT_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
OUT_REVIEW = os.path.join(ROOT, "data", "review", "personregister_xi_review.tsv")

PAGE_LO, PAGE_HI = 47, 444  # 0-indexed PDF pages, "test ABBYY" file
PAGE_W = 440.65

VOLUMES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")

# ── 1. Layout extraction ─────────────────────────────────────────────────


def flow_page(page):
    """Left column top-to-bottom, then right column top-to-bottom;
    header/footer blocks (running head, printed column numbers) excluded
    by y-bounds measured directly against this file (see module
    docstring). Soft hyphens (word-wrap artifacts) are removed before
    line breaks are collapsed to spaces, so a wrapped word rejoins
    cleanly (e.g. "Med\xad\nindehaver" -> "Medindehaver")."""
    blocks = [b for b in page.get_text("blocks") if 55 < b[1] and b[3] < 483]
    left = sorted((b[1], b[4]) for b in blocks if b[0] < PAGE_W / 2)
    right = sorted((b[1], b[4]) for b in blocks if b[0] >= PAGE_W / 2)
    text = "".join(t for _, t in left) + "".join(t for _, t in right)
    text = text.replace("\xad\n", "").replace("\xad", "")
    text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_flowed_text():
    doc = fitz.open(PDF_PATH)
    if doc.page_count <= PAGE_HI:
        sys.exit(f"PDF only has {doc.page_count} pages, expected at least {PAGE_HI + 1}")
    text = " ".join(flow_page(doc[i]) for i in range(PAGE_LO, PAGE_HI + 1))
    doc.close()
    return text


# ── 2. Entry splitting ───────────────────────────────────────────────────

# A "Surname, Given names" head. Particle surnames (auf der Maur, von
# Arnim, van Assen) are alphabetized on the particle in this register,
# so they are included as valid head-starters, not just capitals.
NAME_HEAD_COMMA = (
    r"(?:[A-ZÆØÅÖÜ][\w\x27\-]*|auf|von|van|de|d\x27|le|la)"
    r"(?:[ \-][A-Za-zÆØÅæøåöäüéè\x27\-\.]+)*?,\s"
)
# The minority of entries with no surname comma at all -- single-name
# historical/biblical/royal figures, e.g. "Absalon (ca. 1128-1201)",
# "Aischylos (525-456 f. Chr.)". Anchored on a bare capitalized word
# directly followed by a year-parenthesis or a volume-citation comma, so
# it does not fire on an ordinary given name inside a normal entry
# (those are preceded by "Surname, ", not by entry-closing punctuation).
# Also covers an entry opening "Name [editorial note]" or "Name Epithet
# (year)" -- a name followed by a square bracket, or by a second
# capitalised word and then a year-parenthesis, with no comma anywhere
# ("Lennel [saaledes H. Hertz' Dagbøger], fransk Rejsende…", "Sigurd
# Jorsalfarer (1089/90-1130)"). Without these, such an entry was
# absorbed into the preceding "se:" cross-reference instead of starting
# its own.
#
# Deliberately NOT covered: "Name (Alias)" with a capitalised word in
# parentheses. That shape is overwhelmingly a mid-entry alias
# ("Bajazet (Bajazid) I", "Barfoed (Barfod), Peter Marius") rather than
# an entry opening, and allowing it split 25 entries mid-name.
# The third alternative covers a name joined by a lowercase particle
# before its year-parenthesis -- "Bernhard af Clairvaux (1090-1153)",
# "Giotto di Bondone", "Lope de Vega", "Rembrandt van Rijn". These have
# no comma at all, so without this they were absorbed into the
# preceding entry (12 entries affected).
NAME_HEAD_NOCOMMA = (
    r"(?:[A-ZÆØÅÖÜ][a-zæøåöäü]+)"
    r"(?:\s(?=[IVX]+,|\[|\((?:ca\.\s*)?d?\.?\s*\d{3,4})"
    r"|\s[A-ZÆØÅÖÜ][a-zæøåöäü]+\s(?=\((?:ca\.\s*)?\d{3,4})"
    r"|\s(?:af|von|van|de|der|di|le|la)\s[A-ZÆØÅÖÜ][a-zæøåöäü]+\s(?=\((?:ca\.\s*)?d?\.?\s*\d{3,4})"
    # "Agrippina d.Æ. (død 33)" -- a generational suffix (den Ældre /
    # den Yngre) between the name and its year-parenthesis. The year
    # here may be introduced by a spelled-out "død", not just the
    # abbreviated "d.", and may be as short as 2 digits (year 33).
    r"|\s+d\.\s?[ÆY]\.?\s*(?=\((?:ca\.\s*)?(?:d\.|død)?\s*\d{2,4}))"
)
NAME_HEAD = r"(?:" + NAME_HEAD_COMMA + r"|" + NAME_HEAD_NOCOMMA + r")"

# An entry-closing citation: one or more volume markers each followed by
# column numbers/ranges, ending in a period. Requires a real roman
# volume marker (not just any digit+period) so that a mid-description
# ordinal like "2. Bataillonslæge" never triggers a false split.
CITE_END = r"(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\s[\d\s\-\.]*?[0-9]\.\s"
# A "se:" / "se ogsaa:" cross-reference clause ending in a period (these
# entries carry no volume citation, so CITE_END alone would merge them
# into the next entry). \b is required before "se" -- without it this
# matched the letters "se" inside an ordinary word (e.g. "Jose-phine"),
# causing entries to be cut mid-description.
#
# The colon is optional and "ogsaa" is fuzzy-matched: the source prints
# "se ogsaa Rennenkampff." with no colon at all, and one entry's OCR
# mangles the word itself ("se ogasa: Repsdorph"). Requiring a literal
# "se[ ogsaa]:" merged those entries into the following one. To stay
# safe without the colon anchor, the clause must be followed by a
# capitalised word (a real cross-reference target), which an ordinary
# mid-sentence "se" is not.
# The clause ends at the first period followed by whitespace. A period
# INSIDE the target -- an abbreviated given name ("se: A.N.de
# Saint-Aubain.") -- is followed by a non-space and so does not end the
# clause; a plain [^.]{1,80} run stopped at that first inner dot, found
# no clause end, and merged the cross-reference with the entry after it.
SEE_END = r"\bse(?:\s+og[as]{2}a)?:?\s+(?=[A-ZÆØÅÖÜ])(?:[^.]|\.(?=\S)){1,80}\.\s"

# A dash-prefixed sub-entry with its own citation, no "se:" clause
# (e.g. "— Hendes Søster og dennes Børn. VIII 108."). These continue
# the previous entry's surname (see SUBENTRY_RE / is_subentry in
# parse_entry) rather than opening a new one.
DASH_SUBENTRY_HEAD = r"[–—]\s(?:Hans|Hendes|Deres)\s"

SPLIT_RE = re.compile(
    r"(?:" + CITE_END + r"|" + SEE_END + r"|\)\.\s|\?\.\s)"
    r"(?=" + NAME_HEAD + r"|" + DASH_SUBENTRY_HEAD + r")"
)

# A lone alphabet-section divider ("A.", "Å.") printed on its own
# between entries, immediately before the entry that opens that letter.
# Only stripped when it is the very first thing in an already-split
# segment (never mid-text -- a person's own initial like "F. L. B."
# would otherwise be indistinguishable from this and get eaten).
LEADING_SECTION_DIVIDER_RE = re.compile(r"^[A-ZÆØÅ]\.\s+")


def split_entries(text):
    splits = [0]
    for m in SPLIT_RE.finditer(text):
        splits.append(m.end())
    splits.append(len(text))
    splits = sorted(set(splits))
    segments = [text[splits[i]:splits[i + 1]].strip() for i in range(len(splits) - 1)]
    return [LEADING_SECTION_DIVIDER_RE.sub("", s).strip() for s in segments if s.strip()]


# Section markers ("A.", "Å.") sit alone between entries as alphabet
# dividers -- not entries, not sub-entries of anything.
SECTION_MARKER_RE = re.compile(r"^[A-ZÆØÅ]\.$")


# ── 3. Field parsing ─────────────────────────────────────────────────────

# The name part can itself contain commas (a descriptive clause before
# the redirect, e.g. "Albert, Prinsgemal, se: Sachsen-Coburg-Gotha,
# Albert."), so this matches greedily up to the LAST "se:"/"se ogsaa:"
# clause in the entry, not the first comma.
# "ogsaa" is fuzzy-matched (og[as]{2}a) for the same reason as in
# SEE_END: one entry's OCR renders it "ogasa". Without that, the
# misspelt word was left in the extracted see_also target
# ("ogasa: Repsdorph" instead of "Repsdorph").
SEE_RE = re.compile(r"^(?P<name>.+),\s*se(?:\s+og[as]{2}a)?:?\s+(?P<target>.+?)\.?\s*$", re.IGNORECASE)
SUBENTRY_RE = re.compile(r"^[–—\-]\s*")  # leading en/em-dash or hyphen: continuation under previous surname
# Surname ends at the first comma, OR -- for the no-comma-surname
# entries matched by NAME_HEAD_NOCOMMA (single-name historical figures,
# e.g. "Aischylos (525-456 f. Chr.), græsk...") -- at the year
# parenthesis directly following it, whichever comes first. Without the
# alternative, "Aischylos (525-456 f. Chr.)" (the comma AFTER the
# closing paren) was read as the whole surname.
NAME_COMMA_RE = re.compile(
    r"^(?P<surname>[^,(]+?)"
    r"(?:,\s*(?P<rest>.*)$|\s*(?=\((?:ca\.\s*)?(?:d\.|død)?\s*\d{2,4})(?P<rest2>.*)$)"
)
# The year-parenthesis does not always sit directly after the surname
# comma -- given names/titles/lengthy noble styling can come first
# ("Ahlefeldt, Charlotte Elisabeth Sophie Wilhelmine von, Grevinde, f.
# von Seebach (1781-1849), ..."), so this searches near the start of
# `rest` rather than anchoring at position 0. Capped at 260 chars of
# lead-in -- measured against every entry in the register, the longest
# genuine lead-in is ~250 chars; a citation's own parenthetical range
# elsewhere in the entry must never be mistaken for the birth/death
# year, so this is not uncapped. The death year is often printed
# abbreviated to its final 2 digits ("1818-80" = 1818-1880), the same
# convention used for column-range citations -- so death is 2-4 digits,
# expanded via the same abbreviation rule as references (see
# expand_range), not treated as a literal small number.
YEAR_RE = re.compile(
    r"^(?P<lead>.{0,260}?)\(\s*(?:(?:d\.|død)\s*(?P<death_only>\d{2,4})"
    r"|(?:ca\.\s*)?(?P<birth>\d{3,4})\s*[–—\-]\s*(?P<death>\d{2,4}|\?)"
    r"|(?P<birth_only>\d{3,4}))\s*(?P<fchr>f\.\s*Chr\.)?\)\s*,?\s*"
)

# Reference block: everything from the first volume-roman-numeral marker
# to the end of the entry text is citations, not description.
REF_BLOCK_RE = re.compile(
    r"(?P<refs>(?:\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\b[\d\s,\-]+\.?\s*)+)$"
)

# One volume marker followed by its column numbers/ranges (consumes up
# to, but not including, the next volume marker).
VOL_CHUNK_RE = re.compile(
    r"\b(?P<vol>I|II|III|IV|V|VI|VII|VIII|IX|X)\b\s*(?P<nums>[\d\s,\-]+)"
)
# The hyphen in a range can carry a stray space on EITHER side in the
# extracted text ("283- 85" or "401 -02" for printed "283-85"/"401-02")
# -- an artifact of the source's own line-wrap (the hyphen or the
# number after it falls at a line break), not a second, separate
# citation. Confirmed against page images (Auerbach, Berthold, PDF
# p.58: "283-85" is one range; Collin, Gottlieb, PDF p.118 confirms a
# DIFFERENT nearby defect is a genuine source OCR error, not this one).
NUM_OR_RANGE_RE = re.compile(r"(?P<a>\d+)(?:\s?-\s?(?P<b>\d+))?")


def expand_range(a_str, b_str):
    """'398-99' means 398-399 (b_str is an abbreviated final digit run
    of a_str, the register's own printing convention), not a literal
    398-to-99 range. If b_str is the same length as a_str (e.g.
    '106-107'), it is already a full number."""
    if b_str is None:
        return [a_str]
    if len(b_str) >= len(a_str):
        b = b_str
    else:
        b = a_str[: len(a_str) - len(b_str)] + b_str
    a, b = int(a_str), int(b)
    if b < a:  # abbreviation produced a smaller number than expected; keep as printed pair, don't guess
        return [a_str, b_str]
    return [str(n) for n in range(a, b + 1)]


def parse_references(ref_text):
    """Returns (raw, parsed_list) where parsed_list is ['IV:52', 'IV:135', ...]."""
    pairs = []
    for vm in VOL_CHUNK_RE.finditer(ref_text):
        vol = vm.group("vol")
        for nm in NUM_OR_RANGE_RE.finditer(vm.group("nums")):
            for col in expand_range(nm.group("a"), nm.group("b")):
                pairs.append(f"{vol}:{col}")
    return ref_text.strip(), pairs


# The given-names field is the free-text remainder between the surname
# comma and the year-parenthesis (if any) -- captured directly off
# `rest` before YEAR_RE consumes it, not re-derived from description.
def parse_entry(raw_text):
    text = raw_text.strip()
    is_subentry = bool(SUBENTRY_RE.match(text))
    if is_subentry:
        text = SUBENTRY_RE.sub("", text)

    if SECTION_MARKER_RE.match(text):
        return None

    has_citation = bool(REF_BLOCK_RE.search(text.rstrip(".")))

    # Dash sub-entries without their own "se:" clause have no name/comma
    # at all ("Hans Broder fra Amerika. V 157.") -- the whole thing is
    # description + trailing citation, inherited surname aside.
    if is_subentry and not SEE_RE.match(text):
        ref_m = REF_BLOCK_RE.search(text)
        if ref_m:
            description = text[: ref_m.start()].strip().rstrip(",")
            refs_raw, refs_parsed = parse_references(ref_m.group("refs"))
        else:
            description = text.rstrip(".").strip()
            refs_raw, refs_parsed = "", []
        return {
            "entry_type": "underpost",
            "surname": "",  # filled in by caller from the previous entry's surname
            "given_names": "",
            "birth_year": "",
            "death_year": "",
            "year_note": "",
            "description": description,
            "references_raw": refs_raw,
            "references_parsed": ";".join(refs_parsed),
            "see_also": "",
        }, is_subentry

    see_m = SEE_RE.match(text)
    if see_m and not has_citation:
        surname_part = see_m.group("name").strip()
        nm = NAME_COMMA_RE.match(surname_part + ",")
        surname = nm.group("surname").strip() if nm else surname_part
        nm_rest = (nm.group("rest") or nm.group("rest2") or "").strip() if nm else ""
        given = nm_rest.rstrip(",") if nm_rest else ""
        return {
            "entry_type": "underpost" if is_subentry else "krydshenvisning",
            "surname": surname,
            "given_names": given,
            "birth_year": "",
            "death_year": "",
            "year_note": "",
            "description": "",
            "references_raw": "",
            "references_parsed": "",
            "see_also": see_m.group("target").strip(),
        }, is_subentry

    nm = NAME_COMMA_RE.match(text)
    surname = nm.group("surname").strip() if nm else text.rstrip(".")
    rest = ((nm.group("rest") or nm.group("rest2") or "").strip()) if nm else ""

    ym = YEAR_RE.match(rest)
    given = ym.group("lead").strip().rstrip(",") if ym else ""
    birth = death = note = ""
    if ym:
        if ym.group("fchr"):
            note = "f. Kr. (BC)"
        if ym.group("death_only"):
            death = ym.group("death_only")
        elif ym.group("birth_only"):
            birth = ym.group("birth_only")
            note = (note + "; " if note else "") + "enkeltårstal, usikkert om fødsel/død"
        else:
            birth = ym.group("birth") or ""
            death = ym.group("death") or ""
            if death == "?":
                note = (note + "; " if note else "") + "dødsår usikkert (?)"
                death = ""
            elif death and len(death) < len(birth):
                death = birth[: len(birth) - len(death)] + death
        rest = rest[ym.end():].strip()
    else:
        # No year at all -- still split given-names-like lead-in isn't
        # reliable without the year anchor, so the whole remainder is
        # description (matches entries like "Amiot, Bordeaux 23.8.1866.").
        given = ""
        rest = rest

    ref_m = REF_BLOCK_RE.search(rest)
    if ref_m:
        description = rest[: ref_m.start()].strip().rstrip(",")
        refs_raw, refs_parsed = parse_references(ref_m.group("refs"))
    else:
        description = rest.rstrip(".").strip()
        refs_raw, refs_parsed = "", []

    see_also = ""
    see_inline = re.match(r"^se(?:\s+ogsaa)?:?\s+(.+)$", description, re.IGNORECASE)
    if see_inline:
        see_also = see_inline.group(1).strip().rstrip(".")
        description = ""

    entry_type = "underpost" if is_subentry else ("krydshenvisning" if see_also and not refs_parsed else "standardpost")

    return {
        "entry_type": entry_type,
        "surname": surname,
        "given_names": given,
        "birth_year": birth,
        "death_year": death,
        "year_note": note,
        "description": description,
        "references_raw": refs_raw,
        "references_parsed": ";".join(refs_parsed),
        "see_also": see_also,
    }, is_subentry


SORT_STRIP_RE = re.compile(r"^(auf der |von |van |de |d\x27|le |la )", re.IGNORECASE)


def sort_key(surname, given_names):
    # Register's own convention: particle surnames alphabetize on the
    # particle itself ("auf der Maur" under A), so the particle is kept,
    # not stripped -- this key exists only to make that explicit and
    # stable for downstream consumers, not to "normalize" it away.
    base = f"{surname}, {given_names}".strip().rstrip(",")
    return base


def main():
    print(f"Reading {PDF_PATH} ...")
    text = extract_flowed_text()
    print(f"  {len(text):,} characters extracted, PDF pages {PAGE_LO}-{PAGE_HI}")

    raw_entries = split_entries(text)
    print(f"  {len(raw_entries)} raw segments split")

    rows = []
    last_surname = None
    skipped_markers = 0
    n = 1
    for raw in raw_entries:
        if SECTION_MARKER_RE.match(raw):
            skipped_markers += 1
            continue
        parsed, is_sub = parse_entry(raw)
        if parsed is None:
            skipped_markers += 1
            continue
        if is_sub and last_surname:
            parsed["surname"] = last_surname
        if parsed["entry_type"] != "underpost":
            last_surname = parsed["surname"]

        row = {
            "01_entry_id": f"PerXI{n:05d}",
            "02_entry_type": parsed["entry_type"],
            "03_surname": parsed["surname"],
            "04_given_names": parsed["given_names"],
            "05_sort_key": sort_key(parsed["surname"], parsed["given_names"]),
            "06_birth_year": parsed["birth_year"],
            "07_death_year": parsed["death_year"],
            "08_year_note": parsed["year_note"],
            "09_description": parsed["description"],
            "10_references_raw": parsed["references_raw"],
            "11_references_parsed": parsed["references_parsed"],
            "12_see_also": parsed["see_also"],
            "13_raw_text": raw,
        }
        rows.append(row)
        n += 1

    print(f"  {skipped_markers} alphabet-section markers skipped")
    print(f"  {len(rows)} entries parsed")

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {os.path.relpath(OUT_TSV, ROOT)}")

    # Review flags: entries with neither references nor a see-also
    # target (nothing to cross-check); see-also targets that don't
    # resolve to any surname actually present in the register; and
    # column numbers outside the register's own printed range (1-796,
    # per its colophon) -- a hard implausibility check that catches
    # source OCR errors (a dropped space fusing two numbers, e.g. "V
    # 2456" for "V 245 6") independent of whether the number otherwise
    # looks like a clean digit run.
    MAX_COLUMN = 796
    surnames_seen = {r["03_surname"] for r in rows}
    review_rows = []
    for r in rows:
        reasons = []
        if not r["11_references_parsed"] and not r["12_see_also"]:
            reasons.append("ingen henvisninger og intet 'se:'-mål")
        if r["12_see_also"]:
            target_surname = r["12_see_also"].split(",")[0].strip()
            if target_surname and target_surname not in surnames_seen:
                reasons.append(f"'se:'-mål '{target_surname}' findes ikke som opslag")
        bad_cols = sorted({
            pair for pair in r["11_references_parsed"].split(";") if pair
            for _, col in [pair.split(":")]
            if not (1 <= int(col) <= MAX_COLUMN)
        })
        if bad_cols:
            reasons.append(f"spaltetal uden for 1-{MAX_COLUMN}: {', '.join(bad_cols)}")
        # A death year lower than the birth year is impossible outside
        # BC entries -- usually a 0/9 OCR confusion in this source layer
        # (see raw/ocr-comparison-dagboeger-XI.md), e.g. "1823-1007"
        # printed as "1823-1907" in the book (verified against the page
        # image for this exact case).
        b, d = r["06_birth_year"], r["07_death_year"]
        if (
            b and d and b.isdigit() and d.isdigit() and int(d) < int(b)
            and "f. Kr." not in r["08_year_note"]
        ):
            reasons.append(f"dødsår {d} før fødselsår {b} (sandsynlig 0/9-OCR-fejl eller trykfejl i kilden)")
        # The register prints each volume's columns in increasing order;
        # a drop within one volume is almost always a source OCR defect
        # (a dropped space/hyphen fusing or splitting numbers wrongly),
        # e.g. "V 2456" for what should be several distinct numbers.
        by_vol = {}
        for pair in r["11_references_parsed"].split(";"):
            if not pair:
                continue
            vol, col = pair.split(":")
            by_vol.setdefault(vol, []).append(int(col))
        dropping_vols = sorted(
            vol for vol, cols in by_vol.items()
            if any(cols[i] < cols[i - 1] for i in range(1, len(cols)))
        )
        if dropping_vols:
            reasons.append(f"faldende spaltetalrække i bind {', '.join(dropping_vols)}")
        if reasons:
            review_rows.append({**r, "14_review_reason": "; ".join(reasons)})

    with open(OUT_REVIEW, "w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0].keys()) + ["14_review_reason"]
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(review_rows)
    print(f"  wrote {os.path.relpath(OUT_REVIEW, ROOT)}  ({len(review_rows)} rows flagged)")


if __name__ == "__main__":
    main()
