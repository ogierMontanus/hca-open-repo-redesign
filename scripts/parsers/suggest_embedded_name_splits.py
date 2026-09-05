#!/usr/bin/env python3
"""
suggest_embedded_name_splits.py
-----------------------------------
A third fusion class, found by inspecting 09_description directly for
long cells and dashes (per the user's own check): a further person's
"Surname, Given (birth-death)," header buried anywhere inside a long
09_description, most often after a "— Se ogsaa: X." cross-reference
that breaks the adjacency suggest_description_fusion_splits.py's cue
requires (reference-run immediately before the name-head). Examples
found: Melchior (Moritz G. / Dorothea), Hauch, Wulff, Collin.

Marker: an embedded "Name, Given (YYYY[-YY]),"  segment that does not
start at position 0 (position 0 is this row's own, already-parsed
name). Everything from the FIRST such embedded match onward is treated
as one or more further fused entries and re-split the same way as
suggest_description_fusion_splits.py: cut at every subsequent embedded
name-header, then validate each resulting fragment against xlsx DimPer.

One additional defect this scan surfaces: a small number of rows have
their OWN 03_surname corrupted into description prose (e.g.
"Datter af Oline Thyberg") because an earlier fusion swallowed their
real headword. These cannot be fixed from 09_description alone -- they
are reported separately (needs_own_name_recovery) rather than folded
into the split logic, since inventing a surname without page-image
verification would be a fabrication, not a fix.

Reporting only. Writes
data/curated/personregister_xi_embedded_name_review.tsv and changes
nothing in personregister_xi_parsed.tsv.

  python scripts/parsers/suggest_embedded_name_splits.py
"""
import csv
import difflib
import os
import re
import unicodedata

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
XLSX_PATH = os.path.join(ROOT, "data", "raw", "HCA REPOSITORY V0.92", "PersonData-PQ-V0.92.xlsx")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_embedded_name_review.tsv")

EMBEDDED_NAME_YEAR = re.compile(
    r"[A-ZÆØÅÖÜ][a-zæøåöäü]+(?:\s\([^)]*\))?,\s"
    r"[A-ZÆØÅÖÜ][\wæøåöäü.]*(?:\s[A-ZÆØÅÖÜ]?[\wæøåöäü.]*)*\s?"
    r"\((?:ca\.\s*)?(?:d\.|død)?\s*\d{3,4}[\s–—\-]*\d{0,4}\),"
)
PARTICLES = {"von", "van", "de", "der", "di", "le", "la", "f", "g", "kaldet", "senere"}
REF_CUE = re.compile(r"(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+\S")


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", strip_diacritics(s)).strip().lower()


def name_part(s: str) -> str:
    s = re.split(r"\s*\((?:ca\.\s*)?(?:d\.|død)?\s*\d{3,4}", s)[0]
    units = [u.strip() for u in s.split(",")]
    kept = []
    for i, u in enumerate(units):
        first = u.split()[0] if u.split() else ""
        if i > 0 and first[:1].islower() and first.rstrip(".") not in PARTICLES:
            break
        kept.append(u)
    return ", ".join(kept).strip(" .,")


def surname_looks_like_prose(surname: str) -> bool:
    words = surname.split()
    return len(words) > 2 or surname[:1].islower()


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]
    pool = [(name_part(str(t)), str(t)) for _, t, _, _, _ in dim]

    def top_candidates(fragment: str, n: int = 5):
        key = norm(name_part(fragment))
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, norm(p)).ratio(), title) for p, title in pool),
            key=lambda t: -t[0],
        )
        return scored[:n]

    def pair_matches(frags, candidate_lists):
        """Each fragment brings its own shortlist of xlsx candidates
        (not a single top-1 guess, and not the whole 8900-row pool) --
        assignment is then the globally best-scoring pairing across all
        (fragment, candidate) pairs, so one fragment's bad top guess
        cannot starve another fragment of its own correct match, and a
        wrong top-1 (as happened when Hauch's first fragment's nearest
        neighbour was an unrelated Hogarth) does not shift every
        later fragment down by one."""
        scored = []
        for fi, cands in enumerate(candidate_lists):
            for score, title in cands:
                scored.append((score, fi, title))
        scored.sort(reverse=True)
        out, used_f, used_t = [""] * len(frags), set(), set()
        for score, fi, title in scored:
            if fi in used_f or title in used_t:
                continue
            out[fi] = title
            used_f.add(fi)
            used_t.add(title)
        return out

    out_rows = []
    needs_recovery = []

    for r in rows:
        desc = r["09_description"]
        cuts = [m.start() for m in EMBEDDED_NAME_YEAR.finditer(desc)]
        if not cuts:
            continue

        if surname_looks_like_prose(r["03_surname"]):
            needs_recovery.append(r["01_entry_id"])
            continue

        head = desc[: cuts[0]].strip()
        tail_bounds = cuts + [len(desc)]
        tails = []
        for i in range(len(cuts)):
            frag = desc[tail_bounds[i]: tail_bounds[i + 1]].strip()
            if frag:
                tails.append(frag)
        if not tails:
            continue

        candidate_lists = [top_candidates(f) for f in tails]
        matches = pair_matches(tails, candidate_lists)
        final = []
        for frag, m in zip(tails, matches):
            score = (
                difflib.SequenceMatcher(None, norm(name_part(frag)), norm(name_part(m))).ratio()
                if m else 0.0
            )
            final.append((frag, score, m))

        contaminated = any(REF_CUE.search(f) for f in tails)
        titles = [m for _, _, m in final]
        safe = (
            all(s >= 0.90 for _, s, _ in final)
            and len(set(titles)) == len(titles)
            and all(titles)
            and not contaminated
        )

        out_rows.append({
            "entry_id": r["01_entry_id"],
            "surname": r["03_surname"],
            "verdict": "SAFE" if safe else "MANUAL",
            "head": head,
            "n_tail_fragments": len(tails),
            "tail_fragments": " || ".join(f for f, _, _ in final),
            "xlsx_matches": " || ".join(m for _, _, m in final),
            "scores": " || ".join(f"{s:.2f}" for _, s, _ in final),
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    safe_n = sum(1 for o in out_rows if o["verdict"] == "SAFE")
    print(f"rows with an embedded name+year in 09_description: {len(out_rows) + len(needs_recovery)}")
    print(f"  splittable (own surname intact)   : {len(out_rows)}")
    print(f"    SAFE   (mechanically rewritable) : {safe_n}")
    print(f"    MANUAL (needs a human decision)  : {len(out_rows) - safe_n}")
    print(f"  needs_own_name_recovery (surname itself is corrupted prose): {len(needs_recovery)}")
    for eid in needs_recovery:
        print(f"    {eid}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


if __name__ == "__main__":
    main()
