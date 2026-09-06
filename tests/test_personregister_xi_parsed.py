#!/usr/bin/env python3
"""Sanity checks on data/parsed/personregister_xi_parsed.tsv, the digitized
PERSONREGISTER (person index) from H. C. Andersens Dagbøger XI.

These are regression guards for scripts/parsers/parse_personregister_xi.py,
not a re-verification of OCR accuracy (see data/raw/ocr-comparison-dagboeger-XI.md
for that). They catch the two classes of bug found during development:
mis-split entries (a citation or "se:" clause fused into the wrong entry)
and mis-parsed fields (surname swallowing a parenthetical, year missed
because a title/description lead-in was too long).

Run from the repo root:
  python -m pytest tests/test_personregister_xi_parsed.py -v
"""
import csv
import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
TSV_PATH = REPO / "data" / "parsed" / "personregister_xi_parsed.tsv"

MAX_COLUMN = 796  # register's own printed column range, per its colophon
VOLUMES = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}


@pytest.fixture(scope="module")
def rows():
    if not TSV_PATH.exists():
        pytest.skip(f"{TSV_PATH} not generated -- run parse_personregister_xi.py first")
    with open(TSV_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def test_row_count_in_expected_range(rows):
    # Not a fixed count -- the source PDF could be re-OCR'd -- but a
    # sudden large drop/spike signals the splitter broke, not a benign
    # change. Originally measured at 9306; the ceiling was raised to
    # 10400 after ~300 entries that the column-reflow splitter had
    # fused were split apart, each confirmed against an independent
    # source (xlsx DimPer, and the pre-segmented
    # "Personer _ HCA_tsv.txt", which lists 10228 person rows -- so the
    # true entry count is expected to approach that figure, not 9306).
    # Upper bound raised again after importing the 958 people the
    # reference transcription lists and this parse lacked. Our count now
    # legitimately EXCEEDS the reference's 10228, because we additionally
    # carry ~390 "se:" cross-reference rows as entries of their own,
    # which the reference does not.
    assert 9000 <= len(rows) <= 10800, (
        f"entry count {len(rows)} is outside the expected range; expected roughly "
        "10200 people plus ~390 cross-reference rows -- far below means fused "
        "entries, far above means a splitter regression"
    )


def test_entry_ids_unique_and_sequential(rows):
    ids = [r["01_entry_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate 01_entry_id values"
    expected = [f"PerXI{i:05d}" for i in range(1, len(rows) + 1)]
    assert ids == expected, "01_entry_id values are not sequential PerXI00001.."


def test_no_blank_surname(rows):
    blanks = [r["01_entry_id"] for r in rows if not r["03_surname"].strip()]
    assert not blanks, f"entries with empty 03_surname: {blanks[:10]}"


def test_surname_never_contains_a_year_parenthesis(rows):
    # Regression guard for the "Aischylos (525-456 f. Chr.)" bug: a
    # single-name entry's surname must not swallow its own year
    # parenthetical (NAME_COMMA_RE's no-comma branch).
    bad = [r["01_entry_id"] for r in rows if re.search(r"\(\s*\d", r["03_surname"])]
    assert not bad, f"surname field contains a year parenthesis: {bad[:10]}"


def test_entry_type_is_known_value(rows):
    allowed = {"standardpost", "krydshenvisning", "underpost"}
    bad = {r["02_entry_type"] for r in rows} - allowed
    assert not bad, f"unexpected 02_entry_type values: {bad}"


def test_underpost_inherits_a_surname(rows):
    # Sub-entries (dash-prefixed continuations, e.g. "— Hendes Søster
    # ...") must have been assigned the preceding entry's surname, not
    # left blank.
    bad = [r["01_entry_id"] for r in rows if r["02_entry_type"] == "underpost" and not r["03_surname"].strip()]
    assert not bad, f"underpost rows with no inherited surname: {bad[:10]}"


def test_references_parsed_matches_volume_column_shape(rows):
    pair_re = re.compile(r"^[IVX]+:\d+$")
    bad = []
    for r in rows:
        for pair in r["11_references_parsed"].split(";"):
            if not pair:
                continue
            if not pair_re.match(pair):
                bad.append((r["01_entry_id"], pair))
    assert not bad, f"malformed references_parsed pairs: {bad[:10]}"


def test_references_parsed_volumes_are_known(rows):
    bad = []
    for r in rows:
        for pair in r["11_references_parsed"].split(";"):
            if not pair:
                continue
            vol = pair.split(":")[0]
            if vol not in VOLUMES:
                bad.append((r["01_entry_id"], pair))
    assert not bad, f"references_parsed cite an unknown volume marker: {bad[:10]}"


def test_references_parsed_columns_within_printed_range(rows):
    # A hard implausibility check, not proof of correctness: a column
    # number outside the register's own printed range (1-796) is
    # necessarily wrong, usually a source OCR error (a dropped space
    # fusing two numbers). These rows should also appear in
    # data/curated/personregister_xi_review.tsv, not be silently
    # dropped -- this test only guards that they are not treated as
    # ordinary, unflagged data days after being introduced.
    out_of_range = []
    for r in rows:
        for pair in r["11_references_parsed"].split(";"):
            if not pair:
                continue
            col = int(pair.split(":")[1])
            if not (1 <= col <= MAX_COLUMN):
                out_of_range.append((r["03_surname"], pair))
    # Known, accepted source-OCR defects (see personregister_xi_review.tsv);
    # update this set only after checking a new failure against the raw
    # PDF, not to silence a real regression. Keyed by surname, not
    # entry id: ids renumber whenever the splitter's entry count
    # changes, which would silently turn this allow-list into a
    # different (wrong) set of rows.
    known = {"Florio", "Henriques", "Koch"}
    unexpected = [(surname, pair) for surname, pair in out_of_range if surname not in known]
    assert not unexpected, f"new out-of-range column references (not in known list): {unexpected[:10]}"


def test_see_also_targets_are_extracted_at_all(rows):
    # A coverage guard, not a resolution one: whether each "se:" target
    # actually lands on an entry is checked properly in
    # tests/test_index_integrity.py, which knows the register's own citation
    # conventions (surname-only heads, inverted particles, alias
    # parentheticals, the documented OCR confusion classes) and grades the
    # failures. This test only asserts that SEE_RE is still finding
    # cross-references at all — the one thing that file cannot tell apart
    # from a register that genuinely has none.
    #
    # It replaces an earlier "at least 75% of targets resolve to a known
    # surname" assertion. That threshold was doing more harm than good: bare
    # string equality against the surname column scored a quarter of
    # perfectly good references as failures, so the bar had to sit low
    # enough that a real regression could hide underneath it.
    targets = [r["12_see_also"] for r in rows if r["12_see_also"].strip()]
    assert len(targets) >= 350, (
        f"only {len(targets)} 'se:' cross-references found (expected ~400) -- "
        "SEE_RE or the splitter has stopped recognising them"
    )
    stubs = [r for r in rows if r["02_entry_type"] == "krydshenvisning"]
    missing = [r["01_entry_id"] for r in stubs if not r["12_see_also"].strip()]
    # PerXI01219 is an ordinary entry mis-typed as a cross-reference; it is
    # tracked with the other integrity findings rather than silenced here.
    assert len(missing) <= 1, (
        f"cross-reference rows with no target at all: {missing[:10]}"
    )


def test_birth_year_before_or_equal_death_year(rows):
    # BC-dated entries (year_note "f. Kr. (BC)") correctly count DOWN
    # from birth to death (e.g. Aischylos 525-456 f.Kr.) and are excluded.
    # A handful of entries are genuinely printed with death < birth in
    # the 1977 typesetting itself (a swapped digit, e.g. "(1796-1780)")
    # -- confirmed against the raw text, not a parser bug, so listed
    # here rather than "fixed" by guessing the true year. Plesner,
    # Laura is different: checked against the page image
    # (PDF p.328/printed col. 561-62), the BOOK correctly prints
    # "1823-1907" -- this OCR layer misread "9" as "0" (the same 0/9
    # confusion class documented in data/raw/ocr-comparison-dagboeger-XI.md),
    # so "1007" is a source-OCR defect, not a source typesetting one;
    # kept in this list because fixing one hand-verified digit here
    # would not generalize, and the row is already surfaced in
    # data/curated/personregister_xi_review.tsv for that reason.
    # Sofokles (496-406) is BC but the source omits "f. Chr." on this
    # one entry (unlike the neighboring Aischylos entry, which has it),
    # so year_note misses it too -- same known-defect bucket regardless.
    # Keyed by surname, not entry id: ids renumber whenever the
    # splitter's entry count changes, which would silently turn this
    # allow-list into a different (wrong) set of rows.
    known_source_defects = {"Berner", "Høegh-Guldberg", "Liunge", "Plesner", "Sofokles"}
    bad = []
    for r in rows:
        if "f. Kr." in r["08_year_note"] or r["03_surname"] in known_source_defects:
            continue
        b, d = r["06_birth_year"], r["07_death_year"]
        if b and d and b.isdigit() and d.isdigit() and int(d) < int(b):
            bad.append((r["03_surname"], b, d))
    assert not bad, f"death year before birth year (not in known list): {bad[:10]}"


def test_column_sequence_mostly_increasing_within_volume(rows):
    # The register prints each volume's column citations in increasing
    # order (e.g. "IV 52 135 197 217 228-29 277 281 283-85"), so a drop
    # within one volume's run is a strong signal of a source OCR defect
    # (a dropped hyphen or digit fusing/splitting numbers wrongly) --
    # this caught two real parser bugs during development (a range
    # hyphen followed OR preceded by a stray space, e.g. "283- 85" and
    # "401 -02", was being read as two separate numbers instead of one
    # range) before settling near a small, stable residual of genuine
    # source defects (e.g. "V 2456" printed for what should be several
    # space-separated numbers). A hard zero-tolerance assert would be
    # too brittle against future re-OCRs; a ceiling catches a parser
    # regression while tolerating known source noise.
    violations = 0
    for r in rows:
        pairs = [p for p in r["11_references_parsed"].split(";") if p]
        by_vol = {}
        for p in pairs:
            vol, col = p.split(":")
            by_vol.setdefault(vol, []).append(int(col))
        for cols in by_vol.values():
            if any(cols[i] < cols[i - 1] for i in range(1, len(cols))):
                violations += 1
                break
    assert violations <= 25, (
        f"{violations} entries have a decreasing column sequence within a volume "
        "(baseline: 19 known source-OCR defects) -- check for a new range-parsing regression"
    )


def test_no_leading_section_divider_in_raw_text(rows):
    # Regression guard for the "A. Åberg" bug: a lone alphabet-section
    # marker must never survive as part of an entry's own text.
    #
    # An entry whose given names START with initials is not this bug --
    # "Nørgaard, E. A. (død 1891)" is filed under N and legitimately
    # begins "E. A.". Only a single initial followed by a real word (the
    # divider letter plus the surname it introduced) counts.
    bad = [
        r["01_entry_id"] for r in rows
        if re.match(r"^[A-ZÆØÅ]\.\s+[A-ZÆØÅÖÜ][a-zæøåöäü]", r["13_raw_text"])
    ]
    assert not bad, f"entries still carry a leading section-divider: {bad[:10]}"
