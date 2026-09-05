#!/usr/bin/env python3
"""
suggest_description_fusion_splits.py
---------------------------------------
A second, distinct fusion class from the earlier 04_given_names cue
splits: here the ROW'S OWN year-parenthesis parsed correctly, but its
09_description still trails a second (or third...) entry, glued on
right after that entry's own reference run --
  "...svensk Digter. II 16 18 20 27. III 315 317-18 326 333. Attila
  (dod 453), Hunnernes Konge 433."
Marker: a roman-numeral + arabic-number reference run, terminated by a
period, immediately followed by a capitalised name-head (comma, or a
year-parenthesis, or a second capitalised word before one).

Also handles marker b): an em/en-dash inside 09_description introducing
a name that starts with the SAME LETTER as this row's own 03_surname --
the register's own "repeat this surname" dash convention, landed in the
wrong row because the entry after the dash was never split out (the
Wendell/Wendt/Westergaard/Westrup chain is the found example; note that
chain fuses at "Wendt" too, a case marker (a) does not reach because
Wendt carries no reference run of its own).

Every fragment is validated against ALL of xlsx DimPer, exactly like
suggest_cue_splits.py: fragments are split at every cue in one row (not
just the first), and a candidate is SAFE only when xlsx confirms each
fragment as a distinct, unambiguous entry.

Reporting only. Writes
data/curated/personregister_xi_description_fusion_review.tsv and
changes nothing in personregister_xi_parsed.tsv.

  python scripts/parsers/suggest_description_fusion_splits.py
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
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_description_fusion_review.tsv")

# Marker a): a reference run, then a name-head.
CUE_A = re.compile(
    r"(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+"
    r"(?=[A-ZÆØÅÖÜ][a-zæøåöäü]+(?:,|\s\(|\s[A-ZÆØÅÖÜ][a-zæøåöäü]+\s\())"
)
PARTICLES = {"von", "van", "de", "der", "di", "le", "la", "f", "g", "kaldet", "senere"}


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
        is_desc = (
            i > 0 and first[:1].islower()
            and first.rstrip(".") not in PARTICLES
        )
        if is_desc:
            break
        kept.append(u)
    return ", ".join(kept).strip(" .,")


def dash_cue(text: str, surname: str):
    """Marker b): an em/en-dash followed by a word starting with the
    same letter as this row's own surname -- the register repeating its
    own headword via dash, landed inside the description instead of
    being split into its own row."""
    if not surname:
        return None
    letter = surname[0]
    for m in re.finditer(r"[–—]\s*([A-ZÆØÅÖÜ][\wÀ-ÖØ-öø-ÿ'\-]*)", text):
        if m.group(1) and m.group(1)[0] == letter and m.group(1).lower() != "se":
            return m.end() - len(m.group(1))
    return None


def split_at_cues(text: str):
    cuts = sorted({m.end() for m in CUE_A.finditer(text)})
    cuts = [c for c in cuts if 0 < c < len(text)]
    if not cuts:
        return None
    parts, prev = [], 0
    for c in cuts + [len(text)]:
        frag = text[prev:c].strip()
        if frag:
            parts.append(frag)
        prev = c
    return parts if len(parts) > 1 else None


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]
    xl_all = [str(t) for _, t, _, _, _ in dim]
    pool = [(name_part(t), t) for t in xl_all]

    def best_two(fragment: str):
        key = norm(name_part(fragment))
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, norm(p)).ratio(), title)
             for p, title in pool),
            key=lambda t: -t[0],
        )
        return scored[:2]

    def pair_matches(frags, matches):
        scored = []
        for fi, f in enumerate(frags):
            head = f.split(",")[0].strip().lower()
            for mi, m in enumerate(matches):
                m_head = m.split(",")[0].strip().lower()
                scored.append((difflib.SequenceMatcher(None, head, m_head).ratio(), fi, mi))
        scored.sort(reverse=True)
        out, used_f, used_m = [""] * len(frags), set(), set()
        for _, fi, mi in scored:
            if fi in used_f or mi in used_m:
                continue
            out[fi] = matches[mi]
            used_f.add(fi)
            used_m.add(mi)
        return out

    out_rows = []
    n_marker_a = n_marker_b = 0

    for r in rows:
        desc = r["09_description"]
        parts = split_at_cues(desc)
        marker = "a" if parts else None

        if not parts:
            dash_pos = dash_cue(desc, r["03_surname"])
            if dash_pos is not None:
                head, tail = desc[:dash_pos].strip(), desc[dash_pos:].strip()
                if head and tail:
                    parts = [head, tail]
                    marker = "b"

        if not parts:
            continue
        if marker == "a":
            n_marker_a += 1
        else:
            n_marker_b += 1

        # Fragment 0 is NOT a name fragment: it is the continuation of
        # THIS row's own already-identified entry (name lives in
        # 03_surname/04_given_names, not in 09_description), so it
        # cannot be scored against xlsx titles at all -- doing so is
        # what produced the spurious ~0.3-0.4 "best" matches seen for
        # every head fragment. Only fragments 1.. are new entries that
        # need an xlsx match.
        tail_frags = parts[1:]
        results = []
        for frag in tail_frags:
            hits = best_two(frag)
            score, title = hits[0]
            results.append((frag, score, title))

        matches = pair_matches(tail_frags, [t for _, _, t in results])
        final = []
        for frag, m in zip(tail_frags, matches):
            score = difflib.SequenceMatcher(None, norm(name_part(frag)), norm(name_part(m))).ratio() if m else 0.0
            final.append((frag, score, m))

        # A high score only proves a fragment STARTS like its xlsx
        # match; it says nothing about text trailing after that entry's
        # own reference run (e.g. "Birger Jarl ... III 339 360. Birger
        # Persson til Finsta ..." -- a THIRD entry CUE_A did not cut,
        # because the ref-run-then-name boundary needs a fuller stop
        # than the pattern requires). Reject any tail fragment where a
        # reference run is followed by more text.
        contaminated = any(
            re.search(r"(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+\S", f)
            for f in tail_frags
        )

        titles = [m for _, _, m in final]
        safe = (
            all(s >= 0.90 for _, s, _ in final)
            and len(set(titles)) == len(titles)
            and all(t for t in titles)
            and not contaminated
        )
        # Report includes fragment 0 for context; it was never part of
        # the safety check above, which only ever saw tail_frags/final.
        final = [(parts[0], 1.0, "(row's own continuing description)")] + final

        out_rows.append({
            "entry_id": r["01_entry_id"],
            "surname": r["03_surname"],
            "marker": marker,
            "verdict": "SAFE" if safe else "MANUAL",
            "n_fragments": len(parts),
            "fragments": " || ".join(f for f, _, _ in final),
            "xlsx_matches": " || ".join(m for _, _, m in final),
            "scores": " || ".join(f"{s:.2f}" for _, s, _ in final),
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)

    safe_n = sum(1 for o in out_rows if o["verdict"] == "SAFE")
    print(f"marker a) reference-run + name-head : {n_marker_a}")
    print(f"marker b) dash + same-initial name  : {n_marker_b}")
    print(f"total flagged rows                  : {len(out_rows)}")
    print(f"  SAFE   (mechanically rewritable)  : {safe_n}")
    print(f"  MANUAL (needs a human decision)   : {len(out_rows) - safe_n}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


if __name__ == "__main__":
    main()
