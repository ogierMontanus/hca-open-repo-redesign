#!/usr/bin/env python3
"""
compare_to_reference.py — measure the person register against an independent
transcription of the same printed volume.

`data/raw/Personer _ HCA_tsv.txt` is a separately produced, already
person-per-row transcription of register XI. It is not a pipeline input:
nothing reads it, and nothing should. It is the **only external check on
whether our segmentation found the right people**, and this is the script
that performs it.

Until now it was not a script. The method below was carried out by hand
across a working session and written up as prose in
docs/person-register-segmentation.md, which notes "ingen færdig scriptfil".
Every later change to the segmentation has therefore been unmeasurable. That
is the gap this closes, and it is why the plan puts it *before* any work on
the cleaning chain: consolidating that chain is the riskiest step in the
migration and must not be the first one that cannot be checked.

The method, reproduced from that record
---------------------------------------
Raw row counts mislead, because the two sides count cross-references
differently. Compare *person entries*, and compare them on a normalised core:

  1. Normalise the name: NFKD-strip diacritics, remove **every** year
     parenthesis (not only the last — that was an early bug in the manual
     method), fold punctuation away, upper-case.

  2. Set-difference the normalised cores. Anything present on one side only
     is a *candidate* discrepancy, not yet a real one.

  3. For each candidate, look up whether the opposite side has an entry with
     the same **page-reference signature** — the fully expanded set of
     VOL:PAGE citations. If it does, the two are the same person spelled
     differently, not a surplus or a gap. Only what survives this is real.

Step 3 is what makes the measurement worth anything: on the numbers recorded
in that session it reclassified 330 of 344 apparent surpluses and 170 of 171
apparent gaps as spelling variants.

Also reported
-------------
A duplicate scan over our own side: entries sharing a folded surname, an
identical page-reference signature, AND compatible given names. The session
record lists this as known weakness #3 — two duplicate classes were found
reactively, by a human noticing examples, and "der er intet i tests der
fanger en fremtidig gentagelse".

The given-name test is what makes the scan usable. Surname plus signature
alone returns ~500 groups, most of them siblings and spouses who share pages
because they appear together; with it, 66 remain, and they look like
"Bang, Caroline Amalie, f. Ibsen" beside a bare "Bang" on the same page.

Usage
-----
    python scripts/validation/compare_to_reference.py
    python scripts/validation/compare_to_reference.py --write   # CSV reports
    python scripts/validation/compare_to_reference.py --limit 40
"""

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
OURS = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
REFERENCE = ROOT / "data" / "raw" / "Personer _ HCA_tsv.txt"
OUT_DIR = ROOT / "data" / "review"

# Every parenthesis holding a year, a year range, a "død 1881", a "ca. 1820",
# or an "f. Chr." — removed wholesale before comparing. Removing only the
# trailing one was the early bug the session record calls out.
# The register's own redirect marker, in both spellings it prints.
SEE_REDIRECT = re.compile(r"\bse\s+og(?:s|)(?:aa|å)\s*:|\bse\s*:", re.I)

YEAR_PAREN = re.compile(
    r"\((?=[^)]*\d)[^)]*(?:\d{3,4}|f\.\s*Chr\.|død|ca\.)[^)]*\)", re.I)


def fold_name(name: str) -> str:
    """The normalised comparison core. Step 1 of the method."""
    s = YEAR_PAREN.sub(" ", name or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("æ", "ae").replace("Æ", "AE")
    s = s.replace("ø", "o").replace("Ø", "O")
    s = re.sub(r"[^A-Za-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def parse_our_refs(cell: str) -> frozenset:
    """'I:272;I:298' -> {('I','272'), ('I','298')}"""
    out = set()
    for tok in (cell or "").split(";"):
        tok = tok.strip()
        if ":" in tok:
            v, _, p = tok.rpartition(":")
            v, p = v.strip(), p.strip()
            if v and p.isdigit():
                out.add((v, p))
    return frozenset(out)


def load_ours():
    if not OURS.exists():
        sys.exit(f"missing {OURS}")
    rows = []
    with OURS.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r.get("02_entry_type") == "krydshenvisning":
                continue          # a redirect stub is not a person
            surname = (r.get("03_surname") or "").strip()
            given = (r.get("04_given_names") or "").strip()
            name = f"{surname}, {given}".strip(", ") if given else surname
            rows.append({
                "id": r.get("01_entry_id", ""),
                "name": name,
                "surname": surname,
                "given": given,
                "core": fold_name(name),
                "sig": parse_our_refs(r.get("11_references_parsed", "")),
            })
    return rows


def load_reference():
    """Name, description, then repeating VOL/PAGE pairs, tab separated."""
    if not REFERENCE.exists():
        sys.exit(f"missing {REFERENCE}")
    rows, crossrefs = [], 0
    with REFERENCE.open(encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    for line in lines[2:]:                      # title line, then header
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].strip()
        if not name:
            continue
        desc = parts[1] if len(parts) > 1 else ""
        sig = set()
        rest = parts[2:]
        for i in range(0, len(rest) - 1, 2):
            v, p = rest[i].strip(), rest[i + 1].strip()
            if v and p.isdigit():
                sig.add((v, p))
        # A redirect stub is identified by its "se:" / "se også:" marker, NOT
        # by having no citation. 1,276 reference rows carry no tabulated
        # volume/page, but only 682 of them are redirects; the other 594 are
        # ordinary people whose citations this transcription simply did not
        # put in columns ("Agda — Datter af Mickel Kræmmer, Vadstena."). An
        # earlier draft of this script excluded all 1,276 and so mislaid 594
        # real entries, which inflated the apparent surplus by roughly that
        # amount. They are kept, and matched on the name core alone, since
        # they have no signature for step 3 to use.
        if SEE_REDIRECT.search(f"{name} {desc}"):
            crossrefs += 1
            continue
        rows.append({
            "name": name,
            "surname": name.split(",")[0].strip(),
            "core": fold_name(name),
            "sig": frozenset(sig),
        })
    return rows, crossrefs


def index_by_signature(rows):
    ix = defaultdict(list)
    for r in rows:
        if r["sig"]:
            ix[r["sig"]].append(r)
    return ix


def classify(only_here, other_rows, other_by_sig):
    """Step 3: an apparent discrepancy that the opposite side matches on its
    full page-reference signature is a spelling variant, not a real one."""
    variants, real = [], []
    other_cores = {r["core"] for r in other_rows}
    for r in only_here:
        twin = other_by_sig.get(r["sig"])
        if r["sig"] and twin:
            variants.append((r, twin[0]))
        elif r["core"] in other_cores:
            variants.append((r, None))
        else:
            real.append(r)
    return variants, real


def given_names_compatible(a: str, b: str) -> bool:
    """Could these two given-name strings be the same person?

    Surname plus an identical page signature is not enough on its own: a
    register full of families puts siblings on the same pages, so "Anholm,
    Frieda" and "Anholm, Ida" share a surname and a signature and are plainly
    two people. Requiring the given names to be *compatible* as well is what
    separates a duplicate from a family.

    Compatible means: one side is empty (the register often gives a bare
    surname), the two fold to the same string, or one is an initial-form of
    the other — "C." against "Carl", "J. C." against "Jens Christian".
    """
    fa, fb = fold_name(a), fold_name(b)
    if not fa or not fb or fa == fb:
        return True
    ta, tb = fa.split(), fb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) > len(long_):
        return False
    # every token of the shorter side must initial-match the longer side
    return all(l.startswith(s) or s.startswith(l)
               for s, l in zip(short, long_)) and bool(short)


def duplicate_scan(ours):
    """Known weakness #3: entries that are the same person twice.

    The session record notes that both duplicate classes found so far were
    spotted reactively — a human noticed an example — and that "der er intet
    i tests der fanger en fremtidig gentagelse". This is the systematic scan
    it asks for.

    Grouped on folded surname plus the identical page-reference signature,
    then filtered by given_names_compatible(). Without that filter the scan
    returns ~500 groups, most of them siblings and spouses sharing pages,
    which is a report nobody can act on.
    """
    groups = defaultdict(list)
    for r in ours:
        if r["sig"] and r["surname"]:
            groups[(fold_name(r["surname"]), r["sig"])].append(r)

    out = {}
    for key, rs in groups.items():
        if len(rs) < 2:
            continue
        keep = [rs[0]]
        for cand in rs[1:]:
            if any(given_names_compatible(cand["given"], k["given"]) for k in keep):
                keep.append(cand)
        if len(keep) > 1:
            out[key] = keep
    return out


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)}  ({len(rows):,} rows)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true",
                    help="write the findings to data/curated/*.csv")
    ap.add_argument("--limit", type=int, default=15,
                    help="examples to print per section (default 15)")
    args = ap.parse_args()

    ours = load_ours()
    ref, ref_crossrefs = load_reference()

    ours_by_sig = index_by_signature(ours)
    ref_by_sig = index_by_signature(ref)
    ours_cores = {r["core"] for r in ours}
    ref_cores = {r["core"] for r in ref}

    only_ours = [r for r in ours if r["core"] not in ref_cores]
    only_ref = [r for r in ref if r["core"] not in ours_cores]

    var_ours, real_ours = classify(only_ours, ref, ref_by_sig)
    var_ref, real_ref = classify(only_ref, ours, ours_by_sig)

    print("=" * 68)
    print("  Person register vs. the independent transcription")
    print("=" * 68)
    print(f"  our person entries          {len(ours):>7,}")
    print(f"  reference person entries    {len(ref):>7,}   "
          f"(+{ref_crossrefs:,} redirect stubs excluded)")
    print(f"  raw difference              {len(ours) - len(ref):>+7,}")
    print()
    print(f"  apparent surplus (only ours){len(only_ours):>7,}")
    print(f"     of which spelling variants {len(var_ours):>6,}")
    print(f"     genuinely unmatched        {len(real_ours):>6,}")
    print()
    print(f"  apparent gap (only reference){len(only_ref):>6,}")
    print(f"     of which spelling variants {len(var_ref):>6,}")
    print(f"     genuinely unmatched        {len(real_ref):>6,}")
    print()
    print(f"  NET real difference         {len(real_ours) - len(real_ref):>+7,}")
    print()

    if real_ours:
        print(f"  Unmatched on our side ({len(real_ours):,}) — in our register, "
              "not the reference:")
        for r in real_ours[:args.limit]:
            print(f"     {r['id']:<12} {r['name'][:56]}")
        if len(real_ours) > args.limit:
            print(f"     … {len(real_ours) - args.limit:,} more")
        print()
    if real_ref:
        print(f"  Unmatched on the reference side ({len(real_ref):,}) — "
              "possible gaps in ours:")
        for r in real_ref[:args.limit]:
            print(f"     {r['name'][:68]}")
        if len(real_ref) > args.limit:
            print(f"     … {len(real_ref) - args.limit:,} more")
        print()

    dups = duplicate_scan(ours)
    print(f"  Duplicate candidates (same surname + identical page signature): "
          f"{len(dups):,} group(s), {sum(len(v) for v in dups.values()):,} rows")
    for (sur, sig), rs in list(dups.items())[:args.limit]:
        print(f"     {sur[:28]:<30} {len(sig)} page(s): "
              + " | ".join(r["name"][:30] for r in rs))
    if len(dups) > args.limit:
        print(f"     … {len(dups) - args.limit:,} more")
    print()

    if args.write:
        write_csv(OUT_DIR / "person_reference_unmatched_ours.csv",
                  ["entry_id", "name", "pages"],
                  [{"entry_id": r["id"], "name": r["name"],
                    "pages": " ".join(f"{v}:{p}" for v, p in sorted(r["sig"]))}
                   for r in real_ours])
        write_csv(OUT_DIR / "person_reference_unmatched_reference.csv",
                  ["name", "pages"],
                  [{"name": r["name"],
                    "pages": " ".join(f"{v}:{p}" for v, p in sorted(r["sig"]))}
                   for r in real_ref])
        write_csv(OUT_DIR / "person_duplicate_candidates.csv",
                  ["surname", "n_entries", "pages", "names", "entry_ids"],
                  [{"surname": sur, "n_entries": len(rs),
                    "pages": " ".join(f"{v}:{p}" for v, p in sorted(sig)),
                    "names": " | ".join(r["name"] for r in rs),
                    "entry_ids": " ".join(r["id"] for r in rs)}
                   for (sur, sig), rs in sorted(dups.items(),
                                                key=lambda kv: -len(kv[1]))])

    # A net difference in the low tens is the state the session record
    # reached and called "praktisk talt dækningslige". Anything much larger
    # means the segmentation moved and nobody measured it.
    net = abs(len(real_ours) - len(real_ref))
    print(f"  Net real difference is {net}. The last hand measurement reached "
          "~10;\n  a large jump means the segmentation changed unmeasured.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
