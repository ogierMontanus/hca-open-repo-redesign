#!/usr/bin/env python3
"""
add_warnings_and_actions.py — gather every finding the project has made about
the person register onto the rows it is about.

Three things, in one pass over the annotated register:

  1. **One merge list.** `person_duplicate_candidates.csv` and
     `row_corrections_review.csv` find duplicates on different axes and barely
     overlap — 73 pairs and 23 pairs, 1 in common. The first needs the surname
     to match exactly, so it never sees `Golloredo-Mansfeld` beside
     `Colloredo-Mansfeld`; the second requires two shared pages, so it never
     sees a group tied together by one. Neither is complete alone. Written to
     `merge_pairs_combined.csv`.

  2. **`remove_duplicate` in column X.** On the member of a pair that should
     go, not on both. Which one is not a coin toss: rows 1-921 of the merged
     register are a separate, worse OCR pass (`Amesen Kali`, `Burdett-Goutts`,
     `Clausen-Schiitz`), and where a pair straddles that boundary the block-1
     row is the corrupted reading. Otherwise the row carrying fewer citations
     gives way. Pairs whose two rows are *not* duplicates — the four demoted
     to `probably not a merge` and the block-1 triage's `BEHOLD` verdicts —
     get no action.

  3. **Warnings in columns Y-Z.** The five other review files, joined through
     whichever id space each one speaks:

        label_corruption.csv          Reg  -> "wor" overwritten by "Pag"
        person_reference_merge_review Reg  -> citation list is the next entry's
        person_crosswalk_review.csv   HCAP -> no counterpart in the live register
        page_reference_problems.csv   both -> cites a page that does not exist
        person_duplicate_candidates   PerXI

Nothing is corrected. A warning marks a row as needing a person to look at it.

Usage:
    python scripts/segmentation/add_warnings_and_actions.py
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10 ** 7)

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "data" / "review"
ANN = REVIEW / "personregister_xi_merged_2026-09-06_annotated.tsv"
PAIRS_OUT = REVIEW / "merge_pairs_combined.csv"
BLOCK1_END = 921          # rows 1-921 are the separate A-Z block

ACTION_COL = "24_action"
WARN_COL = "25_warnings"
DETAIL_COL = "26_warning_detail"
NEW = [ACTION_COL, WARN_COL, DETAIL_COL]


def read(p, delim=","):
    if not p.exists():
        print(f"  [spring over] {p.name} findes ikke")
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", type=Path, default=ANN)
    args = ap.parse_args()

    rows = read(ANN, "\t")
    order = {r["01_entry_id"]: i for i, r in enumerate(rows)}
    by_id = {r["01_entry_id"]: r for r in rows}
    nrefs = lambda e: len([t for t in (by_id[e]["11_references_parsed"] or "").split(";") if t.strip()]) if e in by_id else 0
    in_block1 = lambda e: order.get(e, 10 ** 9) < BLOCK1_END
    print(f"  {len(rows):,} rækker, blok 1 = de første {BLOCK1_END}")

    # --- id maps ------------------------------------------------------------
    parsed = read(ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv", "\t")
    hcap2per = {r["00_person_id"]: r["01_entry_id"] for r in parsed
                if r.get("00_person_id") and r["01_entry_id"] in by_id}
    cw = read(ROOT / "data" / "curated" / "person_id_crosswalk.csv")
    reg2per = {r["reg_id"]: hcap2per[r["person_id"]] for r in cw
               if r.get("reg_id") and r.get("person_id") in hcap2per}
    print(f"  id-kort: HCAP->PerXI {len(hcap2per):,}   Reg->PerXI {len(reg2per):,}")

    # --- 1. the combined pair list -----------------------------------------
    pairs = {}

    def add(a, b, source, rule, evidence, mergeable=True):
        if a not in by_id or b not in by_id or a == b:
            return
        k = frozenset((a, b))
        p = pairs.setdefault(k, {"sources": set(), "rules": set(),
                                 "evidence": [], "mergeable": mergeable})
        p["sources"].add(source)
        p["rules"].add(rule)
        if evidence and evidence not in p["evidence"]:
            p["evidence"].append(evidence)
        p["mergeable"] = p["mergeable"] and mergeable

    for d in read(REVIEW / "person_duplicate_candidates.csv"):
        ids = d["entry_ids"].split()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                add(ids[i], ids[j], "duplicate_candidates", "samme efternavn + fælles sider",
                    f'{d["surname"]}: {d["pages"][:60]}')

    for r in rows:
        for part in (r.get("22_merge_candidate") or "").split(" | "):
            if not part.strip():
                continue
            other = part.split(" — ")[0].strip()
            kind = r.get("15_fix_kind", "")
            ok = "probably not" not in (r.get("17_fix_action") or "")
            rule = ("krydshenvisnings-tvilling" if "cross_reference_twin" in kind
                    else "OCR-forveksling" if "ocr_twin" in kind
                    else "identisk række" if "exact_duplicate" in kind
                    else "lignende navne")
            add(r["01_entry_id"], other, "row_corrections", rule,
                part.split(" — ", 1)[-1][:70], mergeable=ok)

    out = []
    for k, p in pairs.items():
        a, b = sorted(k, key=lambda e: order.get(e, 10 ** 9))
        # which row goes: the block-1 reading, else the sparser one
        if p["mergeable"]:
            if in_block1(a) and not in_block1(b):
                drop, keep, why = a, b, "blok 1 er den ringere OCR-læsning"
            elif in_block1(b) and not in_block1(a):
                drop, keep, why = b, a, "blok 1 er den ringere OCR-læsning"
            elif nrefs(a) != nrefs(b):
                drop, keep = (a, b) if nrefs(a) < nrefs(b) else (b, a)
                why = "færrest sidehenvisninger"
            else:
                drop, keep, why = "", "", "lige stærke — afgør manuelt"
        else:
            drop, keep, why = "", "", "sandsynligvis IKKE samme person"
        out.append({
            "entry_id_a": a, "navn_a": f'{by_id[a]["03_surname"]}, {by_id[a]["04_given_names"]}'.strip(", "),
            "sider_a": nrefs(a),
            "entry_id_b": b, "navn_b": f'{by_id[b]["03_surname"]}, {by_id[b]["04_given_names"]}'.strip(", "),
            "sider_b": nrefs(b),
            "kilde": "+".join(sorted(p["sources"])), "regel": "; ".join(sorted(p["rules"])),
            "anbefalet_fjernet": drop, "beholdes": keep, "begrundelse": why,
            "evidens": " | ".join(p["evidence"])[:160]})
    out.sort(key=lambda r: order.get(r["entry_id_a"], 0))
    with PAIRS_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    both = sum(1 for r in out if "+" in r["kilde"])
    drops = {r["anbefalet_fjernet"] for r in out if r["anbefalet_fjernet"]}
    print(f"\n  {PAIRS_OUT.name}: {len(out)} par "
          f"({sum(1 for r in out if r['kilde']=='duplicate_candidates')} kun duplicate_candidates, "
          f"{sum(1 for r in out if r['kilde']=='row_corrections')} kun row_corrections, {both} begge)")
    print(f"     med en anbefalet fjernelse: {len(drops)}")

    # --- 2. remove_duplicate ------------------------------------------------
    action = defaultdict(list)
    for e in drops:
        action[e].append("remove_duplicate")
    tri = {r["01_entry_id"]: r for r in read(REVIEW / "block1_rows_1-921_triage.csv")}
    n_tri = 0
    for e, t in tri.items():
        if "kan fjernes" in t["vurdering"] and e in by_id and not action[e]:
            # a weaker finding than the pair list: one row in the rest holds
            # all this row's pages and reads similarly. Labelled apart so it
            # is not reviewed at the same speed.
            action[e].append("remove_duplicate:blok1_triage")
            n_tri += 1
    print(f"     heraf {n_tri} tilføjet fra blok 1-triagen")

    # --- 3. the warnings ----------------------------------------------------
    warn, detail = defaultdict(list), defaultdict(list)

    def mark(pid, code, text):
        if pid in by_id and code not in warn[pid]:
            warn[pid].append(code)
        if pid in by_id and text:
            detail[pid].append(text)

    for r in read(REVIEW / "label_corruption.csv"):
        if r["entity_type"] == "person":
            mark(reg2per.get(r["entity_id"], ""), "label_corruption",
                 f'"wor"->"Pag": {r["current"][:60]} -> {r["suggested"][:40]}')
    for r in read(REVIEW / "person_reference_merge_review.csv"):
        mark(hcap2per.get(r["person_id"], ""), "run_on_reference_list",
             f'{r["reason"]}, {r["n_refs"]} henvisninger tilbageholdt')
    for r in read(REVIEW / "person_crosswalk_review.csv"):
        mark(hcap2per.get(r["person_id"], ""),
             f'no_live_match:{r["tier"]}', r["note"][:70])
    pp = defaultdict(list)
    for r in read(REVIEW / "page_reference_problems.csv"):
        pid = (hcap2per.get(r["entity_id"]) if r["side"] == "segmentation"
               else reg2per.get(r["entity_id"]))
        if pid:
            pp[pid].append(f'{r["vol"]} {r["page"]} ({r["kind"]})')
    for pid, v in pp.items():
        mark(pid, "bad_page_reference", f'{len(v)} stk: ' + ", ".join(v[:6]))
    for r in read(REVIEW / "person_duplicate_candidates.csv"):
        for e in r["entry_ids"].split():
            mark(e, "duplicate_candidate", f'{r["surname"]}, {r["n_entries"]} poster')

    # --- write --------------------------------------------------------------
    fields = [c for c in rows[0].keys() if c not in NEW] + NEW
    for r in rows:
        e = r["01_entry_id"]
        r[ACTION_COL] = "; ".join(action.get(e, []))
        r[WARN_COL] = "; ".join(warn.get(e, []))
        r[DETAIL_COL] = " | ".join(detail.get(e, []))[:300]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"\n  kolonne {chr(65+fields.index(ACTION_COL))} {ACTION_COL:18} "
          f"{sum(1 for r in rows if r[ACTION_COL]):>5} rækker")
    print(f"  kolonne {chr(65+fields.index(WARN_COL))} {WARN_COL:18} "
          f"{sum(1 for r in rows if r[WARN_COL]):>5} rækker")
    cnt = defaultdict(int)
    for r in rows:
        for c in r[WARN_COL].split("; "):
            if c:
                cnt[c] += 1
    for c, n in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"       {n:>5}  {c}")

    # xlsx
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "personregister XI"
    ws.append(fields)
    FILL = {ACTION_COL: "FFC7CE", WARN_COL: "FFF2CC", DETAIL_COL: "FFF2CC"}
    for c, name in enumerate(fields, 1):
        ws.cell(1, c).font = Font(bold=True)
        if name in FILL:
            ws.cell(1, c).fill = PatternFill("solid", fgColor=FILL[name])
        elif name.startswith(("15_", "16_", "17_", "18_", "19_", "20_", "21_", "22_", "23_")):
            ws.cell(1, c).fill = PatternFill("solid", fgColor="FFE8CC")
    red = PatternFill("solid", fgColor="FFC7CE")
    amber = PatternFill("solid", fgColor="FFE0B2")
    ai = fields.index(ACTION_COL) + 1
    for r in rows:
        ws.append([r.get(c, "") for c in fields])
        if r[ACTION_COL]:
            ws.cell(ws.max_row, ai).fill = (
                amber if "triage" in r[ACTION_COL] else red)
    ws.freeze_panes = "A2"
    xp = args.out.with_suffix(".xlsx")
    try:
        wb.save(xp)
    except PermissionError:
        # Excel holds a lock on an open workbook; write beside it rather than
        # failing a run that has already done all its work
        xp = xp.with_name(xp.stem + "_v2.xlsx")
        wb.save(xp)
        print(f"  [laast] originalen er aaben i Excel - skrev {xp.name} i stedet")
    print(f"\n  skrev {args.out.name} og {xp.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
