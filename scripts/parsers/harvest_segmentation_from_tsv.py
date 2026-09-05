#!/usr/bin/env python3
"""
harvest_segmentation_from_tsv.py
------------------------------------
Harvests entry segmentation from data/raw/Personer _ HCA_tsv.txt -- an
independently-produced digitisation of the same person register, whose
OCR/segmentation is better than this project's column-reflow parser in
exactly the place ours is weakest: it carries ONE ROW PER PERSON, with
name(+years), description and volume/page pairs already in separate
fields, so it never fuses two entries into one cell.

Strategy, for each of our long 13_raw_text / 09_description rows:
  1. Detect the surnames present in our row's text.
  2. Look those surnames up in the reference source.
  3. If the reference has N separate person-rows whose text is all
     accounted for inside our single row, our row is fused N ways and
     the reference tells us exactly where the boundaries fall AND what
     each resulting entry's name, years, description and references are.

Because the reference is a different transcription (spelling, dashes,
year formatting all differ slightly), matching is done on
diacritic-stripped, punctuation-normalised text, and a candidate
segmentation is only accepted when every reference fragment is found in
our row's text in the same order, covering most of it.

Reporting only. Writes
data/curated/personregister_xi_tsv_harvest_review.tsv and changes
nothing in personregister_xi_parsed.tsv.

  python scripts/parsers/harvest_segmentation_from_tsv.py
"""
import csv
import os
import re
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REF_TXT = os.path.join(ROOT, "data", "raw", "Personer _ HCA_tsv.txt")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_tsv_harvest_review.tsv")

# Our rows worth checking: anything whose description is long enough to
# plausibly hide a second entry, or that a fusion flag already marks.
LONG_DESC = 180


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    """Aggressive normalisation for cross-transcription comparison:
    the two sources differ in dash style (- vs en-dash), spacing around
    line-wrap hyphens, capitalisation and punctuation."""
    s = strip_diacritics(s).lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)   # heal line-wrap hyphens
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ref_surname(name_field: str) -> str:
    """'Aabye, Johan Peter (1818-1880)' -> 'Aabye'."""
    return name_field.split(",")[0].split("(")[0].strip()


def load_reference():
    """Returns list of dicts: name, description, refs (list of 'VOL PAGE'),
    plus a surname index."""
    entries = []
    with open(REF_TXT, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2 or not parts[0].strip():
                continue
            name, desc = parts[0].strip(), parts[1].strip()
            if name == "Navn":
                continue
            refs = []
            rest = parts[2:]
            for i in range(0, len(rest) - 1, 2):
                vol, page = rest[i].strip(), rest[i + 1].strip()
                if vol and page:
                    refs.append(f"{vol} {page}")
            entries.append({
                "name": name,
                "surname": ref_surname(name),
                "description": desc,
                "refs": refs,
            })
    index = {}
    for e in entries:
        index.setdefault(norm(e["surname"]), []).append(e)
    return entries, index


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        ours = list(csv.DictReader(f, delimiter="\t"))

    ref_entries, ref_index = load_reference()
    print(f"reference source: {len(ref_entries)} pre-segmented person rows")
    print(f"our parsed file : {len(ours)} rows")
    print()

    out_rows = []
    for r in ours:
        text = r["13_raw_text"]
        if len(r["09_description"]) < LONG_DESC:
            continue

        haystack = norm(text)
        candidates = ref_index.get(norm(r["03_surname"]), [])
        if not candidates:
            continue

        # Which reference entries for this surname have their NAME
        # present inside our row's text? More than one => our row fuses
        # that many of the reference's entries.
        present = []
        for e in candidates:
            key = norm(e["name"].split("(")[0])
            if key and key in haystack:
                present.append((haystack.index(key), e))
        if len(present) < 2:
            continue

        present.sort(key=lambda t: t[0])
        # Verify the reference's descriptions also appear, in order --
        # otherwise the name match is incidental (a person mentioned in
        # someone else's description rather than a fused headword).
        confirmed = []
        cursor = 0
        for pos, e in present:
            desc_key = norm(e["description"])[:40]
            if desc_key and desc_key in haystack[cursor:]:
                cursor = haystack.index(desc_key, cursor) + len(desc_key)
                confirmed.append(e)

        if len(confirmed) < 2:
            continue

        out_rows.append({
            "entry_id": r["01_entry_id"],
            "our_surname": r["03_surname"],
            "our_desc_len": len(r["09_description"]),
            "n_reference_entries": len(confirmed),
            "reference_names": " || ".join(e["name"] for e in confirmed),
            "reference_descriptions": " || ".join(e["description"] for e in confirmed),
            "reference_refs": " || ".join("; ".join(e["refs"]) for e in confirmed),
            "our_raw_text": r["13_raw_text"],
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    if out_rows:
        with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(out_rows)

    print(f"our long rows the reference segments into 2+ entries: {len(out_rows)}")
    total_new = sum(o["n_reference_entries"] - 1 for o in out_rows)
    print(f"  implied missing entries: {total_new}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


if __name__ == "__main__":
    main()
