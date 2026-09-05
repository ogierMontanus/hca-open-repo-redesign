#!/usr/bin/env python3
"""
suggest_leading_firstname_splits.py
---------------------------------------
Finds rows whose 04_given_names is empty but 09_description actually
OPENS with the person's given name(s) and life span, e.g.:

    Bang | (empty) | "Chr. Asmus (død 1888, 62 Aar gl.), Skibsforer."
    -> 04="Chr. Asmus", 07=1888, 08="62 Aar gl.", 09="Skibsforer."

This is the same shape refine_description_segmentation.py's pattern B
already fixes -- but B only fires when the leading phrase already looks
like a name (capitalised word(s), no obvious profession word). This
script instead builds an INTERNAL FIRSTNAME INDEX from every row that
already has a populated 04_given_names (thousands of confirmed real
given names in this exact register, in this exact orthography -- far
more reliable than a generic name list, since it already includes the
register's own abbreviation conventions: "Chr.", "Vilh.", "H. C.").

A candidate is accepted only when:
  1. 04_given_names is empty and 06/07 are both empty (nothing already
     extracted);
  2. the description opens with one or more tokens that each either
     match the internal firstname index, OR are a single-capital
     initial ("H.", "J. C.") -- both extremely common in this register;
  3. that name run is immediately followed by a life-span parenthesis
     (a range, "dod", or "f. Chr.") -- so a name mentioned in running
     prose ("Efter Frederik den Stores dod...") is not mistaken for the
     entry's own headword, which always pairs a name with ITS OWN dates
     at this exact position.

Guards against known false-positive classes (see
refine_description_segmentation.py's docstring for the same catalogue):
  * bare titles ("Fyrste", "Baronesse") are not names -- they are never
    added to the index in the first place, since they never appear as a
    04_given_names value on their own in this data;
  * a leading profession word that happens to capitalise like a name
    ("Digter", "Skibsforer") is excluded because it is not IN the index
    and is not a bare initial;
  * common Danish/German words that could theoretically capitalise at
    a sentence start are not in the index unless they are ALSO attested
    as a given name elsewhere in this register.

Reporting only. Writes
data/curated/personregister_xi_leading_firstname_review.tsv and changes
nothing in personregister_xi_parsed.tsv.

  python scripts/parsers/suggest_leading_firstname_splits.py
"""
import csv
import os
import re
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_leading_firstname_review.tsv")

LIFE = (
    r"\(\s*(?:"
    r"(?:d\.|død)\s*(?P<dy>\d{3,4})(?P<age>,\s*\d{1,3}\s*(?:år|Aa?r)\s*g[li]\.?)?"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})(?P<bfrac>/\d{2,4})?\s*(?:\(\?\))?\s*"
    r"[–—-]\s*(?:ca\.\s*|efter\s*)?(?P<d>\d{2,4}|\?)"
    r"|(?:ca\.\s*)?(?P<bc>\d{3,4})\s*f\.\s*Chr\."
    r")\s*(?P<fchr>f\.\s*Chr\.)?\s*\)"
)
LIFE_RE = re.compile(LIFE)

NAME_TOKEN = re.compile(r"^[A-ZÆØÅÖÜ][a-zæøåöäü]*\.?$")
INITIAL_TOKEN = re.compile(r"^[A-ZÆØÅÖÜ]\.$")

# Words that capitalise like a name at the start of a sentence but are
# professions/roles/relations in this register -- never treated as a
# name even if (implausibly) present in the harvested index.
NEVER_NAME = {
    "digter", "forfatter", "forfatterinde", "skibsfører", "skuespiller",
    "skuespillerinde", "maler", "billedhugger", "professor", "læge",
    "præst", "biskop", "grosserer", "student", "søn", "datter", "broder",
    "søster", "enke", "enkefrue", "frøken", "frue", "hustru", "moder",
    "fader", "familie", "konge", "dronning", "fyrste", "greve",
    "grevinde", "baron", "baronesse", "prins", "prinsesse",
}


def load_firstname_index(rows):
    counts = Counter()
    for r in rows:
        gn = r["04_given_names"]
        if not gn.strip():
            continue
        first_unit = re.sub(r"\([^)]*\)", "", gn.split(",")[0]).strip()
        for tok in first_unit.split():
            if NAME_TOKEN.match(tok) and tok.lower() not in NEVER_NAME:
                counts[tok] += 1
    return counts


def leading_name_run(desc, index):
    """Consume tokens from the start of desc as long as each is either a
    known firstname or a bare initial. Returns (name_text, rest_offset)
    or None."""
    tokens = desc.split(" ")
    taken = []
    pos = 0
    for tok in tokens:
        core = tok.rstrip(",")
        is_initial = bool(INITIAL_TOKEN.match(core))
        is_known = index.get(core, 0) >= 2  # attested at least twice elsewhere
        if not (is_initial or is_known):
            break
        taken.append(tok)
        pos += len(tok) + 1
        if tok.endswith(","):
            break
    if not taken:
        return None
    name_text = " ".join(taken).rstrip(",")
    return name_text, pos


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    index = load_firstname_index(rows)
    print(f"internal firstname index: {len(index)} distinct tokens "
          f"(from {sum(1 for r in rows if r['04_given_names'].strip())} populated rows)")

    out_rows = []
    for r in rows:
        if r["04_given_names"].strip() or r["06_birth_year"] or r["07_death_year"]:
            continue
        desc = r["09_description"]
        if not desc:
            continue

        run = leading_name_run(desc, index)
        if not run:
            continue
        name_text, offset = run

        m = LIFE_RE.match(desc[offset:])
        if not m:
            continue

        out_rows.append({
            "entry_id": r["01_entry_id"],
            "surname": r["03_surname"],
            "proposed_given_names": name_text,
            "life_span_matched": m.group(0),
            "remaining_description": desc[offset + m.end():].strip().lstrip(",").strip(),
            "full_original_description": desc,
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    if out_rows:
        with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(out_rows)

    print(f"candidates found: {len(out_rows)}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


if __name__ == "__main__":
    main()
