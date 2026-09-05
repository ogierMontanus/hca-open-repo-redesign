#!/usr/bin/env python3
"""
link_dash_subentries_to_parents.py
--------------------------------------
The register expresses a relative with no name of their own as a dash
sub-entry under the person before them ("- Hans Datter", "- Hendes
Soester og Soesterdatter"). Our rows carry the dash literally in
03_surname, so alphabetical placement sorted them all to the very top of
the file, severing them from the person they belong to -- leaving 13
rows that say only "his daughter" with no indication of whose.

The parent is recovered from data/raw/Personer _ HCA_tsv.txt, which
preserves the register's printed order: the row immediately above the
dash entry is its parent. Rows are matched on their page references
(transcription-stable, unlike name text), comparing the SET of
volume:page pairs after expanding the reference's ranges ("VII:176-177"
-> VII:176, VII:177) to match our already-expanded form.

Each resolved row gets:
  - the parent named in 09_description, so the row is self-explanatory;
  - 12_see_also pointing at the parent, so the link is machine-readable
    the same way the register's own cross-references are.

  python scripts/parsers/link_dash_subentries_to_parents.py
"""
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REF_TXT = os.path.join(ROOT, "data", "raw", "Personer _ HCA_tsv.txt")


def expand_refs(refs):
    """{'VII:176-177'} -> {'VII:176', 'VII:177'}, matching our format."""
    out = set()
    for item in refs:
        if ":" not in item:
            continue
        vol, page = item.split(":", 1)
        page = page.replace("–", "-").replace("—", "-")
        if "-" in page:
            a, b = page.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if hi < lo:
                    hi = int(str(lo)[: len(str(lo)) - len(b)] + b)
                out.update(f"{vol}:{n}" for n in range(lo, hi + 1))
                continue
        if page.isdigit():
            out.add(f"{vol}:{page}")
    return out


def strip_years(name):
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def load_reference():
    rows = []
    with open(REF_TXT, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2 or not p[0].strip() or p[0] == "Navn":
                continue
            refs, rest = [], p[2:]
            for i in range(0, len(rest) - 1, 2):
                if rest[i].strip() and rest[i + 1].strip():
                    refs.append(f"{rest[i].strip()}:{rest[i + 1].strip()}")
            rows.append({"name": p[0].strip(), "desc": p[1].strip(), "refs": refs})
    return rows


def main():
    ref_rows = load_reference()
    dash_entries = [
        (i, r) for i, r in enumerate(ref_rows)
        if r["name"].lstrip().startswith(("-", "–", "—")) and r["refs"]
    ]

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    linked, unresolved = 0, []
    for r in rows:
        if not r["03_surname"].lstrip().startswith("-"):
            continue
        ours = set(x for x in r["11_references_parsed"].split(";") if x)
        match = None
        for i, d in dash_entries:
            if expand_refs(d["refs"]) == ours:
                match = (i, d)
                break
        if not match:
            unresolved.append(r["01_entry_id"])
            continue

        i, _ = match
        parent = ref_rows[i - 1]
        parent_name = strip_years(parent["name"])

        relation = r["03_surname"].lstrip("- ").strip()
        note = f"{relation} af {parent_name}."
        r["09_description"] = (
            f"{note} {r['09_description']}".strip() if r["09_description"] else note
        )
        r["12_see_also"] = parent_name
        r["13_raw_text"] = (
            f"{r['03_surname']}, {r['09_description']} {r['10_references_raw']}".strip()
        )
        linked += 1

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    print(f"linked {linked} dash sub-entries to their parent")
    if unresolved:
        print(f"unresolved: {unresolved}")


if __name__ == "__main__":
    main()
