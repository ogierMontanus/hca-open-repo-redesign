#!/usr/bin/env python3
"""
suggest_row_corrections.py — find fused and duplicated register rows, and
propose the correction rather than making it.

Two opposite defects, one pass, because they are the same mistake in either
direction: a row that should be two, and two rows that should be one.

    SPLIT   a citation run sits in a column that cannot hold one, and the
            next entry's name-head hangs on after it
    MERGE   two rows cite exactly the same pages under near-identical names

Emits two files, never the master:

    data/review/row_corrections_review.csv        every finding, with tier,
                                                  evidence and what is proposed
    data/parsed/personregister_xi_parsed.proposed.tsv
                                                  the register with the safe
                                                  corrections applied, to diff
                                                  against the real one

Why tiers
---------
"Fused" is not one problem, and the useful thing is knowing which part of a
finding is mechanical and which needs a person:

  **1 · recover citations** — safe, mechanical, additive. A citation inside
        `09_description` is in the wrong column by definition, and there is
        nothing to decide: it is written to a new `14_recovered_references`
        column, never over `11_references_parsed`. ~192 page numbers across
        61 rows, which the reference merge never saw because they were never
        parsed.

  **2 · trim the description** — safe. Everything from the hanging name-head
        onward belongs to a different entry and is removed from this one's
        description. Independently checkable against the raw text.

  **3 · split out a new row** — only where the hanging entry does not already
        exist. Measured: of 61 description fusions, **48 tails are already
        rows in their own right** — splitting those would manufacture
        duplicates, which is worse than the fusion. Only 13 are genuinely
        lost entries. Proposed, not applied: the new row needs an id, which
        is `scripts/index_maintenance/` 's job.

  **4 · merge** — never applied. Removing a row renumbers `01_entry_id` and
        rewrites citations; it is the most destructive edit in the project
        and the one most often wrong. Reported with its evidence.

The rules
---------
Carried over from `build_review_workbook.py`, which is where they were first
written, so there is one definition rather than two that drift:

  REF_FUSED           a roman numeral + arabic page run + terminating period,
                      followed by more text, inside `04_given_names`
  DESC_FUSED_REF      the same run inside `09_description`, followed by
                      something shaped like a name-head
  EMBEDDED_NAME_YEAR  a full "Surname, Given (1801-1870)," deeper inside a
                      description

Usage:
    python scripts/segmentation/suggest_row_corrections.py
    python scripts/segmentation/suggest_row_corrections.py --write
"""

import argparse
import csv
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
REVIEW = ROOT / "data" / "review" / "row_corrections_review.csv"
PROPOSED = ROOT / "data" / "parsed" / "personregister_xi_parsed.proposed.tsv"
RECOVERED_COL = "14_recovered_references"

ROMAN = r"(?:I{1,3}|IV|VI{0,3}|IX|X)"
REF_FUSED = re.compile(rf"{ROMAN}\s[\d\s\-]*\d\.\s+\S")
# Same rule, but the trailing character is a lookahead so the boundary falls
# *before* the next entry rather than one character into it.
REF_FUSED_AT = re.compile(rf"{ROMAN}\s[\d\s\-]*\d\.\s+(?=\S)")
DESC_FUSED_REF = re.compile(
    rf"{ROMAN}\s[\d\s\-]*\d\.\s+"
    r"(?=[A-ZÆØÅÖÜ][a-zæøåöäü]+(?:,|\s\(|\s[A-ZÆØÅÖÜ][a-zæøåöäü]+\s\())")
EMBEDDED_NAME_YEAR = re.compile(
    r"[A-ZÆØÅÖÜ][a-zæøåöäü]+(?:\s\([^)]*\))?,\s"
    r"[A-ZÆØÅÖÜ][\wæøåöäü.]*(?:\s[A-ZÆØÅÖÜ]?[\wæøåöäü.]*)*\s?"
    r"\((?:ca\.\s*)?(?:d\.|død)?\s*\d{3,4}[\s–—\-]*\d{0,4}\),")
CITATION = re.compile(rf"\b({ROMAN})\s+(\d{{1,3}}(?:[\s,]+\d{{1,3}}(?:-\d{{1,3}})?)*)\s*\.")
TAIL_HEAD = re.compile(r"^([A-ZÆØÅÖÜ][\wæøåöäü.'’-]*)")
# The register is printed with single-letter alphabet dividers between
# sections. A fused tail often begins with one, and it is not a name.
DIVIDER = re.compile(r"^[A-ZÆØÅÖÜ]\.?\s+")
GENITIVE = re.compile(r"[’']s$")


def tail_head(tail: str):
    """The surname the fused tail begins with, or None if it does not begin
    with one. Skips an alphabet divider; refuses a genitive ("Amé's Far" is a
    relation, not an entry) and a bare initial."""
    tail = DIVIDER.sub("", tail.strip(), count=1)
    m = TAIL_HEAD.match(tail)
    if not m:
        return None
    head = m.group(1)
    if GENITIVE.search(head) or len(head.rstrip(".")) < 2:
        return None
    return head

# Substitutions this scanner's OCR actually makes, both directions. A pair of
# names differing only by these is a reading error; a pair differing otherwise
# is two people who happen to look alike, and saying which is which is the
# difference between a useful list and a list nobody trusts.
OCR_CONFUSIONS = [("rn", "m"), ("ii", "ü"), ("c", "e"), ("l", "i"), ("i", "t"),
                  ("c", "g"), ("s", "5"), ("o", "ö"), ("a", "ä"), ("h", "b"),
                  ("f", "t"), ("u", "ii"), ("", " ")]


def ocr_confusable(a: str, b: str) -> bool:
    """True if one name becomes the other under the scanner's own confusions."""
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    for x, y in OCR_CONFUSIONS:
        for p, q in ((x, y), (y, x)):
            if p and a.replace(p, q) == b.replace(p, q):
                return True
            if p and (a.replace(p, q) == b or b.replace(p, q) == a):
                return True
    return False


FIELDS = ["person_id", "kind", "tier", "action", "column", "evidence", "proposal"]


def expand(vol: str, run: str) -> list:
    """'298 383-85' under vol I -> ['I:298','I:383','I:384','I:385']"""
    out = []
    for tok in re.split(r"[\s,]+", run.strip()):
        if not tok:
            continue
        if "-" in tok:
            a, _, b = tok.partition("-")
            if a.isdigit() and b.isdigit():
                end = a[: len(a) - len(b)] + b if len(b) < len(a) else b
                if end.isdigit() and int(a) <= int(end) <= int(a) + 50:
                    out += [f"{vol}:{p}" for p in range(int(a), int(end) + 1)]
                    continue
            if a.isdigit():
                out.append(f"{vol}:{a}")
        elif tok.isdigit():
            out.append(f"{vol}:{tok}")
    return out


def load():
    with MASTER.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return list(r), list(r.fieldnames or [])


def find_splits(rows, surnames):
    """Split-side findings, tiered."""
    out = []
    for r in rows:
        pid = r["00_person_id"]
        desc = r["09_description"] or ""
        gn = r["04_given_names"] or ""

        for col, text, kind in (("09_description", desc, "description_reference_run"),
                                ("04_given_names", gn, "given_names_tail")):
            pat = DESC_FUSED_REF if col == "09_description" else REF_FUSED_AT
            m = pat.search(text)
            if not m:
                continue
            # A row can be fused more than once. Take the last boundary for
            # the trim, the whole prefix for citation recovery.
            end = m.end()
            while True:
                nxt = pat.search(text, end)
                if not nxt:
                    break
                end = nxt.end()
            head, tail = text[:m.end()], text[end:]

            have = {t.strip() for t in (r["11_references_parsed"] or "").split(";")
                    if t.strip()}
            seen, cites = set(), []
            for mm in CITATION.finditer(head):          # additive only: a page
                for c in expand(*mm.groups()):          # already carried is not
                    if c not in have and c not in seen:  # a recovery
                        seen.add(c)
                        cites.append(c)
            if cites:
                out.append({"person_id": pid, "kind": kind, "tier": "1",
                            "action": "recover citations", "column": col,
                            "evidence": head[-60:].strip(),
                            "proposal": ";".join(cites)})
            if tail.strip():
                out.append({"person_id": pid, "kind": kind, "tier": "2",
                            "action": "trim the column", "column": col,
                            "evidence": tail[:70].strip(),
                            "proposal": head.strip()})
                th = tail_head(tail)
                if th:
                    key = th.lower()
                    if key not in surnames:
                        out.append({"person_id": pid, "kind": kind, "tier": "3",
                                    "action": "split out a new row", "column": col,
                                    "evidence": tail[:70].strip(),
                                    "proposal": f"new entry: {th}"})
                    else:
                        out.append({"person_id": pid, "kind": kind, "tier": "2",
                                    "action": "no split — the entry already exists",
                                    "column": col, "evidence": tail[:70].strip(),
                                    "proposal": f"see existing {th}"})

        for mm in EMBEDDED_NAME_YEAR.finditer(desc):
            if mm.start() > 20:
                out.append({"person_id": pid, "kind": "embedded_name_year", "tier": "4",
                            "action": "review by hand", "column": "09_description",
                            "evidence": mm.group(0)[:70],
                            "proposal": "a second person is buried in this description"})
                break
    return out


def find_merges(rows):
    """The reverse defect. Reported only — a merge renumbers and rewrites."""
    out = []
    sig = lambda r: frozenset(
        t.strip() for t in (r["11_references_parsed"] or "").split(";") if t.strip())

    exact = defaultdict(list)
    CONTENT = ["03_surname", "04_given_names", "06_birth_year", "07_death_year",
               "09_description", "11_references_parsed"]
    for r in rows:
        exact[tuple(r[c] for c in CONTENT)].append(r)
    for group in exact.values():
        if len(group) > 1:
            out.append({"person_id": " ".join(x["00_person_id"] for x in group),
                        "kind": "exact_duplicate", "tier": "4",
                        "action": "merge — review by hand", "column": "(row)",
                        "evidence": f"{group[0]['03_surname']}, {group[0]['04_given_names']}"[:70],
                        "proposal": f"keep {group[0]['00_person_id']}"})

    by_sig = defaultdict(list)
    for r in rows:
        s = sig(r)
        if len(s) >= 2:                 # a single shared page is coincidence
            by_sig[s].append(r)
    for s, group in by_sig.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i]["03_surname"] or "", group[j]["03_surname"] or ""
                if a == b or not a or not b:
                    continue
                ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
                if ratio < 0.80:
                    continue
                conf = ocr_confusable(a, b)
                out.append({
                    "person_id": f"{group[i]['00_person_id']} {group[j]['00_person_id']}",
                    "kind": "ocr_twin" if conf else "similar_names",
                    "tier": "4",
                    "action": "merge — review by hand" if conf
                              else "probably not a merge — review by hand",
                    "column": "(row)",
                    "evidence": f"{a} / {b}  ({len(s)} shared pages)",
                    "proposal": (f"one scanner confusion apart ({ratio:.2f})" if conf
                                 else f"alike but not an OCR confusion ({ratio:.2f})")})
    return out


def apply_safe(rows, fields, findings):
    """Tiers 1 and 2 only, onto a copy. Additive: the recovered citations go
    to a new column, never over the parsed ones."""
    by_id = {r["00_person_id"]: r for r in rows}
    out_fields = fields + ([RECOVERED_COL] if RECOVERED_COL not in fields else [])
    proposed = [dict(r, **{RECOVERED_COL: r.get(RECOVERED_COL, "")}) for r in rows]
    pby = {r["00_person_id"]: r for r in proposed}
    n1 = n2 = 0
    for f in findings:
        r = pby.get(f["person_id"])
        if r is None:
            continue
        if f["tier"] == "1":
            r[RECOVERED_COL] = f["proposal"]
            n1 += 1
        elif f["tier"] == "2" and f["action"] == "trim the column":
            r[f["column"]] = f["proposal"]
            n2 += 1
    return proposed, out_fields, n1, n2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true",
                    help="write the review and proposed files")
    args = ap.parse_args()

    rows, fields = load()
    surnames = {(r["03_surname"] or "").strip().lower() for r in rows}
    splits = find_splits(rows, surnames)
    merges = find_merges(rows)
    findings = splits + merges

    tiers = defaultdict(int)
    for f in findings:
        tiers[(f["tier"], f["action"])] += 1
    print(f"  register rows {len(rows):,}\n")
    for (t, a), n in sorted(tiers.items()):
        print(f"    tier {t}  {a:<38} {n:>5}")
    affected = len({f['person_id'] for f in splits})
    print(f"\n  rows with a split-side defect : {affected:,}")
    print(f"  merge candidates              : {len(merges):,}")

    proposed, out_fields, n1, n2 = apply_safe(rows, fields, findings)
    print(f"\n  safe corrections applied to the proposal:")
    print(f"     citations recovered into {RECOVERED_COL} : {n1:,}")
    print(f"     descriptions/names trimmed             : {n2:,}")

    if not args.write:
        print("\n  dry run — nothing written. Re-run with --write.")
        return 0

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(findings)
    with PROPOSED.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, delimiter="\t")
        w.writeheader()
        w.writerows(proposed)
    print(f"\n  wrote {REVIEW.relative_to(ROOT)}  ({len(findings):,} findings)")
    print(f"  wrote {PROPOSED.relative_to(ROOT)}  ({len(proposed):,} rows)")
    print("\n  The master is untouched. Diff the proposal against it, then\n"
          "  promote it deliberately — tier 3 and 4 still need a person.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
