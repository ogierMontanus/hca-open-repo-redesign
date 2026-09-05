#!/usr/bin/env python3
"""
fix_diacritics_from_xlsx.py
-----------------------------
Corrects lost foreign-vowel diacritics (ö, ü, é, ô, …) in
data/parsed/personregister_xi_parsed.tsv's 03_surname, 04_given_names
and 09_description fields, using
data/raw/HCA REPOSITORY V0.92/PersonData-PQ-V0.92.xlsx (sheet DimPer)
as the reference.

Background: comparing row counts between this parser's output and
DimPer found that ~300 of the ~600 "no year-key match" entries are not
missing people at all -- they are the SAME person, but this project's
OCR source (raw/dagbog-bd-11-3408_Claus-OCR test ABBYY.pdf) drops
diacritics on foreign names ("Alrnlôf" for "Almlöf", "Bjorck" for
"Björck", "Blucher" for "Blücher"), so a plain-text surname match
against DimPer's correctly-accented titles fails even though both
sources describe the same entry.

Danish Æ/Ø/Å are NOT touched -- Unicode NFKD does not decompose them
(they are independent letters, not base+combining-mark pairs), so
stripping combining marks for matching purposes never risks damaging
them.

Matching key: (diacritic-stripped surname, birth year, death year).
This is precise -- both fields must match exactly -- so it does not
mis-fire across different people who merely share a stripped surname.
Only entries where MY data lacks a diacritic-affected character AND the
matched xlsx title's stripped form equals mine are corrected; if xlsx's
title, stripped, does NOT equal mine, nothing is touched (that is a
substantive difference, not a diacritic issue -- left for the
comparison step, not silently overwritten here).

For 09_description: xlsx's RegistryDescription is compared word-by-word
against mine (after diacritic-stripping); a word is replaced only when
the stripped forms are identical AND my field actually differs from
theirs only in diacritics (never when other differences exist -- this
avoids importing xlsx's own OCR/wording differences into 09_description
under the banner of a "diacritic fix").

Run from the repo root, AFTER parse_personregister_xi.py:
  python scripts/parsers/fix_diacritics_from_xlsx.py
"""
import csv
import os
import re
import sys
import unicodedata

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
XLSX_PATH = os.path.join(ROOT, "data", "raw", "HCA REPOSITORY V0.92", "PersonData-PQ-V0.92.xlsx")


def strip_diacritics(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c))


def xl_surname(title: str) -> str:
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(title))
    return t.split(",")[0].strip()


def xl_given(title: str) -> str:
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str(title))
    parts = t.split(",", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def load_xlsx_index():
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]
    # key: (stripped surname, birth, death) -> list of (surname, given, description)
    index = {}
    for pid, title, desc, birth, death in dim:
        if birth is None or death is None:
            continue
        surname = xl_surname(title)
        given = xl_given(title)
        key = (strip_diacritics(surname).lower(), int(birth), int(death))
        index.setdefault(key, []).append((surname, given, desc or ""))
    return index


def fix_field(mine_value: str, xl_value: str) -> tuple[str, bool]:
    """Replace mine_value with xl_value ONLY if they are identical once
    diacritics are stripped (i.e. the only difference IS diacritics).
    Returns (possibly-corrected value, changed?)."""
    if mine_value == xl_value:
        return mine_value, False
    if strip_diacritics(mine_value).lower() == strip_diacritics(xl_value).lower():
        return xl_value, True
    return mine_value, False


def fix_description(mine_desc: str, xl_desc: str) -> tuple[str, bool]:
    """Word-level diacritic fix: xlsx descriptions differ from mine in
    capitalization and punctuation conventions (xlsx starts sentences
    with a capital typographic style, mine follows the register's
    lowercase-after-comma style) well beyond diacritics, so a whole-
    field fix() would falsely reject almost every real diacritic case.
    Instead, walk aligned tokens and swap in the xlsx spelling only
    where the two tokens are diacritic-identical AND letter-count
    identical (never touching wording, punctuation, or case)."""
    my_tokens = mine_desc.split(" ")
    xl_tokens = xl_desc.split(" ")
    if len(my_tokens) != len(xl_tokens):
        return mine_desc, False
    changed = False
    out = []
    for mt, xt in zip(my_tokens, xl_tokens):
        mt_core = mt.strip(".,;:")
        xt_core = xt.strip(".,;:")
        if mt_core != xt_core and strip_diacritics(mt_core).lower() == strip_diacritics(xt_core).lower():
            # Preserve mine's surrounding punctuation and capitalization
            # pattern except for the specific accented letters.
            if mt_core.islower() or not mt_core[:1].isalpha():
                replacement_core = xt_core.lower() if xt_core[:1].isupper() and not mt_core[:1].isupper() else xt_core
            else:
                replacement_core = xt_core
            new_tok = mt.replace(mt_core, replacement_core, 1) if mt_core in mt else mt
            out.append(new_tok)
            if new_tok != mt:
                changed = True
        else:
            out.append(mt)
    return (" ".join(out), True) if changed else (mine_desc, False)


def main():
    print(f"Læser {XLSX_PATH} ...")
    xl_index = load_xlsx_index()
    print(f"  {len(xl_index)} (efternavn+år)-nøgler indlæst fra DimPer")

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    fixed_surname = fixed_given = fixed_desc = 0
    fix_log = []

    for r in rows:
        if not (r["06_birth_year"] and r["07_death_year"]):
            continue
        b, d = int(r["06_birth_year"]), int(r["07_death_year"])
        if "f. Kr." in r["08_year_note"]:
            b, d = -b, -d
        key = (strip_diacritics(r["03_surname"]).lower(), b, d)
        candidates = xl_index.get(key)
        if not candidates or len(candidates) != 1:
            continue  # no match, or ambiguous (>1 xlsx person under this stripped key) -- skip, don't guess
        xl_surname_v, xl_given_v, xl_desc_v = candidates[0]

        before_surname = r["03_surname"]
        new_surname, ch1 = fix_field(r["03_surname"], xl_surname_v)
        new_given, ch2 = fix_field(r["04_given_names"], xl_given_v)
        new_desc, ch3 = fix_description(r["09_description"], xl_desc_v)

        if ch1:
            r["03_surname"] = new_surname
            fixed_surname += 1
        if ch2:
            r["04_given_names"] = new_given
            fixed_given += 1
        if ch3:
            r["09_description"] = new_desc
            fixed_desc += 1

        if ch1 or ch2 or ch3:
            r["05_sort_key"] = f"{r['03_surname']}, {r['04_given_names']}".strip().rstrip(",")
            fix_log.append((r["01_entry_id"], before_surname, r["03_surname"]))

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"  rettet 03_surname       : {fixed_surname}")
    print(f"  rettet 04_given_names   : {fixed_given}")
    print(f"  rettet 09_description   : {fixed_desc}")
    print(f"  wrote {os.path.relpath(PARSED_TSV, ROOT)}")
    print()
    print("Eksempler på surname-rettelser:")
    for eid, before, after in fix_log[:20]:
        if before != after:
            print(f"  {eid} | {before!r} -> {after!r}")


if __name__ == "__main__":
    main()
