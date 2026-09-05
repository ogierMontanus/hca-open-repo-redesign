#!/usr/bin/env python3
"""
import_reference_missing_candidates.py
------------------------------------------
Imports the 958 people that data/raw/Personer _ HCA_tsv.txt lists but
personregister_xi_parsed.tsv lacks (see
data/curated/personregister_xi_reference_missing_candidates.tsv, built
by the name-difference pass).

Each imported row is built entirely from the reference: name -> surname
/ given names / years, description, and volume:page references. New rows
are inserted in the sort position their surname belongs at, then all
entry ids are renumbered (they are positional).

One orthographic correction is applied on import, per review:
  "Ûxküll (Uexküll), Clara, ..." -> "Üxküll (Uexküll), Clara, ..."
(the reference's OCR read U+00DB LATIN CAPITAL LETTER U WITH CIRCUMFLEX
for U+00DC LATIN CAPITAL LETTER U WITH DIAERESIS).

  python scripts/parsers/import_reference_missing_candidates.py
"""
import csv
import os
import re
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
CANDIDATES_TSV = os.path.join(
    ROOT, "data", "curated", "personregister_xi_reference_missing_candidates.tsv"
)

# Reviewed orthographic fixes to apply to reference text on import.
ORTHOGRAPHIC_FIXES = {
    "Û": "Ü",  # Û -> Ü
}

YEARS_TAIL = re.compile(
    r"\(\s*(?:(?:d\.|død)\s*(?P<dy>\d{3,4})(?P<age>,\s*\d{1,3}\s*[åa]r\s*gl\.?)?"
    # Birth may carry an uncertainty marker ("480(?)-406") and the death
    # year may be abbreviated to 2 digits, including in BC ranges
    # ("356-23 f.Chr." = 356-323 BC).
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})\s*(?:\(\?\))?\s*[–—-]\s*"
    r"(?:ca\.\s*|efter\s*)?(?P<d>\d{2,4}|\?)"
    r"|(?P<bo>\d{3,4}))\s*(?P<fchr>f\.\s*Chr\.)?\s*\)\s*$",
    re.IGNORECASE,
)
# "(12. Aarhundrede)" / "(4.Aarh.f.Chr.)" is a period, not a year pair:
# it stays part of the name rather than being parsed into 06/07.
CENTURY_PAREN = re.compile(r"\(\s*\d{1,2}\.\s*(?:Aarh|Årh)", re.IGNORECASE)


def apply_orthographic_fixes(s: str) -> str:
    for bad, good in ORTHOGRAPHIC_FIXES.items():
        s = s.replace(bad, good)
    return s


def split_name(name: str):
    """'Aabye, Johan Peter (1818-1880)' ->
       (surname, given, birth, death, note)"""
    note = birth = death = ""
    core = name.strip()
    m = YEARS_TAIL.search(core)
    if m:
        core = core[: m.start()].strip()
        if m.group("fchr"):
            note = "f. Kr. (BC)"
        if m.group("age"):
            note = m.group("age").strip(", ")
        if m.group("dy"):
            death = m.group("dy")
        elif m.group("bo"):
            birth = m.group("bo")
        else:
            birth = m.group("b") or ""
            d = m.group("d") or ""
            if d != "?" and d.isdigit():
                # "1838-76" is 1876, the register's abbreviated range.
                death = birth[: len(birth) - len(d)] + d if len(d) < len(birth) else d
    if "," in core:
        surname, given = core.split(",", 1)
        return surname.strip(), given.strip(), birth, death, note
    # No comma: a single-name/epithet entry. Any parenthetical left on it
    # ("Bertran de Bom (12. Aarhundrede)", "Frauenlob (Heinrich von
    # Meissen)") belongs in given names -- 03_surname must never contain
    # a parenthesis, per the parser's convention and its regression test.
    paren = core.find("(")
    if paren != -1:
        return core[:paren].strip(), core[paren:].strip(), birth, death, note
    return core, "", birth, death, note


def parse_refs(refs_field: str):
    """'IV:422–423;IV:425' -> ('IV 422-423. IV 425.', 'IV:422;IV:423;IV:425')"""
    raw_parts, parsed = [], []
    for item in (x.strip() for x in refs_field.split(";") if x.strip()):
        if ":" not in item:
            continue
        vol, page = item.split(":", 1)
        vol, page = vol.strip(), page.strip().replace("–", "-").replace("—", "-")
        raw_parts.append(f"{vol} {page}")
        if "-" in page:
            a, b = page.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if hi < lo:
                    hi = int(str(lo)[: len(str(lo)) - len(b)] + b)
                parsed.extend(f"{vol}:{n}" for n in range(lo, hi + 1))
                continue
        if page.isdigit():
            parsed.append(f"{vol}:{page}")
    return (". ".join(raw_parts) + "." if raw_parts else ""), ";".join(parsed)


def sort_key(surname: str, given: str):
    """Danish register order: surname first, Aa folded to Å (see
    CLAUDE.md's alphabetisation rule)."""
    s = unicodedata.normalize("NFKD", f"{surname} {given}".lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("aa", "å")


def main():
    with open(CANDIDATES_TSV, encoding="utf-8") as f:
        candidates = list(csv.DictReader(f, delimiter="\t"))

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    new_rows = []
    for c in candidates:
        name = apply_orthographic_fixes(c["reference_name"])
        desc = apply_orthographic_fixes(c["reference_desc"])
        surname, given, birth, death, note = split_name(name)
        refs_raw, refs_parsed = parse_refs(c["reference_refs"])

        r = {k: "" for k in fieldnames}
        r.update({
            "02_entry_type": "standardpost",
            "03_surname": surname,
            "04_given_names": given,
            "05_sort_key": f"{surname}, {given}".strip().rstrip(","),
            "06_birth_year": birth,
            "07_death_year": death,
            "08_year_note": note,
            "09_description": desc,
            "10_references_raw": refs_raw,
            "11_references_parsed": refs_parsed,
            "13_raw_text": f"{name}, {desc} {refs_raw}".strip(),
        })
        new_rows.append(r)

    # Insert each new row at its alphabetical position WITHOUT re-sorting
    # the existing file: the register's own order deviates from a plain
    # sort in ~600 places (particle surnames filed under the particle,
    # epithets, cross-reference placement), and a global sort would
    # silently discard that editorial ordering. Each new row is placed
    # before the first existing row that sorts after it.
    existing_keys = [sort_key(r["03_surname"], r["04_given_names"]) for r in rows]
    merged = list(rows)
    merged_keys = list(existing_keys)
    for r in sorted(new_rows, key=lambda x: sort_key(x["03_surname"], x["04_given_names"])):
        k = sort_key(r["03_surname"], r["04_given_names"])
        pos = len(merged)
        for i, ek in enumerate(merged_keys):
            if ek > k:
                pos = i
                break
        merged.insert(pos, r)
        merged_keys.insert(pos, k)

    for i, r in enumerate(merged, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(merged)

    with_years = sum(1 for r in new_rows if r["06_birth_year"] or r["07_death_year"])
    print(f"imported {len(new_rows)} entries ({with_years} with year data)")
    print(f"rows: {len(rows)} -> {len(merged)}")


if __name__ == "__main__":
    main()
