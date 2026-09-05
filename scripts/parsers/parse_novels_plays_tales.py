#!/usr/bin/env python3
"""Parse the ANDRE FORFATTERE prose/drama/poetry slices of the canonical
workbook into a structured 12-column TSV.

See docs/pipeline/stages.md (Stage 2) for context, and
docs/data-model/source-data-characteristics.md / wemi-and-relations.md for
the parenthetical conventions and Se-ogsaa semantics encoded below.

Default slice: RegistryCategory='VÆRK-REGISTER', WorkGenre='ANDRE
FORFATTERE', across the five RegistryForm values in DEFAULT_FORMS below
(Romaner/Noveller/Eventyr, Skuespil, Digte, Tidsskrifter/Periodica, Samlede
og blandede Skrifter) — originally just the first of these; the other four
were validated and added later (see DEFAULT_FORMS' own comment for each
one's creator-recovery rate). Pass one or more --form to parse only
specific forms instead (repeatable; overrides the default list entirely,
not additive).

Column schema
-------------
01_Posttype          : standardpost | krydshenvisning | inferred_container
02_by_Andersen       : False throughout (all other-author works)
03_genre             : NovelsPlaysTales
04_main_title        : Primary title
05_original_title    : Alternative / original-language title (plain 2nd paren)
06_creator           : Author
07_part_of           : Container work (from af: / guillemet pattern)
08_Se_ogsaa          : WEMI relation (- Se ogsaa:)
09_Krydshenvisning_til: Cross-reference target
10_cited_directly    : True = Andersen cited this directly; False = inferred container
11_Note              : Year, descriptor, source, or other note
RegistryTitelID      : From source workbook

Inferred containers
-------------------
Whenever part_of is populated, a second row is emitted immediately after the
source row with Posttype=inferred_container and cited_directly=False.
These represent the container works that Andersen did NOT cite directly — he
cited a subsection, not the whole.

Usage:
    python parse_novels_plays_tales.py [--xlsx PATH] [--output PATH]
                                       [--form FORM] [--genre GENRE]
"""

import argparse
import csv
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import load_registry_slice, resolve_ground_truth_xlsx


COLUMNS = [
    "01_Posttype", "02_by_Andersen", "03_genre",
    "04_main_title", "05_original_title", "06_creator",
    "07_part_of", "08_Se_ogsaa", "09_Krydshenvisning_til",
    "10_cited_directly", "11_Note", "12_adapted_from_creator",
    "RegistryTitelID",
]
GENRE = "NovelsPlaysTales"

# ── Patterns ─────────────────────────────────────────────────────────────────

KRYDS_RE = re.compile(r"^(.+?),\s*se:\s*(.+)$", re.IGNORECASE | re.DOTALL)

SE_OGSAA_RE = re.compile(r"\s*-\s*Se ogsaa:\s*(.+?)\.?\s*$", re.IGNORECASE)

# af: / af »Title« inside a parenthesis → part_of
AF_PAREN_RE = re.compile(
    r"\([^)]*?\baf(?::\s*|\s+(?=»))(?:»([^«]+)«[^)]*|([^)]*?))\)",
    re.IGNORECASE,
)

PAREN_RE = re.compile(r"\(([^)]+)\)")

# Pseudonym markers: "PenName Ͻ: RealName" (ported from parse_non_fiction
# .py's own PSEUDONYM_RE -- same duplicate-with-attribution pattern as
# extract_adaptation()) and the equivalent prose form "PenName, Pseudonym
# for RealName". Checked directly: 8 of the 10 "Ͻ:" occurrences in this
# genre's forms sit inside a round-paren creator candidate (the other 2
# are inside square brackets -- a title-translation gloss and a two-person
# "og"-joined case respectively -- and never reach `creator` at all, so
# they're unaffected here). Real name, not pen name, becomes 06_creator --
# the pen name is preserved in 11_Note instead, matching the WEMI "real
# creator, not the name on the byline" framing used throughout this file.
PSEUDONYM_RE = re.compile(r"^(.+?)[,\s]+Ͻ:\s*(.+)$")
PSEUDONYM_FOR_RE = re.compile(r"^(.+?),?\s*Pseudonym\s+for\s+(.+)$", re.IGNORECASE)


def split_pseudonym(creator: str) -> tuple[str, str]:
    """Returns (pseudonym_or_empty, real_name). real_name is `creator`
    unchanged when no marker is present."""
    m = PSEUDONYM_RE.match(creator)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = PSEUDONYM_FOR_RE.match(creator)
    if m:
        # Strip an incidental leading "Oversat af " left over from a
        # translator marker this parser doesn't otherwise extract here
        # ("Oversat af Talvj, Pseudonym for ..." -- Reg003469) -- cosmetic
        # only, the real name (what matters for 06_creator) is unaffected
        # either way.
        pseudonym = re.sub(r"^oversat\s+af\s+", "", m.group(1).strip(), flags=re.IGNORECASE)
        return pseudonym, m.group(2).strip()
    return "", creator

# Single-word generic terms and bare years → Note rather than original_title
# (or, when this is the LAST parenthetical -- see parse_row -- rather than
# creator). "Tekst" appears on hymn/song Digte entries formatted "Title
# (Creator) (Tekst)" -- a genre/medium tag trailing the real creator paren,
# not a second name.
DESCRIPTOR_RE = re.compile(
    r"^(\d{4}|Skolebog|Anonym|Folkebogen|Anonymus|Uddrag|Tekst)$",
    re.IGNORECASE,
)

# A handful of Skuespil (play) entries carry a premiere date instead of a
# creator in their one parenthetical -- "(19.1.1834, Teatro Fiano, Rom)",
# "(16.1. og 25.1.1841, Teatro Fiano, Rom)" -- the same convention
# build_works_extra.py's place_from_teater_title() already recognises for
# TEATER & MUSIK. No real creator name starts with a bare "D." or "DD."
# day-of-month token, so this is a safe, precise signal that the LAST
# parenthetical is premiere info, not an author.
PREMIERE_DATE_RE = re.compile(r"^\d{1,2}\.")

# ── Adaptation-marker extraction ────────────────────────────────────────────
# A creator string is often two people conflated: the person who made THIS
# register entry's Work, and the original the entry is credited as "efter"
# (after)/"bearbejdet af" (adapted by)/"ved" (via) -- see
# docs/data-model/wemi-and-relations.md's WEMI rule ("new creator -> new
# Work"): the adapter is this row's real creator, the other name belongs in
# a separate field, not folded into 06_creator. Column shape and role
# assignment were worked out against every one of this parser's 55
# efter/bearbejdet/ved/oversat rows by hand (2026-08-28 probe) before being
# encoded here; each rule below is deliberately narrow -- a shape it
# doesn't recognise is left completely unchanged rather than guessed at,
# same "ask, don't guess" discipline as DESCRIPTOR_RE/PREMIERE_DATE_RE
# above.
_ADAPT_MARKER_RE = re.compile(
    r",?\s*(?:frit\s+bearbejdet\s+af|bearbejdet\s+af|bearb\.\s*af|"
    r"frit\s+oversat\s+af|oversat\s+af|overs\.\s*af|ved|af)\s+",
    re.IGNORECASE,
)

# A trailing genre-noun after a source name -- "V. Hugos Roman [Bug
# Jargal]" (Reg001190/Reg002169) -- is the same genitive construction as
# a guillemet-quoted title ("Hugo's novel" vs. "Hugo's «Title»"); both
# get stripped by _clean_bare_name() below, along with anything after
# the genre-noun (a sub-title, as in "Roman Bug Jargal").
_GENRE_NOUN_RE = re.compile(
    r"\s+(Roman|Digt|Digte|Fortælling|Fortællinger|Skuespil|Novelle)\b.*$",
    re.IGNORECASE,
)


def _clean_bare_name(x: str) -> str:
    """Strip a trailing colon/guillemet-quoted title reference ("W.
    Scott: »Guy Mannering«" -> "W. Scott") or trailing genre-noun ("V.
    Hugos Roman" -> "V. Hugo") from a source name. Both are genitive
    constructions in Danish ("Hugo's novel" / "Hugo's «Title»") -- the
    resulting trailing 's' is stripped too, but only when one of these
    two markers actually fired; an ordinary s-ending surname (Thomas,
    Andrews) reaching this function with neither marker present is left
    untouched, same as before this fix."""
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
    """Returns (cleaned_creator, adapted_from_creator_or_None). See the
    module comment above _ADAPT_MARKER_RE for the WEMI rationale."""
    s = creator.strip()
    if not s:
        return s, None

    # "efter X [af/ved/bearbejdet af/oversat af Y]" -- X is the source; if
    # a Y is also present it's the adapter (this row's real creator) and
    # wins the LAST such marker in X (so "efter det Spanske af Kong Ludwig
    # I af Bayern, oversat af J. Both" correctly splits on ", oversat af",
    # not the "af" embedded in the King's own title). With no second
    # marker, X itself becomes the creator -- matches how entities.csv's
    # own person_derived already treats a bare "Efter M. S. Schwartz" (its
    # value there is just "M. S. Schwartz").
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

    # "X efter Y" (comma before "efter" optional) -- X is the adapter, Y
    # the source. Rejected when X itself contains a comma: a real name
    # doesn't, but a descriptive clause sometimes does ("Benjamin
    # Feddersen, Intrigen efter ...") and that must not become creator
    # "Benjamin Feddersen, Intrigen" -- left unchanged instead.
    m = re.search(r",?\s+efter\s+", s, re.IGNORECASE)
    if m:
        adapter = s[: m.start()].strip()
        source = _clean_bare_name(s[m.end() :])
        if adapter and "," not in adapter and source:
            if adapter.lower().startswith("lokaliseret af "):
                adapter = adapter[len("lokaliseret af ") :].strip()
            return adapter, source

    # "X, bearbejdet af / frit bearbejdet af / bearb. af / oversat af /
    # overs. af Y" -- opposite role from "efter": X (before the comma) is
    # the source, Y the adapter. "overs. af" (Reg001035 "Ed. Brisebarre,
    # overs. af Wilh. Friedrich") is the same "oversat af" marker,
    # abbreviated -- this rule previously only recognised the unabbreviated
    # form.
    m = re.search(
        r"^(.*?),\s*(?:frit\s+)?(?:bearbejdet\s+af|bearb\.\s*af|oversat\s+af|overs\.\s*af)\s+(.+)$",
        s, re.IGNORECASE,
    )
    if m:
        source, adapter = m.group(1).strip(), m.group(2).strip()
        if source and adapter:
            return adapter, source

    # "X, bearbejdet efter Y" -- same role as the leading-"efter" rule
    # above (X is the adapter), just introduced by a comma instead.
    m = re.search(r"^(.*?),\s*bearbejdet\s+efter\s+(.+)$", s, re.IGNORECASE)
    if m:
        adapter, source = m.group(1).strip(), m.group(2).strip()
        if adapter and source:
            return adapter, source

    # Standalone " ved " ("X, by way of/via Y") -- both sides must look
    # name-shaped (no digits, capitalised, not absurdly long), since "ved"
    # is also an ordinary Danish preposition ("sunget ved hans
    # Bisættelse" = "sung AT his funeral", not an adapter credit at all).
    m = re.search(r"\s+ved\s+", s, re.IGNORECASE)
    if m:
        source = s[: m.start()].strip().rstrip(",")
        adapter = s[m.end() :].strip()
        if _looks_name_shaped(source) and _looks_name_shaped(adapter):
            return adapter, source

    return s, None


# A periodical entry's role label ("Udg." = Udgiver/publisher, "Red." =
# Redaktør/editor) sometimes precedes the actual name(s), joined by " og "
# when both roles are held by the same masthead line -- "Udg. og Red.:
# Niels Lindberg" is ONE person with two roles, not two people named "Udg."
# and "Red.". Left in place, split_creators() below would wrongly split on
# that "og" and produce a bare "Udg." as a fake co-author. Strip it before
# splitting; a role label followed by several REAL names ("Udg.: Bj.
# Bjørnsen, Rasmus Nielsen og Rudolph Schmidt") is unaffected since there's
# no "og" between the role and the first name there.
_ROLE_LABEL_RE = re.compile(
    r"^(?:Udg\.|Red\.)(?:\s+og\s+(?:Udg\.|Red\.))?\s*:\s*", re.IGNORECASE,
)


def strip_role_label(creator: str) -> str:
    return _ROLE_LABEL_RE.sub("", creator, count=1)


# Two rows whose creator clause is too compound for any rule above to
# safely untangle -- hand-verified (RegistryTitelID, creator,
# adapted_from), not guessed at, per WEMI rule 8:
#
# Reg000831 "Der ewige Jude (Nach dem Roman des Eugen Sue für die
# deutsche Bühne bearbeitet von Carlschmidt)" -- German phrasing this
# parser has no marker rules for at all ("Nach dem Roman des X ...
# bearbeitet von Y"); the two proper nouns are Eugen Sue (the novel's
# author) and Carlschmidt (who adapted it for the German stage).
#
# Reg002457 "Naar Djævelen banker paa! (Benjamin Feddersen, Intrigen
# efter Dupeutys, Dumersans og Gabriels »Victorine ou la nuit porte
# conseil«)" -- Rule 2 above deliberately rejects an adapter-side comma
# ("Benjamin Feddersen, Intrigen") to avoid exactly this kind of
# descriptive clause becoming part of a name, so nothing recovers it
# automatically. Real names: Benjamin Feddersen (this row's actual
# creator) adapting Dupeuty, Dumersan and Gabriel's French play (each
# genitive-marked in the source -- "Dupeutys", "Dumersans", "Gabriels" --
# and the quoted title dropped, same as _clean_bare_name() does
# elsewhere).
_KNOWN_ADAPTATION_OVERRIDES = {
    "Reg000831": ("Carlschmidt", "Eugen Sue"),
    "Reg002457": ("Benjamin Feddersen", "Dupeuty, Dumersan og Gabriel"),
}


# ── Co-author splitting ─────────────────────────────────────────────────────
# Applied to whatever extract_adaptation() leaves as the creator. Only
# " og " is treated as reliably splittable -- a bare comma list with no
# " og " anywhere ("Ángel de Saavedra, Hertug af Rivas") is at least as
# likely to be one person's name-plus-title as it is two people, so it's
# left as a single value rather than guessed at (2026-08-28 probe:
# checked directly, that exact name is not two people).
def split_creators(creator: str) -> list[str]:
    creator = strip_role_label(creator)
    if " og " not in creator:
        return [creator]
    head, last = creator.rsplit(" og ", 1)
    return [p.strip() for p in head.split(",") if p.strip()] + [last.strip()]


KNOWN_TITLES: set[str] = set()


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_row(
    posttype: str,
    main_title: str,
    *,
    original_title: str = "",
    creator: str = "",
    part_of: str = "",
    se_ogsaa: str = "",
    kryds_til: str = "",
    cited_directly: str = "True",
    note: str = "",
    adapted_from_creator: str = "",
    reg_id: str = "",
) -> dict:
    return {
        "01_Posttype": posttype,
        "02_by_Andersen": "False",
        "03_genre": GENRE,
        "04_main_title": main_title,
        "05_original_title": original_title,
        "06_creator": creator,
        "07_part_of": part_of,
        "08_Se_ogsaa": se_ogsaa,
        "09_Krydshenvisning_til": kryds_til,
        "10_cited_directly": cited_directly,
        "11_Note": note,
        "12_adapted_from_creator": adapted_from_creator,
        "RegistryTitelID": reg_id,
    }


def classify_plain_paren(content: str) -> str:
    if DESCRIPTOR_RE.match(content.strip()):
        return "note"
    if content.strip() in KNOWN_TITLES:
        return "part_of"
    return "original_title"


def strip_parens(label: str, matches: list) -> str:
    result = label
    for m in sorted(matches, key=lambda x: x.start(), reverse=True):
        result = result[: m.start()] + result[m.end() :]
    return re.sub(r"\s+", " ", result).strip().rstrip("., ")


# ── Parser ───────────────────────────────────────────────────────────────────

def parse_row(raw_label: str, reg_id: str) -> list[dict]:
    label = raw_label.replace("\xa0", " ").strip()
    out: list[dict] = []

    km = KRYDS_RE.match(label)
    if km:
        out.append(make_row(
            "krydshenvisning",
            km.group(1).strip(),
            kryds_til=km.group(2).strip().rstrip("."),
            reg_id=reg_id,
        ))
        return out

    se_ogsaa = ""
    sm = SE_OGSAA_RE.search(label)
    if sm:
        se_ogsaa = sm.group(1).strip()
        label = label[: sm.start()].strip()

    part_of = ""
    af_m = AF_PAREN_RE.search(label)
    if af_m:
        part_of = (af_m.group(1) or af_m.group(2) or "").strip()
        label = (label[: af_m.start()] + label[af_m.end() :]).strip()

    remaining = list(PAREN_RE.finditer(label))

    original_title = ""
    creator = ""
    note_parts: list[str] = []

    if remaining:
        last_content = remaining[-1].group(1).strip()
        # The last parenthetical is usually the creator, but not when it's
        # a genre/medium tag ("Tekst") or a premiere date -- those go to
        # Note instead, and the real creator (if any) is the group before
        # it. A single such parenthetical with nothing earlier means no
        # creator is recoverable here at all -- leave it blank rather than
        # asserting a date or "Tekst" as an author.
        if DESCRIPTOR_RE.match(last_content) or PREMIERE_DATE_RE.match(last_content):
            note_parts.append(last_content)
            if len(remaining) > 1:
                creator = remaining[-2].group(1).strip()
                earlier = remaining[:-2]
            else:
                earlier = []
        else:
            creator = last_content
            earlier = remaining[:-1]

        for p in earlier:
            content = p.group(1).strip()
            role = classify_plain_paren(content)
            if role == "part_of" and not part_of:
                part_of = content
            elif role == "original_title" and not original_title:
                original_title = content
            else:
                note_parts.append(content)

    # Separate an adaptation credit's source from this row's real creator
    # (see extract_adaptation's own comment), then split whatever's left
    # into individual co-authors on " og " (see split_creators). Applied
    # here, once, after `creator` is fully settled above -- not per-branch
    # -- so it runs identically regardless of which path set `creator`.
    adapted_from_creator = ""
    if creator and reg_id in _KNOWN_ADAPTATION_OVERRIDES:
        creator, adapted_from_creator = _KNOWN_ADAPTATION_OVERRIDES[reg_id]
    elif creator:
        # strip_role_label() runs here too, not just inside split_creators()
        # below -- a role-label prefix ("Red.: Georg og Edvard Brandes")
        # has the exact same surface shape as a source citation ("Geijer
        # og Afzelius: Svenska folkvisor Nr. 26") and MUST be told apart
        # from one before the colon-citation check below runs, or "Red.:"
        # gets mistaken for a citation-name prefix and the real names
        # after it get discarded into Note instead. Calling it again
        # inside split_creators() afterwards is a harmless no-op once
        # it's already been stripped here.
        creator = strip_role_label(creator)
        pseudonym, creator = split_pseudonym(creator)
        if pseudonym:
            note_parts.append(f"Pseudonym: {pseudonym}")
        # A colon in what's left is usually a source citation glued onto
        # the front, not part of a name -- "Geijer og Afzelius: Svenska
        # folkvisor Nr. 26" (an anthology + item number), "Abrahamson,
        # Nyerup og Rahbek: Udvalgte danske Viser fra Middelalderen Nr.
        # CLV". No real name in this corpus contains a colon -- the one
        # marker that legitimately does ("Ͻ:") has already been consumed
        # by split_pseudonym() above -- so splitting on the first
        # remaining colon and keeping only the part before it is safe.
        # The full original string is kept in Note rather than discarded.
        if ":" in creator:
            pre = creator.split(":", 1)[0].strip().rstrip(",")
            if pre:
                note_parts.append(creator)
                creator = pre
        creator, adapted_from = extract_adaptation(creator)
        if adapted_from:
            adapted_from_creator = adapted_from
        creator = "; ".join(split_creators(creator))

    main_title = strip_parens(label, remaining)
    note = "; ".join(note_parts)

    out.append(make_row(
        "standardpost",
        main_title,
        original_title=original_title,
        creator=creator,
        part_of=part_of,
        se_ogsaa=se_ogsaa,
        cited_directly="True",
        note=note,
        adapted_from_creator=adapted_from_creator,
        reg_id=reg_id,
    ))

    if part_of:
        out.append(make_row(
            "inferred_container",
            part_of,
            creator=creator,
            cited_directly="False",
        ))

    return out


# ── Main ─────────────────────────────────────────────────────────────────────

# ANDRE FORFATTERE forms this parser is validated against. Originally just
# Romaner, Noveller, Eventyr; the other four were checked one at a time
# (each run against the live workbook, standardpost/creator counts compared
# by hand) before being added here — see docs/pipeline/stages.md and the
# coverage-planning note in build_works_extra.py's
# load_parsed_creator_overrides(). Recovery rate varies by form (periodicals
# are often compiled, not single-authored, hence Periodica's lower rate) but
# every one of the four beat "no creator at all", which is the only
# alternative entries.csv's own person_derived offers for most of them.
#   Form                                                  creator recovery
#   Romaner, Noveller, Eventyr (the original slice)        229 works
#   Skuespil                                                728 rows, 99.6%
#   Digte                                                   244 rows, 97%
#   Tidsskrifter og aarbøger, ugeblade,
#     vittighedsblade (Periodica)                            82 rows, 55%
#   Samlede og blandede Skrifter                             19 rows, 89%
DEFAULT_FORMS = (
    "Romaner, Noveller, Eventyr",
    "Skuespil",
    "Digte",
    "Tidsskrifter og aarbøger, ugeblade, vittighedsblade (Periodica)",
    "Samlede og blandede Skrifter",
)


def run(
    xlsx: pathlib.Path,
    dst: pathlib.Path,
    *,
    genre: str,
    forms: list[str],
) -> pathlib.Path:
    output: list[dict] = []
    per_form_counts: list[tuple[str, int, int]] = []  # (form, rows, with_creator)

    for form in forms:
        slice_rows = load_registry_slice(
            xlsx,
            category="VÆRK-REGISTER",
            genre=genre,
            form=form,
        )

        # KNOWN_TITLES is scoped per form, matching how a single-form run
        # always worked -- a bare parenthetical is classified as part_of
        # only against titles from the SAME form's own slice, not across
        # every form processed in this call.
        KNOWN_TITLES.clear()
        for title, _ in slice_rows:
            bare = PAREN_RE.sub("", title).strip().rstrip("., ")
            KNOWN_TITLES.add(bare)

        form_rows: list[dict] = []
        for title, reg_id in slice_rows:
            form_rows.extend(parse_row(title, reg_id))
        output.extend(form_rows)

        std = [r for r in form_rows if r["01_Posttype"] == "standardpost"]
        with_creator = sum(1 for r in std if r["06_creator"])
        per_form_counts.append((form, len(std), with_creator))

    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        for r in output:
            w.writerow(r)

    n_std = sum(1 for r in output if r["01_Posttype"] == "standardpost")
    n_kryd = sum(1 for r in output if r["01_Posttype"] == "krydshenvisning")
    n_inf = sum(1 for r in output if r["01_Posttype"] == "inferred_container")
    n_pof = sum(1 for r in output if r["07_part_of"])
    n_orig = sum(1 for r in output if r["05_original_title"])
    n_creator = sum(1 for r in output if r["01_Posttype"] == "standardpost" and r["06_creator"])

    print(f"Source : {xlsx.name}  (genre: {genre})")
    print(f"Written: {dst}")
    for form, std_n, creator_n in per_form_counts:
        pct = f"{creator_n / std_n:.0%}" if std_n else "n/a"
        print(f"  {form:<66s} {std_n:5d} rows, {creator_n:5d} with creator ({pct})")
    print(f"Rows   : {len(output)}")
    print(f"  standardpost      : {n_std}  ({n_creator} with a creator)")
    print(f"  krydshenvisning   : {n_kryd}")
    print(f"  inferred_container: {n_inf}  (cited_directly=False)")
    print(f"  with part_of      : {n_pof}")
    print(f"  with original_title: {n_orig}")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", type=pathlib.Path, default=None)
    ap.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("data/parsed/novels_plays_tales_parsed.tsv"),
    )
    ap.add_argument("--genre", default="ANDRE FORFATTERE")
    ap.add_argument(
        "--form",
        action="append",
        default=None,
        help="RegistryForm to include; repeatable. Defaults to all five "
             "forms in DEFAULT_FORMS above when omitted.",
    )
    args = ap.parse_args()
    xlsx = args.xlsx or resolve_ground_truth_xlsx()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    forms = args.form if args.form else list(DEFAULT_FORMS)
    run(xlsx, args.output, genre=args.genre, forms=forms)


if __name__ == "__main__":
    main()
