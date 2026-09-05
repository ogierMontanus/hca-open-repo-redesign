#!/usr/bin/env python3
"""
refine_description_segmentation.py
--------------------------------------
Moves name and year data that is still sitting inside 09_description
into the fields that own it, for rows the main parser left unsplit.

Three patterns, all found by inspecting rows that carry NO year data:

  A  09_description starts with the entry's own life-span parenthesis,
     because the name has no comma and the parser's no-comma branch did
     not fire:
        Tiziano Vecellio | "(1476/77-1576), italiensk Maler."
     -> 06=1476, 07=1576, 08="1476/77", 09="italiensk Maler."

  B  09_description starts with the given name(s) AND the life-span:
        Titov | "Vladimir Pavlovic (dod 1891), russisk Diplomat og ..."
     -> 04="Vladimir Pavlovic", 07=1891, 09="russisk Diplomat og ..."

  G  04_given_names still carries a life-span parenthesis duplicated
     from the name text, while 06/07 are empty:
        "Carl (ca. 1820-ca.1876)" -> 04="Carl", 06=1820, 07=1876,
        08="ca."

What is deliberately NOT touched:

  * A parenthesis that is a DATE OF ENCOUNTER, not a life span
    ("Black | Amerikansk Beundrer (1871)", "Holstein | Familie fra
    Holbaek-Egnen (1869)"). Only a range, an explicit "d."/"dod", or an
    "f. Chr." form counts as life data -- a bare "(1871)" does not.
  * A leading phrase that is a TITLE rather than a given name
    ("Henrik III | Tysk-romersk Kejser (1017-1056)"). Moving that into
    04_given_names would assert the emperor's given name was
    "Tysk-romersk Kejser". Such rows get their years extracted but the
    phrase stays in the description.
  * Sibling-group descriptions listing several people with their own
    life spans ("Hildur (1835-1892), Inga (1841-1919) og Iduna ...") --
    the row describes a group, so no single birth/death applies.

  python scripts/parsers/refine_description_segmentation.py
"""
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")

# A genuine life span: a range, an explicit death, or a BC year.
LIFE = (
    r"\(\s*(?P<inner>"
    r"(?:d\.|død)\s*(?P<dy>\d{3,4})(?P<age>,\s*\d{1,3}\s*(?:år|Aa?r)\s*g[li]\.?)?"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})(?P<bfrac>/\d{2,4})?\s*(?:\(\?\))?\s*"
    r"[–—-]\s*(?:ca\.\s*|efter\s*)?(?P<d>\d{2,4})"
    r"|(?:ca\.\s*)?(?P<bc>\d{3,4})\s*f\.\s*Chr\."
    r")\s*(?P<fchr>f\.\s*Chr\.)?\s*\)"
)
LIFE_AT_START = re.compile(r"^" + LIFE)
# The name part may itself contain commas -- Danish register names carry
# a maiden name ("Elisa, f. Hallady") or a title ("Maria Elizabeth,
# Lady, f. Grevinde ...") before the life span. Stop at the first
# parenthesis instead of at the first comma.
NAME_THEN_LIFE = re.compile(r"^(?P<name>[A-ZÆØÅÖÜ][^()]{0,70}?)\s(?P<life>" + LIFE + r")")
GIVEN_LIFE = re.compile(LIFE)

# Leading phrases that are titles/roles, never given names.
TITLE_WORDS = (
    "konge", "kejser", "dronning", "fyrste", "hertug", "greve", "grevinde",
    "baron", "baronesse", "prins", "prinsesse", "pave", "biskop", "kurfyrste",
    "landgreve", "storhertug", "lensgreve", "friherre", "frøken", "frue",
    "datter", "søn", "broder", "søster", "enke", "familie", "brødrene",
    "moder", "fader", "hustru",
)
SIBLING_GROUP = re.compile(r"\(\d{3,4}\s*[–—-]\s*\d{2,4}\)[^()]*\(\d{3,4}\s*[–—-]\s*\d{2,4}\)")


def looks_like_title(phrase: str) -> bool:
    """True only when the phrase is a bare title/role with no personal
    name in it ("Tysk-romersk Kejser", "Fyrste"). A real name followed
    by a title or a maiden name is NOT a title -- "Elisa, f. Hallady"
    and "Maria Elizabeth, Lady, f. Grevinde ..." are given-name fields,
    so only the FIRST comma-unit is examined."""
    # A relation clause ("Datter af Heinrich Z.", "Søn af Hans P.")
    # describes the person, it does not name them.
    if re.match(r"^(?:datter|søn|broder|søster|enke|hustru|moder|fader)\s+(?:af|efter)\b",
                phrase.strip(), re.IGNORECASE):
        return True
    first_unit = phrase.split(",")[0]
    words = [w.strip(".,").lower() for w in first_unit.split()]
    return bool(words) and all(
        w in TITLE_WORDS or not w.isalpha() or w in ("af", "til", "von", "den", "det")
        for w in words
    )


def years_from(m) -> tuple:
    """(birth, death, note) from a LIFE match."""
    note = ""
    if m.group("age"):
        note = m.group("age").strip(", ")
    if m.group("dy"):
        return "", m.group("dy"), note
    if m.group("bc"):
        return m.group("bc"), "", "f. Kr. (BC)"
    b = m.group("b") or ""
    d = m.group("d") or ""
    if d and b and len(d) < len(b):
        d = b[: len(b) - len(d)] + d          # "1838-76" -> 1876
    if m.group("bfrac"):
        note = f"{b}{m.group('bfrac')}"        # "1476/77" preserved
    if m.group("fchr"):
        note = "f. Kr. (BC)"
    return b, d, note


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    n_a = n_b = n_g = n_title_only = 0

    for r in rows:
        desc = r["09_description"]

        # --- G: years duplicated inside 04_given_names ---------------
        if not r["06_birth_year"] and not r["07_death_year"]:
            m = GIVEN_LIFE.search(r["04_given_names"])
            if m:
                b, d, note = years_from(m)
                if b or d:
                    r["06_birth_year"] = r["06_birth_year"] or b
                    r["07_death_year"] = r["07_death_year"] or d
                    if note and not r["08_year_note"]:
                        r["08_year_note"] = note
                    r["04_given_names"] = (
                        r["04_given_names"][: m.start()] + r["04_given_names"][m.end():]
                    ).strip().rstrip(",").strip()
                    r["05_sort_key"] = f"{r['03_surname']}, {r['04_given_names']}".strip().rstrip(",")
                    n_g += 1

        if r["06_birth_year"] or r["07_death_year"] or not desc:
            continue
        if SIBLING_GROUP.search(desc):
            continue   # a group of people, not one person's dates

        # --- A: description opens with the life span -----------------
        m = LIFE_AT_START.match(desc)
        if m:
            b, d, note = years_from(m)
            r["06_birth_year"], r["07_death_year"] = b, d
            if note and not r["08_year_note"]:
                r["08_year_note"] = note
            r["09_description"] = desc[m.end():].strip().lstrip(",").strip()
            n_a += 1
            continue

        # --- B: description opens with given name + life span --------
        m = NAME_THEN_LIFE.match(desc)
        if m:
            inner = re.match(LIFE, m.group("life"))
            b, d, note = years_from(inner)
            r["06_birth_year"], r["07_death_year"] = b, d
            if note and not r["08_year_note"]:
                r["08_year_note"] = note
            rest = desc[m.end():].strip().lstrip(",").strip()
            phrase = m.group("name").strip()
            if looks_like_title(phrase):
                # Keep the title in the description; only years move.
                r["09_description"] = f"{phrase}, {rest}".strip().rstrip(",")
                n_title_only += 1
            elif not r["04_given_names"].strip():
                r["04_given_names"] = phrase
                r["05_sort_key"] = f"{r['03_surname']}, {phrase}".strip().rstrip(",")
                r["09_description"] = rest
                n_b += 1
            else:
                r["09_description"] = rest
                n_title_only += 1

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"A  years lifted from start of description : {n_a}")
    print(f"B  given names + years lifted             : {n_b}")
    print(f"G  years lifted out of 04_given_names     : {n_g}")
    print(f"   years lifted, leading phrase kept as title/description: {n_title_only}")


if __name__ == "__main__":
    main()
