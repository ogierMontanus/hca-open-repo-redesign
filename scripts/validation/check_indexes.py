#!/usr/bin/env python3
"""
check_indexes.py — integrity rules for the registers.

Two families of rule, both written to the *local* logic of each index and
each of its entry kinds rather than to one global schema:

  Cross-reference rules  — every "se:" / "se ogsaa:" / Krydshenvisning_til
                           must land on an entry that exists. A reference
                           that lands nowhere is a dead end for a reader,
                           and it is invisible: the stub still renders, it
                           just leads nowhere.

  Required-value rules   — what a row must carry depends on what kind of
                           row it is. A cross-reference stub has no
                           description and no page references by
                           construction; an ordinary entry that has neither
                           has lost something. The same assertion is right
                           for one and wrong for the other, so the rules are
                           written per entry kind.

Findings are graded, because they call for different work:

  blind       the target does not exist and nothing is close — an editorial
              finding, and the one that matters
  overrun     the target has swallowed the next entry — a splitter defect
  malformed   the target is not a name or title at all (empty, or a bare
              column pointer) — a parser defect
  linewrap    the target still carries an unrejoined printed-column line
              break — a known defect family with its own repair script
  near_miss   an entry is one or two characters away — an OCR defect,
              usually in the *target entry's* own label
  ocr_variant the two agree once this corpus's documented OCR confusion
              classes are collapsed — still two spellings, one is wrong

Usage:
    python scripts/validation/check_indexes.py            # report
    python scripts/validation/check_indexes.py --write    # + review CSVs
    python scripts/validation/check_indexes.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registers as R  # noqa: E402

ROOT = R.ROOT
REVIEW_DIR = ROOT / "data" / "curated"

UNRESOLVED = ("blind", "overrun", "malformed", "linewrap")


# ── the work sub-registers, and what each calls its columns ────────────────

PARSED_REGISTERS = [
    # (file, title col, alt-identity col, cross-ref col, see-also col,
    #  content cols that a cross-reference must NOT carry)
    ("music_register_parsed.tsv", "04_main_title", "04b_incipit",
     "09_Krydshenvisning_til", None,
     ["05_original_title", "06_creator", "07_opus", "08_part_of", "10_Note"]),
    ("non_fiction_parsed.tsv", "04_main_title", None,
     "10_Krydshenvisning_til", "09_Se_ogsaa",
     ["05_pseudonym", "06_creator", "07_translator", "08_source", "12_Note"]),
    ("novels_plays_tales_parsed.tsv", "04_main_title", None,
     "09_Krydshenvisning_til", "08_Se_ogsaa",
     ["05_original_title", "06_creator", "07_part_of", "11_Note"]),
]


class Findings:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, index, rule, severity, row_id, label, detail, nearest=""):
        self.rows.append({
            "index": index, "rule": rule, "severity": severity,
            "id": row_id, "label": (label or "").replace("\n", " ")[:120],
            "detail": (detail or "").replace("\n", " ")[:160],
            "nearest": (nearest or "").replace("\n", " ")[:120],
        })

    def by(self, **kw):
        return [r for r in self.rows
                if all(r.get(k) == v for k, v in kw.items())]


# ── cross-reference rules ──────────────────────────────────────────────────

def check_entity_redirects(ents, f: Findings):
    """XR1-XR4 over the three registers in entities.csv.

    `see` is populated by the ingester for works only; for persons and
    places the register's redirect survives only inside the label. Both are
    read (see registers.redirect_of), so all three registers are covered
    rather than one.
    """
    for etype in ("work", "person", "place"):
        idx = R.build_entity_index(ents, etype)
        rows = [r for r in ents if r["entity_type"] == etype]
        stubs = {}
        for r in rows:
            target = R.redirect_of(r)
            if not target:
                continue
            stubs[r["entity_id"]] = r
            for res in R.resolve_field(idx, target, citing_id=r["entity_id"],
                                       citing_label=r["label"]):
                if res.status == "self":
                    f.add(etype, "XR3-self-reference", "blind",
                          r["entity_id"], r["label"], res.target)
                elif res.status in UNRESOLVED:
                    f.add(etype, f"XR2-{res.status}", res.status,
                          r["entity_id"], r["label"], res.target, res.candidate)
                elif res.status in ("near_miss", "ocr_variant"):
                    f.add(etype, f"XR2-{res.status}", res.status,
                          r["entity_id"], r["label"], res.target, res.candidate)

        # XR4 — a redirect must not land on another redirect. The register
        # never chains: every stub points at a substantive entry. A stub
        # pointing at a stub is either a lost entry or a cycle, and a reader
        # following it arrives at another signpost, not at content.
        by_key = defaultdict(list)
        for sid, r in stubs.items():
            k = R.primary_key(idx, r["label"])
            if k:
                by_key[k].append(sid)
        for sid, r in stubs.items():
            t = R.redirect_of(r)
            k = R.primary_key(idx, t)
            hit = [x for x in by_key.get(k, []) if x != sid] if k else []
            if hit:
                f.add(etype, "XR4-chained-redirect", "blind",
                      sid, r["label"], t, stubs[hit[0]]["label"])


def check_parsed_registers(f: Findings):
    """XR1-XR2 and the required-value rules over the parsed work registers.

    Their cross-references are resolved against the *whole* work register in
    entities.csv, not against their own file: the register cross-references
    freely across its sub-sections (a ballet stub points at an opera entry),
    so an in-file check would report a third of them as blind.
    """
    ents = R.load_entities()
    work_idx = R.build_entity_index(ents, "work")

    for fname, title_c, alt_c, xref_c, seealso_c, content_cols in PARSED_REGISTERS:
        path = ROOT / "data" / "parsed" / fname
        if not path.exists():
            continue
        rows = R.load_parsed(fname)
        name = fname.replace("_parsed.tsv", "")

        for r in rows:
            pt = r["01_Posttype"]
            rid = r.get("RegistryTitelID") or r.get(title_c, "")[:40]
            label = r.get(title_c, "")

            if pt == "krydshenvisning":
                target = r.get(xref_c, "").strip()
                # XR1 — a cross-reference with no target is not a
                # cross-reference; it is a lost entry.
                if not target:
                    f.add(name, "XR1-no-target", "malformed", rid, label, "")
                    continue
                for res in R.resolve_field(work_idx, target):
                    if res.status in UNRESOLVED or res.status in ("near_miss", "ocr_variant"):
                        f.add(name, f"XR2-{res.status}",
                              res.status if res.status in UNRESOLVED else res.status,
                              rid, label, res.target, res.candidate)
                # RV — a stub carries no content of its own; content that
                # appears here was cut from the wrong side of a split.
                carried = [c for c in content_cols if r.get(c, "").strip()]
                if carried:
                    f.add(name, "RV-stub-carries-content", "malformed",
                          rid, label, "; ".join(f"{c}={r[c][:30]}" for c in carried))
            else:
                # RV — an ordinary entry must be identifiable. In the music
                # register a song known only by its first line legitimately
                # has no title, and carries an incipit instead, so identity
                # is title OR incipit, never title alone.
                has_title = bool(r.get(title_c, "").strip())
                has_alt = bool(alt_c and r.get(alt_c, "").strip())
                if not has_title and not has_alt:
                    what = f"{title_c}" + (f" or {alt_c}" if alt_c else "")
                    f.add(name, "RV-no-identity", "malformed", rid, label,
                          f"neither {what}")
                # RV — only a stub redirects. An ordinary entry that also
                # carries a Krydshenvisning_til was mis-typed by the parser.
                if r.get(xref_c, "").strip():
                    f.add(name, "RV-entry-redirects", "malformed", rid, label,
                          f"{xref_c}={r[xref_c][:40]}")
                # XR5 — "se ogsaa" is a soft link between two real entries;
                # it must still land somewhere.
                if seealso_c and r.get(seealso_c, "").strip():
                    for res in R.resolve_field(work_idx, r[seealso_c]):
                        if res.status in UNRESOLVED:
                            f.add(name, f"XR5-see-also-{res.status}", res.status,
                                  rid, label, res.target, res.candidate)

            # RV — provenance. Every row traces to its source workbook row,
            # except the containers the parser synthesises for a part_of
            # that has no row of its own; those have nothing to point at.
            if pt != "inferred_container" and not r.get("RegistryTitelID", "").strip():
                f.add(name, "RV-no-provenance", "malformed", rid, label,
                      "RegistryTitelID empty")


# ── the person register: its own three entry kinds ─────────────────────────

def check_person_register(f: Findings):
    path = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
    if not path.exists():
        return
    rows = R.load_parsed("personregister_xi_parsed.tsv")
    name = "personregister_xi"

    idx = R.Index(name, R.name_keys)
    for r in rows:
        if r["02_entry_type"] == "krydshenvisning":
            continue
        label = r["03_surname"] + (", " + r["04_given_names"] if r["04_given_names"] else "")
        idx.add(r["01_entry_id"], label)

    for r in rows:
        et, rid = r["02_entry_type"], r["01_entry_id"]
        label = (r["03_surname"] + (", " + r["04_given_names"]
                                    if r["04_given_names"] else "")).strip()

        if et == "krydshenvisning":
            target = r["12_see_also"].strip()
            if not target:
                # A stub with no target: the row was classified as a
                # cross-reference but the "se:" clause never parsed. The one
                # such row also carries page references, which a stub never
                # does — i.e. it is an ordinary entry mis-typed.
                f.add(name, "XR1-no-target", "malformed", rid, label,
                      r["13_raw_text"][:120])
            else:
                for res in R.resolve_field(idx, target, citing_id=rid,
                                           citing_label=label):
                    if res.status != "resolved":
                        f.add(name, f"XR2-{res.status}", res.status,
                              rid, label, res.target, res.candidate)
            # RV — content belongs at the target, never at the signpost.
            for col in ("09_description", "11_references_parsed"):
                if r[col].strip():
                    f.add(name, "RV-stub-carries-content", "malformed",
                          rid, label, f"{col}={r[col][:40]}")

        elif et == "standardpost":
            if not r["03_surname"].strip():
                f.add(name, "RV-no-identity", "malformed", rid, label, "empty surname")
            # RV — an ordinary entry says something about its person: a
            # description, or at least where the diaries mention them.
            # Either alone is normal (a name with only page references is a
            # complete entry, and so is one with only a description); having
            # neither means the entry was truncated.
            if not r["09_description"].strip() and not r["11_references_parsed"].strip():
                f.add(name, "RV-no-content", "blind", rid, label,
                      r["13_raw_text"][:120])

        elif et == "underpost":
            # RV — a sub-entry ("— Hans Datter") is meaningless without the
            # parent it hangs from; the linkage lives in 12_see_also and the
            # inherited surname.
            if not r["03_surname"].strip():
                f.add(name, "RV-no-parent", "malformed", rid, label,
                      "underpost without inherited surname")
            if not r["12_see_also"].strip():
                f.add(name, "RV-no-parent", "malformed", rid, label,
                      "underpost without parent linkage")


def run() -> Findings:
    f = Findings()
    check_entity_redirects(R.load_entities(), f)
    check_parsed_registers(f)
    check_person_register(f)
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--write", action="store_true",
                    help="write data/curated/index_integrity_review.csv")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    f = run()
    if args.json:
        print(json.dumps(f.rows, ensure_ascii=False, indent=2))
        return

    per_index = defaultdict(Counter)
    for r in f.rows:
        per_index[r["index"]][r["rule"]] += 1
    print("Register integrity\n" + "=" * 60)
    for index in sorted(per_index):
        print(f"\n{index}")
        for rule, n in sorted(per_index[index].items()):
            print(f"   {n:4d}  {rule}")
    actionable = [r for r in f.rows if r["severity"] in UNRESOLVED]
    print("\n" + "-" * 60)
    print(f"{len(f.rows)} finding(s); {len(actionable)} need a human "
          f"(blind / overrun / malformed), "
          f"{len(f.rows) - len(actionable)} are OCR near misses")
    for r in actionable:
        print(f"  [{r['severity']:9s}] {r['index']:22s} {r['id']:12s} "
              f"{r['detail'][:46]!r}" + (f"  nearest {r['nearest'][:34]!r}" if r["nearest"] else ""))

    if args.write:
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        out = REVIEW_DIR / "index_integrity_review.csv"
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(f.rows[0]) if f.rows else
                               ["index", "rule", "severity", "id", "label", "detail", "nearest"])
            w.writeheader()
            w.writerows(f.rows)
        print(f"\nwrote {out.relative_to(ROOT)}  ({len(f.rows)} rows)")


if __name__ == "__main__":
    main()
