#!/usr/bin/env python3
"""
apply_person_emendations.py
-------------------------------
Reads data/curated/person_emendations.tsv and reports, or emits, the
post-editorial corrections layered on top of the printed register.

An emendation is NOT an edit of master1. The register is the source; a
correction is a separate, sourced claim laid over it at display time --
see docs/data-model/person-editorial-emendations.md for why (page
references point at what the book actually prints, corrections can be
wrong, and 01_entry_id renumbers).

This script therefore has no --apply-to-master mode, and never writes
personregister_xi_parsed.tsv. It:

  * validates every emendation against master1 (default);
  * writes a merged view for consumers (--emit);
  * writes a RESOLVED copy of master1 for the enrichment chain
    (--emit-resolved), where corrections are applied and the original is
    preserved alongside.

Validation is the point. Each row carries the value it expects to find in
`original`; when that no longer matches, the entry underneath the
emendation has changed and the correction must be re-checked rather than
applied blindly.

Two rules from docs/data-model/person-editorial-emendations.md are
implemented here rather than left to the consumer:

  * An emended SURNAME moves the entry in the alphabet -- Oesterling sits
    among the Ø/Ö names, Osterley lands 3,000 rows earlier. So the resolved
    view also carries a krydshenvisning at the printed position, or a
    reader looking up the name the book prints finds nothing. Its wording
    follows the confidence: "se:" only when certain, otherwise
    "sandsynligvis/muligvis hentydning til:".
  * master2 reads the resolved form (decided 2026-09-03): "Oesterling" has
    no forename and no years, so the chain can derive neither gender nor
    lifespan; "Osterley, Carl (1805-1891)" gives it all three.

  python scripts/parsers/apply_person_emendations.py
  python scripts/parsers/apply_person_emendations.py --emit
  python scripts/parsers/apply_person_emendations.py --emit-resolved
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MASTER1 = os.path.join(ROOT, "data", "curated", "personregister_xi_review_full.tsv")
EMENDATIONS = os.path.join(ROOT, "data", "curated", "person_emendations.tsv")
OUT_JSON = os.path.join(ROOT, "data", "normalized", "person_emendations.json")
OUT_RESOLVED = os.path.join(ROOT, "data", "normalized",
                            "personregister_xi_resolved.tsv")

# Wording of the generated cross-reference, by confidence. "se:" is the
# register's own word for an identity that is not in dispute; using it for
# a probable identification would claim more than we know.
XREF_WORDING = {
    "certain": "se:",
    "probable": "sandsynligvis hentydning til:",
    "proposed": "muligvis hentydning til:",
}

FIELD_MAP = {
    "surname": "03_surname",
    "given_names": "04_given_names",
    "birth_year": "06_birth_year",
    "death_year": "07_death_year",
    "description": "09_description",
}
CONFIDENCE = ("certain", "probable", "proposed")


def ref_key(surname, refs):
    return (surname.strip(), ";".join(sorted(x for x in refs.split(";") if x)))


def load_master1():
    with open(MASTER1, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    index = {}
    for r in rows:
        index.setdefault(ref_key(r["03_surname"], r["11_references_parsed"]), []).append(r)
    return rows, index


def emit_resolved(master_rows, ok):
    """Write master1 with corrections applied, originals kept alongside.

    Adds three columns rather than overwriting anything:
      14_emended_fields   which fields were corrected, ";"-separated
      15_original_values  their pre-correction values, "field=value;…"
      16_emendation_source  "HCAC, 2026-09-03, probable"

    A corrected SURNAME also yields a krydshenvisning row at the entry's
    printed alphabetical position, so the name the book prints stays
    findable. See the module docstring.
    """
    by_key = {}
    for e, row in ok:
        by_key.setdefault(id(row), []).append(e)

    extra_cols = ["14_emended_fields", "15_original_values", "16_emendation_source"]
    fieldnames = list(master_rows[0].keys()) + extra_cols

    out, n_emended, n_xref = [], 0, 0
    for row in master_rows:
        ems = by_key.get(id(row))
        if not ems:
            out.append({**row, **{c: "" for c in extra_cols}})
            continue

        resolved = dict(row)
        originals, fields, stamps = [], [], []
        surname_change = None
        for e in ems:
            col = FIELD_MAP[e["field"]]
            originals.append(f"{e['field']}={row[col]}")
            fields.append(e["field"])
            resolved[col] = e["emended"]
            stamps.append(f"{e['source']}, {e['date']}, {e['confidence']}")
            if e["field"] == "surname":
                surname_change = e

        resolved["05_sort_key"] = (
            f"{resolved['03_surname']}, {resolved['04_given_names']}"
        ).strip().rstrip(",")
        resolved["14_emended_fields"] = ";".join(fields)
        resolved["15_original_values"] = ";".join(originals)
        resolved["16_emendation_source"] = " | ".join(sorted(set(stamps)))
        out.append(resolved)
        n_emended += 1

        if surname_change:
            target = f"{resolved['03_surname']}, {resolved['04_given_names']}".strip().rstrip(",")
            wording = XREF_WORDING[surname_change["confidence"]]
            desc = f"{wording} {target}"
            printed = row["09_description"].strip().rstrip(".")
            if printed:
                # A target ending in an initial ("Hasebroek, J. P.") already
                # carries its own period; don't double it.
                sep = "" if desc.endswith(".") else "."
                desc += f'{sep} Registret: »{printed}«'
            desc += f". Rettet efter {surname_change['source']}, {surname_change['date']}."

            xref = {c: "" for c in fieldnames}
            xref.update({
                "01_entry_id": f"{row['01_entry_id']}x",
                "02_entry_type": "krydshenvisning",
                "03_surname": row["03_surname"],
                "05_sort_key": row["03_surname"],
                "09_description": desc,
                "12_see_also": target,
                "13_raw_text": row["13_raw_text"],
                "16_emendation_source": (
                    f"{surname_change['source']}, {surname_change['date']}, "
                    f"{surname_change['confidence']}"),
            })
            out.append(xref)
            n_xref += 1

    os.makedirs(os.path.dirname(OUT_RESOLVED), exist_ok=True)
    with open(OUT_RESOLVED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"skrev {os.path.relpath(OUT_RESOLVED, ROOT)} "
          f"({len(out)} rækker: {len(master_rows)} + {n_xref} krydshenvisning)")
    print(f"  poster med rettelser : {n_emended}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true",
                    help="write data/normalized/person_emendations.json for consumers")
    ap.add_argument("--emit-resolved", action="store_true",
                    help="write data/normalized/personregister_xi_resolved.tsv "
                         "(corrections applied, originals preserved) for the "
                         "enrichment chain")
    args = ap.parse_args()

    if not os.path.exists(EMENDATIONS):
        sys.exit(f"missing {os.path.relpath(EMENDATIONS, ROOT)}")

    master_rows, index = load_master1()
    with open(EMENDATIONS, encoding="utf-8") as f:
        emendations = [r for r in csv.DictReader(f, delimiter="\t")
                       if r.get("match_surname", "").strip()]

    ok, problems = [], []
    for e in emendations:
        where = f"{e['match_surname']} [{e['match_refs']}] {e['field']}"

        if e["field"] not in FIELD_MAP:
            problems.append((where, f"ukendt felt {e['field']!r}"))
            continue
        if e["confidence"] not in CONFIDENCE:
            problems.append((where, f"ukendt confidence {e['confidence']!r}"))
            continue
        if not e.get("source", "").strip():
            problems.append((where, "mangler kilde"))
            continue
        if not e.get("notes", "").strip():
            problems.append((where, "mangler begrundelse"))
            continue

        targets = index.get(ref_key(e["match_surname"], e["match_refs"]), [])
        if not targets:
            problems.append((where, "ingen post i master1 med det efternavn + henvisningssignatur"))
            continue
        if len(targets) > 1:
            problems.append((where, f"{len(targets)} poster matcher — nøglen er ikke entydig"))
            continue

        row = targets[0]
        actual = row[FIELD_MAP[e["field"]]].strip()
        expected = e["original"].strip()
        if actual != expected:
            problems.append((
                where,
                f"master1 har {actual!r}, rettelsen forventer {expected!r} "
                "— posten er ændret, genvurder rettelsen"))
            continue

        ok.append((e, row))

    print(f"emendationer i alt : {len(emendations)}")
    print(f"  validerede       : {len(ok)}")
    print(f"  problemer        : {len(problems)}")
    for where, why in problems:
        print(f"    [!] {where}: {why}")

    if not (args.emit or args.emit_resolved):
        for e, row in ok:
            print(f"    {e['match_surname']} {e['field']}: "
                  f"{e['original']!r} -> {e['emended']!r}  "
                  f"({e['source']}, {e['date']}, {e['confidence']})")
        return 1 if problems else 0

    if problems:
        sys.exit("nægter at skrive output med uløste problemer ovenfor")

    if args.emit_resolved:
        return emit_resolved(master_rows, ok)

    merged = {}
    for e, row in ok:
        key = ref_key(e["match_surname"], e["match_refs"])
        entry = merged.setdefault("|".join(key), {
            "match_surname": key[0],
            "match_refs": key[1],
            "original": {},
            "emended": {},
            "sources": [],
        })
        entry["original"][e["field"]] = e["original"]
        entry["emended"][e["field"]] = e["emended"]
        stamp = {
            "field": e["field"],
            "source": e["source"],
            "source_detail": e.get("source_detail", ""),
            "date": e["date"],
            "confidence": e["confidence"],
            "notes": e["notes"],
        }
        entry["sources"].append(stamp)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(list(merged.values()), f, ensure_ascii=False, indent=2)
    print(f"skrev {os.path.relpath(OUT_JSON, ROOT)} ({len(merged)} poster)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
