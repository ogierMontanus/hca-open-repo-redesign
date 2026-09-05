#!/usr/bin/env python3
"""
suggest_malformed_xref_splits.py
------------------------------------
Repairs the `crossReferenceMalformed` class: a cross-reference glued to
the entry that follows it in the printed register, so both end up in one
row's 04_given_names:

    03_surname       = "Jonas"
    04_given_names   = "se: Collin, Jonas d. Y. Jonas, Emil"
    09_description   = "tysk Litterat og Oversætter, 1852-54 …"
    10_references_raw= "IV 158. X 329."

That is two entries. The cross-reference "Jonas, se: Collin, Jonas d. Y."
carries no description and no page references of its own; everything else
in the row -- description, years, references -- belongs to the SECOND
person, "Jonas, Emil".

The class was identified by classify_entity_type.py in the enrichment
chain (datacleaning/diaries_datacleaning). It counts 22 rows, up from 5
before the chain was run on master1 -- not because the cleanup made things
worse, but because master1 has ~1,150 more rows and therefore exposes more
of this same fusion. Each one hides a real person who is currently
unreachable.

Split rule
    04_given_names  =  <xref tail>  se[ ogsaa][:]  <target>.  <Name, Given>
                       └── row 1 ──────────────┘   └── row 2 ─┘

Row 1 (krydshenvisning): keeps 03_surname, gets the xref tail as its
given-name qualifier and the target in 12_see_also. No description, no
references -- the register gives it none.

Row 2 (standardpost): the name after the target's closing period becomes
surname + given names; the original row's description, years and
references move here unchanged, because they were always this person's.

Two rows are deliberately NOT auto-split and are reported for review:
  * a row whose 04_given_names has no "se" at all (a different defect --
    description bled into the name field);
  * "vist: Dreibein, se denne" -- a self-contained cross-reference
    ("see this one") with no separate target name to split on.

Reporting only. Writes
data/curated/personregister_xi_malformed_xref_review.tsv; use --apply to
write the split into personregister_xi_parsed.tsv.

  python scripts/parsers/suggest_malformed_xref_splits.py
  python scripts/parsers/suggest_malformed_xref_splits.py --apply
"""
import argparse
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
OUT_TSV = os.path.join(ROOT, "data", "curated",
                       "personregister_xi_malformed_xref_review.tsv")

# "se:", "se ogsaa:", "se" — the register is inconsistent about the colon.
SE_RE = re.compile(r"\bse(?:\s+og[s]?aa)?\s*:?\s+", re.IGNORECASE)
# "vist: X, se denne" — points at itself, nothing to split off.
SELF_REF_RE = re.compile(r"\bse\s+denne\b", re.IGNORECASE)


def split_given(given: str):
    """-> (xref_tail, target, second_name) or None when the shape does not fit."""
    m = SE_RE.search(given)
    if not m:
        return None
    tail = given[: m.start()].strip(" ,")
    rest = given[m.end():].strip()

    # Where does the cross-reference target end and the next entry begin?
    # A period alone is not the signal: the target itself routinely ends in
    # initials ("Collin, Jonas d. Y.", "Møller, A. C. A. From"), and the
    # target often carries its own given name after a comma ("Reybaud,
    # Fanny"), so cutting at the first period gets both wrong.
    #
    # The next entry is a register headword, so it looks like a headword:
    # a capitalised surname immediately followed by a comma or an opening
    # parenthesis. Cut at the LAST such candidate that still leaves a
    # non-empty target -- the target's own comma comes earlier in the
    # string than the following entry's does.
    best = None
    for mm in re.finditer(r"\.\s+(?=([A-ZÆØÅÖÜ][^\s,(]*(?:\s+[A-ZÆØÅÖÜ][^\s,(]*)*)\s*[,(])",
                          rest):
        target = rest[: mm.start()].strip(" .,")
        second = rest[mm.end():].strip()
        # A cut that leaves the target's own trailing initials stranded at
        # the head of the next entry ("Mackay, D." + "J. Kameliadamen") is
        # the wrong cut: pull leading initials back onto the target.
        while re.match(r"^[A-ZÆØÅÖÜ]\.\s+\S", second):
            initial, second = second.split(None, 1)
            target = f"{target} {initial}".strip()
        if target and second:
            best = (tail, target, second)
    if best:
        return best

    # No headword shape found -- fall back to a period before a capitalised
    # word, but only when what follows is long enough to be an entry rather
    # than a trailing initial.
    for mm in re.finditer(r"\.\s+(?=[A-ZÆØÅÖÜ])", rest):
        target = rest[: mm.start()].strip(" .,")
        second = rest[mm.end():].strip()
        if target and len(second) > 3:
            return tail, target, second
    return None


def split_name(text: str):
    """'Brodersen, Charlotte, f. Hornemann' -> (surname, given)."""
    if "," in text:
        s, g = text.split(",", 1)
        return s.strip(), g.strip()
    paren = text.find("(")
    if paren == -1:
        return text.strip(), ""
    return text[:paren].strip(), text[paren:].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the splits into personregister_xi_parsed.tsv")
    args = ap.parse_args()

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    proposals, skipped = [], []
    for r in rows:
        given = r["04_given_names"]
        if not SE_RE.search(given):
            continue
        if SELF_REF_RE.search(given):
            skipped.append((r, "selvhenvisning (»se denne«) — intet mål at splitte på"))
            continue
        parts = split_given(given)
        if not parts:
            skipped.append((r, "kunne ikke findes en navnegrænse efter målet"))
            continue
        tail, target, second = parts
        # The register writes the target as "Efternavn, Fornavn"; a period
        # inside it ("Reybaud. Fanny", "Beutner. C") is OCR for that comma,
        # and a bare trailing initial belongs to the target's own name.
        # Only a period before a full WORD is the misread comma; a period
        # before another initial ("A. C. A. From") is just an initial.
        target = re.sub(r"\.\s+(?=[A-ZÆØÅÖÜ][a-zæøåöäü])", ", ", target).strip(" .,")
        # A leading initial left at the head of the following entry is the
        # target's ("Mackay, D" + "J. Kameliadamen" -> "Mackay, D. J.").
        while re.match(r"^[A-ZÆØÅÖÜ]\.\s+\S", second):
            initial, second = second.split(None, 1)
            target = f"{target}{'' if target.endswith(',') else ''} {initial}".strip()
        sn2, gn2 = split_name(second)
        if not sn2:
            skipped.append((r, "tom efterfølgende post"))
            continue
        proposals.append((r, tail, target, sn2, gn2))

    if args.apply:
        out = []
        for r in rows:
            match = next((p for p in proposals if p[0] is r), None)
            if not match:
                out.append(r)
                continue
            _, tail, target, sn2, gn2 = match

            xref = {k: "" for k in fieldnames}
            xref.update({
                "02_entry_type": "krydshenvisning",
                "03_surname": r["03_surname"],
                "04_given_names": tail,
                "05_sort_key": f"{r['03_surname']}, {tail}".strip().rstrip(","),
                "12_see_also": target,
                "13_raw_text": f"{r['03_surname']}, {given_of(r)}",
            })
            out.append(xref)

            person = dict(r)
            person.update({
                "02_entry_type": "standardpost",
                "03_surname": sn2,
                "04_given_names": gn2,
                "05_sort_key": f"{sn2}, {gn2}".strip().rstrip(","),
                "12_see_also": "",
                "13_raw_text": f"{sn2}, {gn2} {r['09_description']} {r['10_references_raw']}".strip(),
            })
            out.append(person)

        for i, r in enumerate(out, start=1):
            r["01_entry_id"] = f"PerXI{i:05d}"
        with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            w.writeheader()
            w.writerows(out)
        print(f"applied {len(proposals)} splits; rows {len(rows)} -> {len(out)}")
        for r, why in skipped:
            print(f"  [skipped] {r['03_surname']}: {why}")
        return

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["entry_id", "verdict", "surname", "given_names_before",
                    "xref_given", "xref_see_also",
                    "person_surname", "person_given", "person_description"])
        for r, tail, target, sn2, gn2 in proposals:
            w.writerow([r["01_entry_id"], "SPLIT", r["03_surname"],
                        r["04_given_names"], tail, target, sn2, gn2,
                        r["09_description"][:80]])
        for r, why in skipped:
            w.writerow([r["01_entry_id"], "MANUAL", r["03_surname"],
                        r["04_given_names"], "", "", "", "", why])

    print(f"splittable : {len(proposals)}")
    print(f"needs review: {len(skipped)}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


def given_of(row):
    return row["04_given_names"]


if __name__ == "__main__":
    main()
