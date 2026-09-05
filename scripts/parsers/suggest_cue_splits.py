#!/usr/bin/env python3
"""
suggest_cue_splits.py
-----------------------
Finds kun_min rows whose 04_given_names still carries a fused *second*
entry, splits them at the fusion cue, then validates each resulting
fragment against xlsx DimPer -- which segments entries reliably, having
been keyed by hand rather than derived from column-reflow OCR.

Fusion cues (all mark the END of one entry's text, so the split point is
what FOLLOWS them):
  - a reference run  "III 375."  / "VIII 89-91 101."  -- roman volume
    number + arabic column numbers, terminated by a period;
  - a cross-reference "..., se: Target."  -- the target ends the entry.

Both fragments are matched against ALL of DimPer, not just the kun_xlsx
leftovers: the fused tail is the *next* register entry, which xlsx
normally carries as an ordinary row, so restricting the pool to kun_xlsx
misses the very rows that confirm a split. Comparison uses each
fragment's NAME portion only (text before the year-parenthesis, minus
the trailing reference run), because xlsx titles hold name + years while
our fragments trail long descriptions and column references -- scoring
whole strings would drown the part that actually identifies the person.

Classification:
  SAFE   -- BOTH fragments match a distinct xlsx entry at >= 0.90, i.e.
            xlsx independently confirms an entry boundary exactly where
            the cue put one: the rewrite can be applied mechanically.
  MANUAL -- everything else (a fragment xlsx does not know, or two xlsx
            candidates too close to separate).

Reporting only; writes
data/curated/personregister_xi_cue_split_review.tsv and rewrites
nothing.

  python scripts/parsers/suggest_cue_splits.py
"""
import csv
import difflib
import os
import re
import unicodedata

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REVIEW_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_vs_xlsx_review.tsv")
XLSX_PATH = os.path.join(ROOT, "data", "raw", "HCA REPOSITORY V0.92", "PersonData-PQ-V0.92.xlsx")
OUT_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_cue_split_review.tsv")

# A reference run ending an entry, e.g. "III 375." or "VIII 89- 91 101."
# followed by the next entry's capitalised name-head.
REF_CUE = re.compile(
    r"(?<=[.\s])(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+(?=[A-ZÆØÅÖÜ])"
)
# A "se:"-style cross-reference ending an entry.
SEE_CUE = re.compile(
    r",\s*se(?:\s+denne|:)?\s*[^.]{0,60}?\.\s+(?=[A-ZÆØÅÖÜ])", re.IGNORECASE
)


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", strip_diacritics(s)).strip().lower()


def xl_surname(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(title)).split(",")[0].strip()


REF_RUN = re.compile(r"\s*(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.?\s*$")


def name_part(s: str) -> str:
    """The identifying head of an entry: everything before the year
    parenthesis, with any trailing reference run removed. xlsx titles
    are 'Surname, Given (birth-death)', so this is what can fairly be
    compared against them."""
    s = re.split(r"\s*\((?:ca\.\s*)?(?:d\.|død)?\s*\d{3,4}", s)[0]
    s = re.split(r",\s*se\b", s, flags=re.IGNORECASE)[0]
    prev = None
    while prev != s:
        prev = s
        s = REF_RUN.sub("", s).strip()
    # Descriptions run on after the name. Cut at the first unit that
    # reads as description rather than a name element -- a lowercase
    # word that is not a name particle (von/van/de/f./g. …). This keeps
    # "Berry, Grevinde" and "Hesse, Wilhelmine Charlotte, f. Neuendorff"
    # whole while dropping "…, dansk Vicekonsul i Bayonne".
    units = [u.strip() for u in s.split(",")]
    kept = []
    for i, u in enumerate(units):
        first = u.split()[0] if u.split() else ""
        is_desc = (
            i > 0
            and first[:1].islower()
            and first.rstrip(".") not in {"von", "van", "de", "der", "di", "le", "la", "f", "g", "kaldet", "senere"}
        )
        if is_desc:
            break
        kept.append(u)
    return ", ".join(kept).strip(" .,")


def split_all(text: str):
    """Split at EVERY cue, not just the last one: a row can carry three
    fused entries (e.g. Clavaud + Clemens III + Clemens VII), and one
    pass would leave the middle one buried in the head."""
    cuts = sorted({m.end() for pat in (REF_CUE, SEE_CUE) for m in pat.finditer(text)})
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
    with open(REVIEW_TSV, encoding="utf-8") as f:
        kun_min = [r for r in csv.DictReader(f, delimiter="\t") if r["status"] == "kun_min"]
    with open(REVIEW_TSV, encoding="utf-8") as f:
        kun_xlsx = [r for r in csv.DictReader(f, delimiter="\t") if r["status"] == "kun_xlsx"]

    with open(PARSED_TSV, encoding="utf-8") as f:
        parsed = {r["01_entry_id"]: r for r in csv.DictReader(f, delimiter="\t")}

    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
    dim = list(wb["DimPer"].iter_rows(values_only=True))[1:]
    xl_all = [(str(t), d or "", b, dt) for _, t, d, b, dt in dim]

    # Search pool: every DimPer title, plus a flag for whether that title
    # is one of the kun_xlsx leftovers (useful context in the report).
    kun_xlsx_labels = {
        norm(f"{r['xlsx_surname']}, {r['xlsx_given_names']}".strip().rstrip(","))
        for r in kun_xlsx
    }
    pool = [(name_part(t), t) for t, _, _, _ in xl_all]

    def best_two(fragment: str):
        key = norm(name_part(fragment))
        scored = sorted(
            ((difflib.SequenceMatcher(None, key, norm(p)).ratio(), title)
             for p, title in pool),
            key=lambda t: -t[0],
        )
        return scored[:2]

    out = []
    for r in kun_min:
        row = parsed.get(r["min_entry_id"])
        if not row:
            continue
        parts = split_all(row["04_given_names"])
        if not parts:
            continue

        # Only the first fragment inherits this row's surname; every
        # later one carries its own name-head.
        results = []
        for i, frag in enumerate(parts):
            probe = f"{row['03_surname']}, {frag}" if i == 0 else frag
            hits = best_two(probe)
            score, title = hits[0]
            second = hits[1][0] if len(hits) > 1 else 0.0
            results.append((frag, score, title, second))

        titles = [t for _, _, t, _ in results]
        # A high score only proves the fragment STARTS like its xlsx
        # match; it says nothing about text trailing after the entry's
        # own reference run. Clavaud is the case in point: its first
        # fragment still ends "... VII 87. demens III (dod 1191), Pave
        # 1187. I 402.", a whole further entry that no cue caught,
        # because OCR lowercased "Clemens" and REF_CUE only splits
        # before a capital. Treat any fragment whose reference run is
        # followed by more prose as still fused.
        contaminated = [
            f for f, _, _, _ in results
            if re.search(r"(?:I{1,3}|IV|VI{0,3}|IX|X)\s[\d\s\-]*\d\.\s+\S", f)
        ]
        safe = (
            all(s >= 0.90 and s - sec >= 0.03 for _, s, _, sec in results)
            and len(set(titles)) == len(titles)
            and not contaminated
        )
        out.append({
            "min_entry_id": r["min_entry_id"],
            "verdict": "SAFE" if safe else "MANUAL",
            "surname": row["03_surname"],
            "n_fragments": len(parts),
            "fragments": " || ".join(f for f, _, _, _ in results),
            "xlsx_matches": " || ".join(t for _, _, t, _ in results),
            "scores": " || ".join(f"{s:.2f}" for _, s, _, _ in results),
            "any_in_kun_xlsx": "yes" if any(
                norm(name_part(t)) in kun_xlsx_labels for t in titles
            ) else "no",
        })

    os.makedirs(os.path.dirname(OUT_TSV), exist_ok=True)
    with open(OUT_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(out)

    safe_n = sum(1 for o in out if o["verdict"] == "SAFE")
    print(f"kun_min rows with a fusion cue : {len(out)}")
    print(f"  SAFE   (mechanically rewritable): {safe_n}")
    print(f"  MANUAL (needs a human decision) : {len(out) - safe_n}")
    print(f"wrote {os.path.relpath(OUT_TSV, ROOT)}")


if __name__ == "__main__":
    main()
