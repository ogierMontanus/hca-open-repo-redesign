#!/usr/bin/env python3
"""
match_collin_letter_ids.py
----------------------------
Calibrates a printed-volume-position -> Brevbasen BrevID mapping for the
letters in H. C. Andersens Brevveksling med Edvard og Henriette Collin,
using 5 sampled letters per letter-volume (I-IV; V is commentary, VI is
the register -- see extract_collin_letter_pages.py), matched against
the hca_db_export SQL dump by DATE, disambiguated by sender/recipient
identity (never by letter text) when a date is shared by more than one
Brevbasen row.

Working assumption, per the task: within this one correspondence,
BrevIDs increase roughly in step with the letters' position in the
printed volumes (evidence, not just assumed -- see the printed report
this script writes). The 20 calibration points let that assumption be
checked directly rather than taken on faith, and support a per-volume
linear interpolation for every letter that wasn't hand-verified.

Tables read from ../hca_db_export/hca_db.sql (sibling checkout):
  brev(ID, Dato, ...)                 -- ID is the BrevID; Dato is
                                          normalized YYYY-MM-DD (or
                                          -00 for an unknown day/month)
  brev_person(BrevID, PersonID, Relation)  -- Relation: afsender/modtager
  brevperson(ID, Fornavn, Efternavn)  -- resolves PersonID -> a name

Output:
  data/curated/collin_letter_id_calibration.csv -- the 20 sampled
    letters with their verified (or flagged-ambiguous/unmatched) BrevID
  data/curated/collin_letter_pages_with_ids.csv -- all 505 letters from
    collin_letter_pages.csv, each with an interpolated estimated_brevid
    (per-volume linear fit from that volume's 5 calibration points) plus
    the verified BrevID directly on the 20 calibration rows themselves

Run from the repo root (after extract_collin_letter_pages.py):
  python scripts/correspondence/match_collin_letter_ids.py
"""

import csv
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SQL_PATH = r"C:\Users\nh\Documents\GitHub\hca_db_export\hca_db.sql"
LETTER_PAGES_CSV = os.path.join(ROOT, "data", "curated", "collin_letter_pages.csv")
OUT_CALIBRATION = os.path.join(ROOT, "data", "curated", "collin_letter_id_calibration.csv")
OUT_FULL = os.path.join(ROOT, "data", "curated", "collin_letter_pages_with_ids.csv")


def parse_tuples(sql_text):
    tuples, i, n = [], 0, len(sql_text)
    while i < n:
        if sql_text[i] == '(':
            depth, j, in_str, esc = 1, i + 1, False, False
            while j < n and depth > 0:
                c = sql_text[j]
                if in_str:
                    if esc: esc = False
                    elif c == '\\': esc = True
                    elif c == "'": in_str = False
                else:
                    if c == "'": in_str = True
                    elif c == '(': depth += 1
                    elif c == ')': depth -= 1
                j += 1
            tuples.append(sql_text[i + 1:j - 1])
            i = j
        else:
            i += 1
    return tuples


def split_fields(tuple_text):
    fields, cur, in_str, esc = [], [], False, False
    for c in tuple_text:
        if in_str:
            if esc:
                cur.append(c); esc = False
            elif c == '\\':
                esc = True
            elif c == "'":
                in_str = False
            else:
                cur.append(c)
        else:
            if c == "'":
                in_str = True
            elif c == ',':
                fields.append(''.join(cur).strip()); cur = []
            else:
                cur.append(c)
    fields.append(''.join(cur).strip())
    return [f.strip("'") if f.startswith("'") else f for f in fields]


def parse_table(text, table_name):
    start = text.index(f"CREATE TABLE `{table_name}`")
    # Table section ends at the next CREATE TABLE.
    m = re.search(r"\nCREATE TABLE `", text[start + 20:])
    end = start + 20 + m.start() if m else len(text)
    section = text[start:end]
    rows = []
    for m in re.finditer(rf"INSERT INTO `{table_name}`[^\n]*VALUES\s*\n?", section):
        rest = section[m.end():]
        stop = rest.index(';\n') if ';\n' in rest else len(rest)
        for t in parse_tuples(rest[:stop]):
            rows.append(split_fields(t))
    return rows


def load_sql():
    print(f"Reading {SQL_PATH} (latin1) …")
    text = open(SQL_PATH, encoding='latin1').read()

    print("Parsing brev …")
    brev_rows = parse_table(text, "brev")
    by_date = {}
    for r in brev_rows:
        bid, dato = r[0], r[1]
        by_date.setdefault(dato, []).append(bid)
    print(f"  {len(brev_rows)} letters, {len(by_date)} distinct dates")

    print("Parsing brev_person …")
    bp_rows = parse_table(text, "brev_person")
    rel_by_brevid = {}
    for r in bp_rows:
        bid, pid, rel = r[0], r[1], r[2]
        rel_by_brevid.setdefault(bid, []).append((pid, rel))
    print(f"  {len(bp_rows)} sender/recipient links")

    print("Parsing person …")
    # brev_person.PersonID links to the main `person` table (Fornavn/
    # Efternavn), NOT `brevperson` (a different, letter-provenance-
    # specific person table with its own unrelated ID space) -- confirmed
    # directly: PersonID=1 must resolve to H. C. Andersen himself (every
    # letter's implicit other party), and only `person` has that row.
    person_rows = parse_table(text, "person")
    name_by_pid = {r[0]: f"{r[1]} {r[2]}".strip() for r in person_rows}
    print(f"  {len(person_rows)} named persons")

    return by_date, rel_by_brevid, name_by_pid


def surname_tokens(person_field):
    """From the PDF heading's person field (e.g. 'E. Collin', 'Henriette
    Collin', 'E. og Henriette Collin') -> the surname-ish tokens to look
    for in a Brevbasen name, case-insensitive."""
    return set(re.findall(r"[A-Za-zÆØÅæøå]+", person_field.lower()))


def pick_candidate(brevids, rel_by_brevid, name_by_pid, person_field):
    """Disambiguate same-date candidates by sender/recipient NAME overlap
    with the PDF heading's person field -- never by letter text."""
    if len(brevids) == 1:
        return brevids[0], "unique_date"
    want = surname_tokens(person_field)
    scored = []
    for bid in brevids:
        names = [name_by_pid.get(pid, "") for pid, _rel in rel_by_brevid.get(bid, [])]
        got = set()
        for nm in names:
            got |= surname_tokens(nm)
        overlap = len(want & got)
        scored.append((overlap, bid, "; ".join(n for n in names if n)))
    scored.sort(key=lambda x: -x[0])
    if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1], f"disambiguated_by_person (matched: {scored[0][2]})"
    return None, f"ambiguous ({len(brevids)} candidates share this date, no unique person match)"


def main():
    by_date, rel_by_brevid, name_by_pid = load_sql()

    with open(LETTER_PAGES_CSV, encoding="utf-8") as f:
        letters = list(csv.DictReader(f))

    by_vol = {}
    for l in letters:
        by_vol.setdefault(l["volume"], []).append(l)

    calibration = []
    attempted = []
    for vol, vol_letters in sorted(by_vol.items()):
        dated = [l for l in vol_letters if l["dateline_iso"]]
        n = len(dated)
        # Start from 5 evenly-spaced target positions, but a same-date
        # collision with an unrelated letter elsewhere in the whole
        # database (13,585 letters, not just this correspondence) is
        # common enough that aiming for exactly 5 fixed picks leaves
        # several volumes short -- see match_note on the "ambiguous"
        # rows this produces regardless, which stay in the CSV as
        # evidence of *why* a slot needed a replacement, not hidden.
        target_idxs = sorted(set(int(round(i * (n - 1) / 4)) for i in range(5))) if n else []
        pool_order = target_idxs + [i for i in range(n) if i not in target_idxs]

        resolved_for_vol = []
        for i in pool_order:
            if len(resolved_for_vol) >= 5:
                break
            l = dated[i]
            candidates = by_date.get(l["dateline_iso"], [])
            bid, note = (None, "no brevbasen row for this date") if not candidates else \
                pick_candidate(candidates, rel_by_brevid, name_by_pid, l["person"])
            row = {**l, "brevid": bid or "", "match_note": note,
                   "candidate_count": len(candidates)}
            attempted.append(row)
            if bid:
                resolved_for_vol.append(row)
        calibration.extend(resolved_for_vol)

    os.makedirs(os.path.dirname(OUT_CALIBRATION), exist_ok=True)
    with open(OUT_CALIBRATION, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(calibration[0].keys()))
        w.writeheader()
        w.writerows(calibration)
    print(f"\nwrote {os.path.relpath(OUT_CALIBRATION, ROOT)}  ({len(calibration)} calibration rows)")
    resolved = [c for c in calibration if c["brevid"]]
    print(f"  {len(resolved)}/{len(calibration)} resolved to a BrevID")

    out_review = os.path.join(ROOT, "data", "curated", "collin_letter_id_calibration_review.csv")
    failed = [a for a in attempted if not a["brevid"]]
    with open(out_review, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(attempted[0].keys()))
        w.writeheader()
        w.writerows(failed)
    print(f"wrote {os.path.relpath(out_review, ROOT)}  ({len(failed)} attempted-but-unresolved rows, "
          f"for transparency on which slots needed a replacement pick and why)")

    # Same-date collision check: two DIFFERENT letters (different
    # letter_no) that share a printed date and both resolved to the SAME
    # BrevID via "unique_date" -- that label means unique among brev's
    # rows for that date, not unique among this calibration sample, so
    # at least one of the pair is wrong whenever this happens. Flagged
    # here rather than left silently presented as equally confident;
    # excluded from the per-volume fit below since a duplicate y-value
    # would bias the interpolation.
    brevid_seen = {}
    for c in calibration:
        brevid_seen.setdefault((c["volume"], c["brevid"]), []).append(c["letter_no"])
    for c in calibration:
        dupes = brevid_seen.get((c["volume"], c["brevid"]), [])
        if len(dupes) > 1:
            c["match_note"] += f" [COLLISION: letters {', '.join(dupes)} share this date/BrevID -- at least one is wrong]"

    # Per-volume linear fit: sequence position (letter_no, numeric) -> BrevID.
    print("\nPer-volume calibration check (letter_no vs BrevID, should trend together):")
    fits = {}
    for vol in sorted(by_vol.keys()):
        pts = [(int(c["letter_no"]), int(c["brevid"])) for c in calibration
               if c["volume"] == vol and c["brevid"] and c["letter_no"].isdigit()
               and len(brevid_seen.get((vol, c["brevid"]), [])) == 1]
        print(f"  vol {vol}: {pts}")
        if len(pts) >= 2:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            n = len(pts)
            mean_x, mean_y = sum(xs) / n, sum(ys) / n
            cov = sum((x - mean_x) * (y - mean_y) for x, y in pts)
            var = sum((x - mean_x) ** 2 for x in xs)
            slope = cov / var if var else 0
            intercept = mean_y - slope * mean_x
            fits[vol] = (slope, intercept)
        elif len(pts) == 1:
            fits[vol] = (0, pts[0][1])

    full_rows = []
    for l in letters:
        row = dict(l)
        vol = l["volume"]
        cal = next((c for c in calibration if c["volume"] == vol and c["letter_no"] == l["letter_no"]), None)
        if cal and cal["brevid"]:
            row["estimated_brevid"] = cal["brevid"]
            row["estimate_source"] = "calibration_sample"
        elif l["letter_no"].isdigit() and vol in fits:
            slope, intercept = fits[vol]
            row["estimated_brevid"] = str(round(slope * int(l["letter_no"]) + intercept))
            row["estimate_source"] = "interpolated"
        else:
            row["estimated_brevid"] = ""
            row["estimate_source"] = "no_estimate"
        full_rows.append(row)

    with open(OUT_FULL, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(full_rows[0].keys()))
        w.writeheader()
        w.writerows(full_rows)
    print(f"\nwrote {os.path.relpath(OUT_FULL, ROOT)}  ({len(full_rows)} rows)")


if __name__ == "__main__":
    main()
