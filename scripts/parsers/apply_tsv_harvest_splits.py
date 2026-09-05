#!/usr/bin/env python3
"""
apply_tsv_harvest_splits.py
-------------------------------
Applies the segmentation harvested by harvest_segmentation_from_tsv.py.

Each of our fused rows is replaced by N rows, one per person the
reference source lists -- taking name, years, description and page
references from the reference, which segments them correctly.

Our own row keeps its identity for the FIRST person (so nothing that
already links to that entry id breaks more than the renumbering
already does); the remaining people become new standardposts.

The reference's year format ("1822-1902", en-dash) and page format
("IX 312") are converted to this project's conventions
(06_birth_year/07_death_year, and "VOL:PAGE;..." in
11_references_parsed).

Run from the repo root, AFTER harvest_segmentation_from_tsv.py:
  python scripts/parsers/apply_tsv_harvest_splits.py
"""
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
HARVEST_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_tsv_harvest_review.tsv")

NAME_YEARS = re.compile(
    r"^(?P<name>.*?)\s*\(\s*(?:(?:d\.|død)\s*(?P<dy>\d{3,4})"
    r"|(?:ca\.\s*)?(?P<b>\d{3,4})\s*[–—-]\s*(?P<d>\d{3,4}|\?)"
    r"|(?P<b_only>\d{3,4}))\s*(?P<fchr>f\.\s*Chr\.)?\s*\)\s*$"
)


def parse_name(name_field: str):
    """'Aabye, Johan Peter (1818-1880)' ->
       ('Aabye', 'Johan Peter', '1818', '1880', '')"""
    birth = death = note = ""
    m = NAME_YEARS.match(name_field.strip())
    core = name_field.strip()
    if m:
        core = m.group("name").strip()
        if m.group("dy"):
            death = m.group("dy")
        elif m.group("b_only"):
            birth = m.group("b_only")
        else:
            birth = m.group("b") or ""
            d = m.group("d") or ""
            death = "" if d == "?" else d
        if m.group("fchr"):
            note = "f. Kr. (BC)"
    if "," in core:
        surname, given = core.split(",", 1)
        return surname.strip(), given.strip(), birth, death, note
    return core, "", birth, death, note


def parse_refs(refs_field: str):
    """'IX 312; X 55' -> ('IX 312. X 55.', 'IX:312;X:55')"""
    pairs = [p.strip() for p in refs_field.split(";") if p.strip()]
    raw_parts, parsed = [], []
    for p in pairs:
        bits = p.split()
        if len(bits) != 2:
            continue
        vol, page = bits
        raw_parts.append(f"{vol} {page}")
        # A page can itself be a range, "104-105" / "104–105".
        page = page.replace("–", "-").replace("—", "-")
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
    return (" ".join(raw_parts) + "." if raw_parts else ""), ";".join(parsed)


def main():
    with open(HARVEST_TSV, encoding="utf-8") as f:
        harvest = list(csv.DictReader(f, delimiter="\t"))

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    by_id = {h["entry_id"]: h for h in harvest}
    out, n_new = [], 0

    for row in rows:
        spec = by_id.get(row["01_entry_id"])
        if not spec:
            out.append(row)
            continue

        names = spec["reference_names"].split(" || ")
        descs = spec["reference_descriptions"].split(" || ")
        refs = spec["reference_refs"].split(" || ")

        for i, (name, desc, ref) in enumerate(zip(names, descs, refs)):
            surname, given, birth, death, note = parse_name(name)
            refs_raw, refs_parsed = parse_refs(ref)

            if i == 0:
                new = dict(row)
            else:
                new = {k: "" for k in fieldnames}
                new["02_entry_type"] = "standardpost"
                n_new += 1

            new.update({
                "03_surname": surname,
                "04_given_names": given,
                "05_sort_key": f"{surname}, {given}".strip().rstrip(","),
                "06_birth_year": birth,
                "07_death_year": death,
                "08_year_note": note or new.get("08_year_note", ""),
                "09_description": desc,
                "10_references_raw": refs_raw,
                "11_references_parsed": refs_parsed,
                "13_raw_text": f"{name}, {desc} {refs_raw}".strip(),
            })
            out.append(new)

    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"applied {len(harvest)} harvested segmentations -> {n_new} new entries")
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
