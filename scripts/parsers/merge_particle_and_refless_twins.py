#!/usr/bin/env python3
"""
merge_particle_and_refless_twins.py
---------------------------------------
A second duplicate class dedupe_imported_twins.py could not see.

That script grouped rows by their FULL page-reference signature, so it
only matched twins where both copies carried references. But the import
also produced pairs where one copy has references and the other has
none, and where the surnames differ by a leading particle:

    d'Auchamp, F. L. F. (1810-1872)   VIII 146.      <- imported
    Auchamp,   F. L. F. (1810-1872)   (no refs)      <- ours

Those are the same person. The register files such names under the
PARTICLE ("d'Auchamp" under A... in the printed volume the entry is
alphabetised on Auchamp but printed with its particle, and d'Ohsson
likewise appears under O), so the copy WITH the particle is the correct
headword form and is kept.

Matching key: diacritic-insensitive surname with any leading particle
stripped, plus given names, plus both years -- deliberately NOT the page
references, since one side having none is the whole point.

Which copy wins: the one with page references (the import supplied
those). But its DESCRIPTION is replaced by ours where the two differ
only by the reference transcription's systematic C->G confusion, which
is visible in exactly these rows:
    ours "Svigersoen af C. D. Rauch"  vs import "... G. D. Rauch"
    ours "Puggaard, C."               vs import "Puggaard, G."
    ours "Riegels, H. C."             vs import "Riegels, H. G."
So given names and description are taken from our copy, references and
years from the import.

  python scripts/parsers/merge_particle_and_refless_twins.py
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")

PARTICLES = r"(?:d[’'`]|de\s|van\s|von\s|le\s|la\s|di\s|af\s)"


def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def key_surname(s):
    s = strip_diacritics(s).lower().strip()
    s = re.sub(r"^" + PARTICLES + r"\s*", "", s)
    return re.sub(r"[^a-z]", "", s)


def key_given(s):
    s = strip_diacritics(s).lower()
    # "H. C." and "H.C." and "H. G." must compare on letters only, but
    # C/G is exactly the distinction that matters here, so it is KEPT --
    # only spacing and punctuation are normalised away.
    return re.sub(r"[^a-z0-9]", "", s)


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    groups = defaultdict(list)
    for r in rows:
        if r["02_entry_type"] != "standardpost":
            continue
        groups[(
            key_surname(r["03_surname"]),
            r["06_birth_year"],
            r["07_death_year"],
        )].append(r)

    drop, merged = set(), 0
    for members in groups.values():
        if len(members) < 2:
            continue
        # Only pair up rows whose given names agree apart from the C/G
        # confusion, so unrelated same-surname relatives never merge.
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if id(a) in drop or id(b) in drop:
                    continue
                ga, gb = key_given(a["04_given_names"]), key_given(b["04_given_names"])
                same = ga == gb or ga.replace("g", "c") == gb.replace("g", "c")
                if not same or not ga:
                    continue
                has_a = bool(a["11_references_parsed"].strip())
                has_b = bool(b["11_references_parsed"].strip())
                if has_a == has_b:
                    continue    # not the refs/no-refs pair this targets

                winner, loser = (a, b) if has_a else (b, a)
                # Keep OUR name and description (the ref copy carries
                # its own C->G OCR errors); keep the import's refs.
                if loser["04_given_names"].strip():
                    winner["04_given_names"] = loser["04_given_names"]
                if loser["09_description"].strip():
                    winner["09_description"] = loser["09_description"]
                for fld in ("08_year_note", "12_see_also"):
                    if not winner[fld].strip() and loser[fld].strip():
                        winner[fld] = loser[fld]
                winner["05_sort_key"] = (
                    f"{winner['03_surname']}, {winner['04_given_names']}".strip().rstrip(",")
                )
                drop.add(id(loser))
                merged += 1

    out = [r for r in rows if id(r) not in drop]
    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"twins merged : {merged}")
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
