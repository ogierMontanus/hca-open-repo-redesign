#!/usr/bin/env python3
"""
calibrate_names_from_reference.py
-------------------------------------
Fills in 04_given_names (and 06/07 years, where they follow from the
same name) for rows whose given names our parser never extracted, using
data/raw/Personer _ HCA_tsv.txt.

Why a page-reference key rather than a name key: the two sources are
independent transcriptions that differ in dash style, capitalisation,
line-wrap hyphenation and -- crucially -- in OCR character errors, so
name text is NOT a stable join key. Volume/page numbers are, because
both sources transcribe the same printed reference lists. Joining on
(surname, first page reference) and requiring a UNIQUE reference hit
was measured at 91% agreement against the 4605 of our rows that already
carry given names, which is what justifies trusting it for the rows
that do not.

The 9% disagreement is itself informative and is the reason this script
only ever FILLS EMPTY fields, never overwrites a value we already have:
inspection showed the reference carries its own OCR defects that our
text gets right (it reads "G.J.L." for Almqvist's "C.J.L.",
"Gornelis" for "Cornelis" -- a systematic C->G confusion), and a
shared first page reference can legitimately belong to two members of
the same family (Anker, Arnim, Aminoff). So:

  - given names are filled ONLY where ours is empty;
  - years are filled ONLY where ours are empty AND the reference states
    them;
  - nothing is ever overwritten, and a non-unique key is skipped.

Reports what it changed; writes personregister_xi_parsed.tsv in place.

  python scripts/parsers/calibrate_names_from_reference.py
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REF_TXT = os.path.join(ROOT, "data", "raw", "Personer _ HCA_tsv.txt")

YEARS_TAIL = re.compile(
    r"\(\s*(?:(?:d\.|død)\s*(?P<dy>\d{3,4})"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})\s*[–—-]\s*(?P<d>\d{3,4}|\?)"
    r"|(?P<bo>\d{3,4}))\s*(?P<fchr>f\.\s*Chr\.)?\s*\)\s*$"
)


def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s):
    s = strip_diacritics(s).lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_name_years(name):
    """'Aller, Peter van (død 1885, 84 år gl.)' -> ('Aller, Peter van', b, d, note)"""
    m = YEARS_TAIL.search(name)
    if not m:
        return name.strip(), "", "", ""
    core = name[: m.start()].strip()
    note = "f. Kr. (BC)" if m.group("fchr") else ""
    if m.group("dy"):
        return core, "", m.group("dy"), note
    if m.group("bo"):
        return core, m.group("bo"), "", note
    d = m.group("d") or ""
    return core, m.group("b") or "", ("" if d == "?" else d), note


def load_reference():
    entries = []
    with open(REF_TXT, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2 or not p[0].strip() or p[0] == "Navn":
                continue
            refs, rest = [], p[2:]
            for i in range(0, len(rest) - 1, 2):
                vol, page = rest[i].strip(), rest[i + 1].strip()
                if vol and page:
                    refs.append(f"{vol}:{page}")
            entries.append({"name": p[0].strip(), "desc": p[1].strip(), "refs": refs})
    index = defaultdict(list)
    for e in entries:
        surname = norm(e["name"].split(",")[0].split("(")[0])
        if e["refs"]:
            index[(surname, e["refs"][0])].append(e)
    return entries, index


def main():
    entries, index = load_reference()
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    filled_given = filled_years = 0
    samples = []

    for r in rows:
        first_ref = r["11_references_parsed"].split(";")[0] if r["11_references_parsed"] else ""
        if not first_ref:
            continue
        cands = index.get((norm(r["03_surname"]), first_ref), [])
        if len(cands) != 1:
            continue  # ambiguous -- never guess between two family members

        core, b, d, note = split_name_years(cands[0]["name"])
        ref_given = core.split(",", 1)[1].strip() if "," in core else ""

        if ref_given and not r["04_given_names"].strip():
            r["04_given_names"] = ref_given
            r["05_sort_key"] = f"{r['03_surname']}, {ref_given}".strip().rstrip(",")
            filled_given += 1
            if len(samples) < 15:
                samples.append((r["01_entry_id"], r["03_surname"], ref_given))

        if b and not r["06_birth_year"].strip():
            r["06_birth_year"] = b
            filled_years += 1
        if d and not r["07_death_year"].strip():
            r["07_death_year"] = d
        if note and not r["08_year_note"].strip():
            r["08_year_note"] = note

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"filled 04_given_names : {filled_given}")
    print(f"filled 06_birth_year  : {filled_years}")
    print()
    for eid, sn, gn in samples:
        print(f"  {eid} | {sn} -> {gn}")


if __name__ == "__main__":
    main()
