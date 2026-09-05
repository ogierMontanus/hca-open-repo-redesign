#!/usr/bin/env python3
"""
apply_description_fusion_splits.py
--------------------------------------
Applies the SAFE rows from suggest_description_fusion_splits.py.

Unlike the earlier 04_given_names cue-split class, here the row's OWN
03/04/06/07/10/11 fields are already correct (its year-parenthesis
parsed fine); only 09_description trails one or more further entries
after its own reference run. So: the original row is kept as-is except
09_description is trimmed back to fragment 0, and each later fragment
becomes an entirely new standardpost built from its own text.

Run from the repo root, AFTER suggest_description_fusion_splits.py:
  python scripts/parsers/apply_description_fusion_splits.py
"""
import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REVIEW_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_description_fusion_review.tsv")

XL_YEARS = re.compile(
    r"\((?:ca\.\s*)?(?:(?P<d_only>(?:d\.|død)\s*(?P<dy>\d{3,4}))"
    r"|(?P<b>\d{3,4})\s*[–—-]\s*(?:efter\s*)?(?P<d>\d{3,4}))\)"
)
REF_RUN = re.compile(r"((?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d)\.\s*$")
PARTICLES = {"von", "van", "de", "der", "di", "le", "la", "f", "g", "kaldet", "senere"}


def split_name_desc(frag: str):
    text = frag.strip()
    refs_raw = ""
    m = REF_RUN.search(text)
    if m:
        refs_raw = text[m.start():].strip()
        text = text[: m.start()].strip().rstrip(",")

    ym = re.search(r"\((?:ca\.\s*)?(?:d\.|død)?\s*\d{2,4}", text)
    if ym:
        close = text.find(")", ym.start())
        cut = close + 1 if close != -1 else ym.start()
        return text[:cut].strip().rstrip(","), text[cut:].strip().lstrip(",").strip(), refs_raw

    units = [u.strip() for u in text.split(",")]
    name_units = []
    for i, u in enumerate(units):
        first = u.split()[0] if u.split() else ""
        if i > 0 and first[:1].islower() and first.rstrip(".") not in PARTICLES:
            break
        name_units.append(u)
    name_text = ", ".join(name_units).strip().rstrip(",")
    desc = ", ".join(units[len(name_units):]).strip(" ,")
    return name_text, desc, refs_raw


def parse_refs(raw: str):
    out = []
    for m in re.finditer(r"\b(I{1,3}|IV|VI{0,3}|IX|X)\s([\d\s\-]*\d)", raw):
        vol, nums = m.group(1), m.group(2)
        for nm in re.finditer(r"(\d+)(?:\s?-\s?(\d+))?", nums):
            a, b = nm.group(1), nm.group(2)
            if b is None:
                out.append(f"{vol}:{a}")
            else:
                lo, hi = int(a), int(b)
                if hi < lo:
                    hi = int(str(lo)[: len(str(lo)) - len(b)] + b)
                out.extend(f"{vol}:{n}" for n in range(lo, hi + 1))
    return ";".join(out)


def main():
    with open(REVIEW_TSV, encoding="utf-8") as f:
        safe = [r for r in csv.DictReader(f, delimiter="\t") if r["verdict"] == "SAFE"]

    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    by_id = {r["entry_id"]: r for r in safe}
    out, n_new = [], 0

    for row in rows:
        spec = by_id.get(row["01_entry_id"])
        if not spec:
            out.append(row)
            continue

        frags = [f.strip() for f in spec["fragments"].split(" || ") if f.strip()]
        matches = [m.strip() for m in spec["xlsx_matches"].split(" || ") if m.strip()]
        # matches[0] is the placeholder "(row's own continuing
        # description)" -- drop it, it is not an xlsx title.
        matches = matches[1:]

        row = dict(row)
        row["09_description"] = frags[0]
        out.append(row)

        for frag, xl_title in zip(frags[1:], matches):
            name_text, desc, refs_raw = split_name_desc(frag)
            if "," in name_text:
                surname, given = name_text.split(",", 1)
                surname, given = surname.strip(), given.strip()
            else:
                # No comma: a single-word/epithet name like "Apollonio
                # Greco (13. Aarhundrede)" or "Rafael (Raffaello Santi)
                # (1483-1520)". The surname is only the text before the
                # FIRST parenthesis (never a parenthesis itself, which
                # the main parser's own convention -- and this project's
                # own regression test -- both require); anything from
                # that parenthesis onward is a given-names/epithet field,
                # same as parse_personregister_xi.py's no-comma branch.
                paren = name_text.find("(")
                if paren == -1:
                    surname, given = name_text.strip(), ""
                else:
                    surname, given = name_text[:paren].strip(), name_text[paren:].strip()

            birth = death = ""
            ym = XL_YEARS.search(xl_title)
            if ym:
                if ym.group("d_only"):
                    death = ym.group("dy")
                else:
                    birth, death = ym.group("b"), ym.group("d")

            new = {k: "" for k in fieldnames}
            new.update({
                "02_entry_type": "standardpost",
                "03_surname": surname,
                "04_given_names": given,
                "05_sort_key": f"{surname}, {given}".strip().rstrip(","),
                "06_birth_year": birth,
                "07_death_year": death,
                "09_description": desc,
                "10_references_raw": refs_raw,
                "11_references_parsed": parse_refs(refs_raw),
                "13_raw_text": frag,
            })
            out.append(new)
            n_new += 1

    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"applied {len(safe)} SAFE description-fusion splits -> {n_new} new entries")
    print(f"rows: {len(rows)} -> {len(out)}")


if __name__ == "__main__":
    main()
