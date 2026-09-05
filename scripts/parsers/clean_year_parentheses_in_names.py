#!/usr/bin/env python3
"""
clean_year_parentheses_in_names.py
--------------------------------------
Removes the redundant year-parenthesis left inside 04_given_names, which
duplicates the dedicated 06_birth_year/07_death_year columns
("Anker, Johan (1838-76)" where 06/07 already hold 1838/1876).

Where the parenthesis holds years the year columns do NOT have -- the
register's "(død 1885, 84 år gl.)" form, which the main parser's
YEAR_RE never matched because of the trailing age clause -- the years
are moved into 06/07 (and the age clause preserved in 08_year_note)
before the parenthesis is dropped, so no information is lost.

A parenthesis that is not a year statement ("(eller: Agnelli)",
"(13. Aarhundrede)", "(Pseud. for Leon Lherie)") is left untouched:
those are part of the name.

  python scripts/parsers/clean_year_parentheses_in_names.py
"""
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")

# A parenthesis that IS a year statement, in any of the register's forms.
YEAR_PAREN = re.compile(
    r"\s*\(\s*(?:"
    r"(?:d\.|død)\s*(?P<dy>\d{3,4})(?P<age>,\s*\d{1,3}\s*[åa]r\s*gl\.?)?"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})\s*[–—-]\s*(?P<d>\d{2,4}|\?)"
    r"|(?P<bo>\d{3,4})"
    r")\s*(?P<fchr>f\.\s*Chr\.)?\s*\)"
)


def expand_death(birth: str, death: str) -> str:
    """'1838-76' -> 1876, matching the register's abbreviated ranges."""
    if not (birth and death and death.isdigit()):
        return death
    if len(death) < len(birth):
        return birth[: len(birth) - len(death)] + death
    return death


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    cleaned = recovered = 0
    for r in rows:
        given = r["04_given_names"]
        m = YEAR_PAREN.search(given)
        if not m:
            continue

        b = m.group("b") or m.group("bo") or ""
        d = expand_death(b, m.group("d") or "") if m.group("d") else (m.group("dy") or "")
        note = "f. Kr. (BC)" if m.group("fchr") else ""
        age = (m.group("age") or "").strip(", ")

        # Recover years the parser never captured before discarding them.
        if b and not r["06_birth_year"].strip():
            r["06_birth_year"] = b
            recovered += 1
        if d and not r["07_death_year"].strip():
            r["07_death_year"] = d
            recovered += 1
        if note and not r["08_year_note"].strip():
            r["08_year_note"] = note
        if age and not r["08_year_note"].strip():
            r["08_year_note"] = age

        r["04_given_names"] = (given[: m.start()] + given[m.end():]).strip().rstrip(",").strip()
        r["05_sort_key"] = f"{r['03_surname']}, {r['04_given_names']}".strip().rstrip(",")
        cleaned += 1

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"cleaned year-parenthesis out of 04_given_names : {cleaned}")
    print(f"year values recovered into 06/07 in the process : {recovered}")


if __name__ == "__main__":
    main()
