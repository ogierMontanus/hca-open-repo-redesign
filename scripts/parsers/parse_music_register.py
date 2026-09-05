#!/usr/bin/env python3
"""Parse the MUSIK slices of the canonical workbook into a structured
13-column TSV.

See docs/pipeline/stages.md (Stage 2) for context, and
docs/data-model/source-data-characteristics.md for the parenthetical
conventions encoded in the parsing logic below.

Default slice: RegistryCategory='VÆRK-REGISTER', WorkGenre='MUSIK', across
the three RegistryForm values in DEFAULT_FORMS below (Vokal- og
Instrumentalmusik, Operaer og Syngestykker/Skuespil med Musik, Balletter)
-- originally just the first of these; the other two were added once their
own creator column was checked for the same issues found in the ANDRE
FORFATTERE forms (see build_works_extra.py's
load_parsed_creator_overrides()). Pass one or more --form to parse only
specific forms instead (repeatable; overrides the default list entirely).

Usage:
    python parse_music_register.py [--xlsx PATH] [--output PATH] [--form FORM ...]
"""

import argparse
import csv
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import load_registry_slice, resolve_ground_truth_xlsx


# ── Patterns ─────────────────────────────────────────────────────────────────

FOLK_RE = re.compile(r"^(norsk|tysk|irsk|svensk|napolitansk|dansk|Folke)", re.I)
NOTE_RE = re.compile(r"^(Hvilken|Sang af|Hvad|Ukendt)", re.I)
OPUS_RE = re.compile(r"^op\.", re.I)
AF_RE = re.compile(r"^af[: ]", re.I)
GUILLEMET = re.compile(r"[»«](.+?)[«»]", re.S)
OPUS_EMBEDDED = re.compile(r",?\s*(op\.\s*\d+[a-z]?(?:\s+nr\.\s*\d+)?)\s*$", re.I)

# "- Se ogsaa: X" (WEMI cross-reference, e.g. an opera's Danish and
# original-language titles pointing at each other) trails 39 MUSIK rows --
# ported from parse_novels_plays_tales.py's own SE_OGSAA_RE, which this
# parser never had at all. Left unhandled, the target text and any of
# its OWN trailing parens get treated as more parens belonging to THIS
# entry -- e.g. Reg003328 "Troubaduren (G. Verdi)- Se ogsaa: Il trovatore
# (Divertissement)" was reading "(Divertissement)" (a dance-form note on
# the CROSS-REFERENCED entry) as this row's own composer. No downstream
# consumer reads a structured Se-ogsaa field for MUSIK yet (unlike
# novels_plays_tales.py), so the extracted text is folded into Note
# rather than a new column -- preserved, not lost, without building
# infrastructure nothing reads.
SE_OGSAA_RE = re.compile(r"\s*-\s*Se ogsaa:?\s*(.+?)\.?\s*$", re.IGNORECASE)

# Co-author splitting, same rule and same rationale as
# parse_novels_plays_tales.py's split_creators()/strip_role_label(): only
# " og " is reliably splittable (a bare comma list risks being one
# person's name-plus-title, not two people); a leading "Udg."/"Red." role
# label joined by "og" to a second role label ("Udg. og Red.: X") is one
# person with two roles, not two people, so it's stripped first.
_ROLE_LABEL_RE = re.compile(
    r"^(?:Udg\.|Red\.)(?:\s+og\s+(?:Udg\.|Red\.))?\s*:\s*", re.IGNORECASE,
)


def split_creators(creator: str) -> str:
    creator = _ROLE_LABEL_RE.sub("", creator, count=1)
    if " og " not in creator:
        return creator
    head, last = creator.rsplit(" og ", 1)
    parts = [p.strip() for p in head.split(",") if p.strip()] + [last.strip()]
    return "; ".join(parts)


# ── Adaptation-marker extraction ────────────────────────────────────────────
# Ported verbatim from parse_novels_plays_tales.py's extract_adaptation()
# (parsers don't import each other -- see split_creators()/_ROLE_LABEL_RE
# above for the same duplicate-with-attribution precedent). The sibling
# parser's own docstring originally scoped this out ("MUSIK's own creator
# field rarely carries the adaptation-credit shape... checked directly: 12
# of 407 creators contain ' og ', none of the messier compound ones"). A
# 2026-08-28 re-check of the current TSV found that no longer holds: 3
# real rows do carry it (Reg000570 "P. Larcher efter F. Taglioni",
# Reg002733, Reg000554 -- see docs/data-model/ note for the full trace),
# so the sibling machinery is ported in now that it's needed.
_ADAPT_MARKER_RE = re.compile(
    r",?\s*(?:frit\s+bearbejdet\s+af|bearbejdet\s+af|bearb\.\s*af|"
    r"frit\s+oversat\s+af|oversat\s+af|overs\.\s*af|ved|af)\s+",
    re.IGNORECASE,
)

# Same genitive-construction cleanup as parse_novels_plays_tales.py's own
# copy of this function -- kept in sync even though no current MUSIK row
# happens to trigger it, since both are meant to be the same ported logic.
_GENRE_NOUN_RE = re.compile(
    r"\s+(Roman|Digt|Digte|Fortælling|Fortællinger|Skuespil|Novelle)\b.*$",
    re.IGNORECASE,
)


def _clean_bare_name(x: str) -> str:
    trimmed = x.strip().rstrip(".,")
    stripped_quote = re.split(r"[:»]", trimmed)[0].strip().rstrip(".,")
    had_quote = stripped_quote != trimmed
    stripped_genre = _GENRE_NOUN_RE.sub("", stripped_quote).strip()
    had_genre = stripped_genre != stripped_quote
    result = stripped_genre
    if (had_quote or had_genre) and len(result) > 2 and result.endswith("s"):
        result = result[:-1]
    return result


def _looks_name_shaped(x: str) -> bool:
    if not x or any(ch.isdigit() for ch in x):
        return False
    if x[0].islower():
        return False
    if len(x.split()) > 8:
        return False
    return True


def extract_adaptation(creator: str) -> tuple[str, str | None]:
    """Returns (cleaned_creator, adapted_from_creator_or_None). See
    parse_novels_plays_tales.py's own copy of this function for the full
    WEMI rationale and rule-by-rule commentary -- unchanged here."""
    s = creator.strip()
    if not s:
        return s, None

    m = re.match(r"^efter\s+(.+)$", s, re.IGNORECASE)
    if m:
        rest = m.group(1)
        marker_matches = list(_ADAPT_MARKER_RE.finditer(rest))
        if marker_matches:
            mm = marker_matches[-1]
            source = _clean_bare_name(rest[: mm.start()].strip().rstrip(","))
            adapter = rest[mm.end() :].strip()
            if source and adapter:
                return adapter, source
        return _clean_bare_name(rest), None

    m = re.search(r",?\s+efter\s+", s, re.IGNORECASE)
    if m:
        adapter = s[: m.start()].strip()
        source = _clean_bare_name(s[m.end() :])
        if adapter and "," not in adapter and source:
            if adapter.lower().startswith("lokaliseret af "):
                adapter = adapter[len("lokaliseret af ") :].strip()
            return adapter, source

    m = re.search(
        r"^(.*?),\s*(?:frit\s+)?(?:bearbejdet\s+af|bearb\.\s*af|oversat\s+af|overs\.\s*af)\s+(.+)$",
        s, re.IGNORECASE,
    )
    if m:
        source, adapter = m.group(1).strip(), m.group(2).strip()
        if source and adapter:
            return adapter, source

    m = re.search(r"^(.*?),\s*bearbejdet\s+efter\s+(.+)$", s, re.IGNORECASE)
    if m:
        adapter, source = m.group(1).strip(), m.group(2).strip()
        if adapter and source:
            return adapter, source

    m = re.search(r"\s+ved\s+", s, re.IGNORECASE)
    if m:
        source = s[: m.start()].strip().rstrip(",")
        adapter = s[m.end() :].strip()
        if _looks_name_shaped(source) and _looks_name_shaped(adapter):
            return adapter, source

    return s, None


# Danish libretto convention: "Tekst af NAME" names the text-writer,
# distinct from (and usually following) a composer/genre preamble --
# "Operette med Musik af forskellige Komponister, Tekst af Erik Bøgh
# efter H. Chivot og A. Duru" (Reg002733). Confirmed a single-occurrence
# pattern across all 456 MUSIK rows (checked directly), not general
# enough to risk a looser match -- the literal marker text is required.
_TEKST_AF_RE = re.compile(r"^(.*?),?\s*Tekst\s+af\s+(.+)$", re.IGNORECASE | re.DOTALL)

# A creator candidate can bury its actual attributions behind explicit
# "Label: Name" role markers, with a long non-name preamble in front --
# "Studenterkomedie, Parodi paa italiensk Opera, Musik: C. J. Hansen,
# Tekst: Otto Zinck" (Reg002019) is a genre/plot description followed by
# TWO separate credits, not a single garbled name -- is_composer() lets
# it through (nothing in its exclusion list matches a long descriptive
# clause) and every rule above leaves it unchanged (no "efter"/
# "bearbejdet af"/etc. marker), so mechanically it would become 06_creator
# wholesale. Detected here instead: "Musik:" names the composer -- the
# ONLY thing that becomes 06_creator -- and every other labeled credit
# ("Tekst: Otto Zinck") plus the preamble move to Note.
_LABELED_ROLE_RE = re.compile(r"\b([A-ZÆØÅ][\wæøå.]*)\s*:\s*([^,;]+)")


def extract_labeled_roles(s: str) -> tuple[str, list[str]]:
    """Returns (new_creator_candidate, note_fragments) when s contains
    embedded 'Label: Name' role markers -- the name after 'Musik:' becomes
    the new candidate (empty string if no 'Musik:' marker is present, so
    no composer is asserted when none is actually named), with the
    preamble and every OTHER labeled credit in note_fragments. Returns
    (s, []) -- a no-op -- when no labeled marker is found at all."""
    matches = list(_LABELED_ROLE_RE.finditer(s))
    if not matches:
        return s, []
    composer = ""
    notes = []
    preamble = s[: matches[0].start()].strip().rstrip(",")
    if preamble:
        notes.append(preamble)
    for m in matches:
        label, val = m.group(1).strip(), m.group(2).strip().rstrip(".")
        if label.lower() == "musik" and not composer:
            composer = val
        else:
            notes.append(f"{label}: {val}")
    return composer, notes


# Rows where a single clause names 3+ unrelated role-credits with no
# clean single creator to extract (Reg000554: "Syngestykke, indrettet af
# N. T. Bruun, Musiken af Mozart, Méhul og Paër, Teksten efter
# Hauteroche" -- arranger, 3 composers, and a text-source all in one
# clause). person_derived is already correct here ("N. T. Bruun"); no
# override is emitted so build_works_extra.py's fallback to it wins
# instead of the naive split's fake "Syngestykke" author. WEMI rule 8,
# "ask, don't guess" -- add here only after confirming person_derived is
# right and no rule above recovers the row.
_KNOWN_UNSPLITTABLE = {"Reg000554"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def extract_parens(s):
    """Extract top-level parenthetical groups from string."""
    groups, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            if depth > 0:
                cur += ch
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                groups.append(cur.strip())
                cur = ""
            else:
                cur += ch
        elif depth > 0:
            cur += ch
    return groups


def is_composer(s):
    return not (
        OPUS_RE.match(s)
        or AF_RE.match(s)
        or FOLK_RE.match(s)
        or NOTE_RE.match(s)
        or s.startswith("»")
        or s.startswith("«")
        or s.startswith("=")
        # A premiere date+venue, common on Operaer/Balletter entries
        # ("18.1.1863, Tours", "9.10.1833, Firenze") -- {1,2} not a fixed
        # {2}, since the source often has a single-digit day or month
        # ("8.4.1843") that a strict two-digit pattern misses, letting the
        # date+venue fall through and get misread as the creator instead.
        or re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", s)
    )


def strip_guillemets(s):
    return re.sub(r"[»««»]", "", s).strip()


def extract_embedded_opus(s):
    """Remove trailing ', op. N' from a string. Returns (cleaned, opus)."""
    m = OPUS_EMBEDDED.search(s)
    return (s[: m.start()].strip(), m.group(1).strip()) if m else (s, "")


def assign_parens(r, parens):
    """Assign parenthetical groups to the correct fields.

    Guillemet rule: guillemet content in a parenthetical is treated as
    part_of (source reference), NOT as incipit — unless incipit is still
    empty AND the parens has no surrounding source text (e.g. 'Sang af').
    """
    remaining = []

    for p in parens:
        if OPUS_RE.match(p):
            r["opus"] = p

        elif AF_RE.match(p):
            r["part_of"] = p

        elif GUILLEMET.search(p):
            outer = GUILLEMET.sub("", p).strip(" -.,")

            if outer:
                r["part_of"] = (r["part_of"] + " | " if r["part_of"] else "") + p
            elif not r["incipit"]:
                r["incipit"] = strip_guillemets(GUILLEMET.search(p).group(1))
            else:
                r["part_of"] = (r["part_of"] + " | " if r["part_of"] else "") + p

        elif FOLK_RE.match(p):
            r["creator"] = p
            r["creator_is_human"] = "False"

        elif NOTE_RE.match(p):
            r["note"] = (r["note"] + " | " if r["note"] else "") + p

        elif p.startswith("="):
            r["note"] = (r["note"] + " | " if r["note"] else "") + f"({p})"

        else:
            remaining.append(p)

    if remaining and is_composer(remaining[-1]):
        raw = remaining.pop()
        if r["RegistryTitelID"] in _KNOWN_UNSPLITTABLE:
            r["note"] = (r["note"] + " | " if r["note"] else "") + f"({raw})"
        else:
            raw, label_notes = extract_labeled_roles(raw)
            for note_text in label_notes:
                r["note"] = (r["note"] + " | " if r["note"] else "") + note_text
            tm = _TEKST_AF_RE.match(raw)
            if tm:
                pre, raw = tm.group(1).strip().rstrip(","), tm.group(2).strip()
                if pre:
                    r["note"] = (r["note"] + " | " if r["note"] else "") + pre
            cleaned, adapted_from = extract_adaptation(raw)
            r["creator"] = split_creators(cleaned)
            r["adapted_from_creator"] = adapted_from or ""
            r["creator_is_human"] = "True"

    if remaining and not r["original_title"]:
        r["original_title"] = remaining.pop(0)

    for p in remaining:
        r["note"] = (r["note"] + " | " if r["note"] else "") + f"({p})"

    if r["original_title"] and not r["opus"]:
        cleaned, opus = extract_embedded_opus(r["original_title"])
        if opus:
            r["original_title"] = cleaned
            r["opus"] = opus


# ── Main parser ──────────────────────────────────────────────────────────────

def parse(raw, reg_id=""):
    r = dict(
        Posttype="",
        by_Andersen="False",
        genre="VocalAndInstrumentalMusic",
        main_title="",
        incipit="",
        original_title="",
        creator="",
        creator_is_human="",
        adapted_from_creator="",
        opus="",
        part_of="",
        kryds="",
        note="",
        RegistryTitelID=reg_id,
    )
    # A non-breaking space (U+00A0) in the source ("Fr.\xa0Schubert") reads
    # as a different string than its plain-space sibling, splitting one
    # composer across two facet entries downstream -- every sibling parser
    # under scripts/parsers/ already normalises this on its own raw label;
    # this one didn't.
    entry = raw.replace("\xa0", " ").strip().rstrip(".")

    m = re.match(r"^(.+),\s*\nse:\s*(.+)$", entry, re.DOTALL | re.I)
    if m:
        r["Posttype"] = "krydshenvisning"
        r["main_title"] = m.group(1).strip()
        r["kryds"] = m.group(2).strip().rstrip(".")
        return r

    r["Posttype"] = "standardpost"

    se_m = SE_OGSAA_RE.search(entry)
    if se_m:
        r["note"] = f"Se ogsaa: {se_m.group(1).strip()}"
        entry = entry[: se_m.start()].strip()

    sq = re.match(r"^\[([^\]]+)\](.*)", entry)
    if sq:
        r["main_title"] = f"[{sq.group(1)}]"
        assign_parens(r, extract_parens(sq.group(2).strip()))
        return r

    inc = re.match(r"^[»«](.+?)[«»](.*)", entry, re.S)
    if inc:
        r["incipit"] = inc.group(1).strip()
        assign_parens(r, extract_parens(inc.group(2).strip()))
        return r

    fp = entry.find("(")
    if fp == -1:
        r["main_title"] = entry.strip()
        return r

    r["main_title"] = entry[:fp].strip().rstrip(",").strip()
    assign_parens(r, extract_parens(entry[fp:]))
    return r


# ── I/O ──────────────────────────────────────────────────────────────────────

FIELDNAMES = [
    "01_Posttype",
    "02_by_Andersen",
    "03_genre",
    "04_main_title",
    "04b_incipit",
    "05_original_title",
    "06_creator",
    "06b_creator_is_human",
    "07_opus",
    "08_part_of",
    "09_Krydshenvisning_til",
    "10_Note",
    # Literal name, not the next sequential number -- build_works_extra.py's
    # load_parsed_creator_overrides() reads this exact column name from
    # every CREATOR_OVERRIDE_FILES entry (see
    # parse_novels_plays_tales.py's own 12_adapted_from_creator column),
    # so no downstream change is needed to pick this up here too.
    "12_adapted_from_creator",
    "RegistryTitelID",
]


# MUSIK forms this parser covers. Vokal- og Instrumentalmusik was the
# original, sole slice; the other two were added once their own output was
# checked for the same digit/year-in-creator defects the ANDRE FORFATTERE
# forms had (see docs/pipeline/stages.md and
# build_works_extra.py's load_parsed_creator_overrides()) -- both came back
# clean, so no parser-logic fix was needed here the way parse_novels_
# plays_tales.py's PREMIERE_DATE_RE/DESCRIPTOR_RE fix was.
DEFAULT_FORMS = (
    "Vokal- og Instrumentalmusik",
    "Operaer og Syngestykker, Skuespil med Musik",
    "Balletter",
)


def run(xlsx: pathlib.Path, dst: pathlib.Path, *, forms: list[str] = None) -> pathlib.Path:
    forms = forms if forms else list(DEFAULT_FORMS)
    results: list[dict] = []
    per_form_counts: list[tuple[str, int, int]] = []  # (form, standardpost, with_creator)

    for form in forms:
        slice_rows = load_registry_slice(
            xlsx,
            category="VÆRK-REGISTER",
            genre="MUSIK",
            form=form,
        )
        form_results = [parse(title, reg_id) for title, reg_id in slice_rows]
        results.extend(form_results)
        std = [r for r in form_results if r["Posttype"] == "standardpost"]
        with_creator = sum(1 for r in std if r["creator"] and r["creator_is_human"] != "False")
        per_form_counts.append((form, len(std), with_creator))

    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=FIELDNAMES, delimiter="\t", extrasaction="ignore"
        )
        w.writeheader()
        for r in results:
            w.writerow(
                {
                    "01_Posttype": r["Posttype"],
                    "02_by_Andersen": r["by_Andersen"],
                    "03_genre": r["genre"],
                    "04_main_title": r["main_title"],
                    "04b_incipit": r["incipit"],
                    "05_original_title": r["original_title"],
                    "06_creator": r["creator"],
                    "06b_creator_is_human": r["creator_is_human"],
                    "07_opus": r["opus"],
                    "08_part_of": r["part_of"],
                    "09_Krydshenvisning_til": r["kryds"],
                    "10_Note": r["note"],
                    "12_adapted_from_creator": r["adapted_from_creator"],
                    "RegistryTitelID": r["RegistryTitelID"],
                }
            )

    pt = Counter(r["Posttype"] for r in results)
    n_adapted = sum(1 for r in results if r["adapted_from_creator"])
    print(f"Source: {xlsx.name}  (genre: MUSIK)")
    print(f"   To:  {dst}")
    for form, std_n, creator_n in per_form_counts:
        pct = f"{creator_n / std_n:.0%}" if std_n else "n/a"
        print(f"   {form:<50s} {std_n:5d} rows, {creator_n:5d} with a human creator ({pct})")
    print(f" Rows:  {len(results)}  |  {dict(pt)}  |  {n_adapted} with an adapted_from source")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--xlsx",
        type=pathlib.Path,
        default=None,
        help="Path to ground-truth workbook (default: highest version in raw/)",
    )
    ap.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("data/parsed/music_register_parsed.tsv"),
        help="Output TSV path (default: data/parsed/music_register_parsed.tsv)",
    )
    ap.add_argument(
        "--form",
        action="append",
        default=None,
        help="RegistryForm to include; repeatable. Defaults to all three "
             "forms in DEFAULT_FORMS above when omitted.",
    )
    args = ap.parse_args()
    xlsx = args.xlsx or resolve_ground_truth_xlsx()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    forms = args.form if args.form else list(DEFAULT_FORMS)
    run(xlsx, args.output, forms=forms)


if __name__ == "__main__":
    main()
