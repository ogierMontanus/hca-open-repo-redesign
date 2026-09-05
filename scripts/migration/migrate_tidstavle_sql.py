"""migrate_tidstavle_sql.py — Phase 3: migrate Tidstavle tables from
hca_db.sql (Input B) into Target C normalized CSVs.

Produces three CSV files in data/normalized_v092/:
  timeline.csv               — 1,446 biographical timeline events
  timeline_subjects.csv      — 213 thematic subjects (controlled vocabulary)
  timeline_subject_links.csv — 2,087 event ↔ subject links (1 null row filtered)

Usage:
  python scripts/migration/migrate_tidstavle_sql.py [--sql PATH] [--out DIR]

SQL encoding: utf-8 (actual content despite latin-1 header in dump).
"""

import argparse
import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQL = REPO_ROOT.parent / "hca_db_export" / "hca_db.sql"
DEFAULT_OUT = REPO_ROOT / "data" / "normalized_v092"


# ---------------------------------------------------------------------------
# SQL extractor — handles semicolons inside string values
# ---------------------------------------------------------------------------

def extract_insert_blocks(sql_text: str, table_name: str) -> list[str]:
    """Return a list of VALUES-block strings for the given table.

    Uses a state-machine scan so that semicolons inside string values
    do not prematurely terminate the INSERT block.
    """
    marker = f"INSERT INTO `{table_name}`"
    blocks = []
    pos = 0
    while True:
        start = sql_text.find(marker, pos)
        if start < 0:
            break
        # Find the VALUES keyword
        v_idx = sql_text.find("VALUES", start + len(marker))
        if v_idx < 0:
            break
        # State-machine scan for the terminating ';' (outside strings)
        i = v_idx + len("VALUES")
        in_string = False
        while i < len(sql_text):
            c = sql_text[i]
            if in_string:
                if c == '\\' and i + 1 < len(sql_text):
                    i += 2  # skip escaped character
                    continue
                if c == "'":
                    in_string = False
            else:
                if c == "'":
                    in_string = True
                elif c == ";":
                    break
            i += 1
        # Everything between VALUES and the ';' is the values block
        blocks.append(sql_text[v_idx + len("VALUES"):i].strip())
        pos = i + 1
    return blocks


# ---------------------------------------------------------------------------
# MySQL VALUES row parser — state machine
# ---------------------------------------------------------------------------

def _unescape(s: str) -> str:
    """Unescape MySQL backslash sequences in a string already stripped of
    surrounding quotes."""
    return (s
            .replace("\\'",  "'")
            .replace('\\"',  '"')
            .replace("\\\\", "\\")
            .replace("\\r",  "\r")
            .replace("\\n",  "\n")
            .replace("\\t",  "\t")
            .replace("\\0",  ""))


def parse_mysql_rows(values_block: str) -> list[list[str]]:
    """State-machine parser for a MySQL VALUES block.

    Handles: multi-line strings, \\ \\' \\" escapes, NULL, numbers.
    Returns list of rows, each row a list of string values (None for SQL NULL).
    """
    rows = []
    i = 0
    n = len(values_block)

    def skip_ws() -> None:
        nonlocal i
        while i < n and values_block[i] in ' \t\r\n':
            i += 1

    while i < n:
        skip_ws()
        if i >= n:
            break
        if values_block[i] != '(':
            i += 1
            continue

        i += 1  # consume '('
        row: list[str] = []

        while True:
            skip_ws()
            if i >= n:
                break

            ch = values_block[i]

            if ch == "'":
                # Quoted string
                i += 1
                buf: list[str] = []
                while i < n:
                    c = values_block[i]
                    if c == '\\' and i + 1 < n:
                        nxt = values_block[i + 1]
                        escape_map = {
                            "'": "'", '\\': '\\', 'r': '\r', 'n': '\n',
                            't': '\t', '"': '"', '0': '\x00', 'b': '\x08',
                            'Z': '\x1a',
                        }
                        buf.append(escape_map.get(nxt, nxt))
                        i += 2
                    elif c == "'":
                        i += 1
                        break
                    else:
                        buf.append(c)
                        i += 1
                row.append(''.join(buf))

            elif values_block[i:i+4].upper() == 'NULL':
                row.append('')
                i += 4

            else:
                # Numeric or bare value
                j = i
                while i < n and values_block[i] not in (',', ')', ' ', '\t', '\r', '\n'):
                    i += 1
                row.append(values_block[j:i])

            skip_ws()
            if i < n and values_block[i] == ',':
                i += 1        # field separator
            elif i < n and values_block[i] == ')':
                i += 1        # end of row
                break
            else:
                break         # unexpected — end row defensively

        rows.append(row)

    return rows


def parse_table(sql_text: str, table_name: str) -> list[list[str]]:
    """Extract and parse all rows for *table_name*."""
    rows: list[list[str]] = []
    for block in extract_insert_blocks(sql_text, table_name):
        rows.extend(parse_mysql_rows(block))
    return rows


# ---------------------------------------------------------------------------
# Data transformation
# ---------------------------------------------------------------------------

def build_aar_index(aar_rows: list[list[str]]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for row in aar_rows:
        if len(row) < 4:
            continue
        idx[row[1].strip()] = {
            "year_heading_da": row[2],
            "year_heading_en": row[3],
        }
    return idx


def transform_data(data_rows: list[list[str]],
                   aar_idx: dict[str, dict]) -> list[dict]:
    events: list[dict] = []
    for row in data_rows:
        if len(row) < 13:
            continue
        raw_id   = row[0].strip()
        year     = row[1].strip()
        quarter  = row[2].strip() if row[2].strip() in ("1","2","3","4") else ""
        dato     = row[3].strip()
        placing  = row[4].strip()
        titel_da = row[5].strip()
        tekst_da = row[6].strip()
        titel_en = row[7].strip()
        tekst_en = row[8].strip()
        bogm_da  = row[10].strip()
        bogm_en  = row[11].strip()
        gl_bogm  = row[12].strip()

        date_iso = "" if dato in ("0000-00-00", "") else dato
        year_info = aar_idx.get(year, {})

        events.append({
            "event_id":          f"T{int(raw_id):04d}",
            "year":              year,
            "quarter":           quarter,
            "date_iso":          date_iso,
            "ordering":          placing,
            "title_da":          titel_da,
            "title_en":          titel_en,
            "text_da":           tekst_da,
            "text_en":           tekst_en,
            "bookmark_title_da": bogm_da,
            "bookmark_title_en": bogm_en,
            "legacy_slug":       gl_bogm,
            "year_heading_da":   year_info.get("year_heading_da", ""),
            "year_heading_en":   year_info.get("year_heading_en", ""),
            "source_id":         raw_id,
        })
    return events


def transform_subjects(emner_rows: list[list[str]]) -> list[dict]:
    subjects: list[dict] = []
    for row in emner_rows:
        if len(row) < 6:
            continue
        raw_id = row[0].strip()
        subjects.append({
            "subject_id": f"S{int(raw_id):04d}",
            "subject_da": row[1].strip(),
            "subject_en": row[2].strip(),
            "group_da":   row[4].strip(),
            "group_en":   row[5].strip(),
            "source_id":  raw_id,
        })
    return subjects


def transform_links(rel_rows: list[list[str]]) -> list[dict]:
    links: list[dict] = []
    for row in rel_rows:
        if len(row) < 3:
            continue
        did = row[1].strip()
        eid = row[2].strip()
        try:
            d, e = int(did), int(eid)
        except ValueError:
            continue
        if d == 0 or e == 0:
            continue  # orphan null row (source ID 1414 in rel table)
        links.append({
            "event_id":   f"T{d:04d}",
            "subject_id": f"S{e:04d}",
        })
    return links


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

TIMELINE_FIELDS = [
    "event_id", "year", "quarter", "date_iso", "ordering",
    "title_da", "title_en", "text_da", "text_en",
    "bookmark_title_da", "bookmark_title_en", "legacy_slug",
    "year_heading_da", "year_heading_en", "source_id",
]
SUBJECT_FIELDS  = ["subject_id", "subject_da", "subject_en",
                    "group_da", "group_en", "source_id"]
LINK_FIELDS     = ["event_id", "subject_id"]


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def validate(events: list[dict],
             subjects: list[dict],
             links: list[dict]) -> list[str]:
    issues: list[str] = []
    event_ids   = {e["event_id"] for e in events}
    subject_ids = {s["subject_id"] for s in subjects}

    missing_e = {l["event_id"]   for l in links if l["event_id"]   not in event_ids}
    missing_s = {l["subject_id"] for l in links if l["subject_id"] not in subject_ids}
    if missing_e:
        issues.append(
            f"Links reference {len(missing_e)} non-existent events "
            f"(first 10: {sorted(missing_e)[:10]})")
    if missing_s:
        issues.append(
            f"Links reference {len(missing_s)} non-existent subjects "
            f"(first 10: {sorted(missing_s)[:10]})")

    no_text = [e["event_id"] for e in events if not e["text_da"] and not e["text_en"]]
    if no_text:
        issues.append(f"Events with no text: {no_text}")

    ungrouped = [s["subject_id"] for s in subjects if not s["group_da"]]
    if ungrouped:
        issues.append(
            f"{len(ungrouped)} subjects without a group (top-level — expected): "
            f"{ungrouped[:5]}…")

    return issues


# ---------------------------------------------------------------------------
# Mapping summary (printed to stdout)
# ---------------------------------------------------------------------------

def print_mapping_summary() -> None:
    print("""
── FIELD MAPPING: Input B → Target C ──────────────────────────────────────

tidstavle_aar (65 rows):
  ID         → (join key, not stored in output)
  Aar        → timeline.year  (denormalized into each event)
  Manchet    → timeline.year_heading_da
  Manchet_e  → timeline.year_heading_en
  Timestamp  → discarded (system metadata)

tidstavle_data (1,446 rows → timeline.csv):
  ID         → event_id  T{ID:04d}
  Aar        → year
  Kvartal    → quarter   (1-4; '5' mapped to empty — non-standard value)
  Dato       → date_iso  (0000-00-00 → empty)
  Placering  → ordering  (display order within year)
  Titel      → title_da  (section title DA; often empty)
  Tekst      → text_da   (event narrative DA)
  Titel_e    → title_en  (section title EN; often empty)
  Tekst_e    → text_en   (event narrative EN)
  Timestamp  → discarded
  Bogm_titel → bookmark_title_da
  Bogm_titel_e → bookmark_title_en
  gl_bogm    → legacy_slug  (old URL anchor; preserved for provenance)

tidstavle_emner (213 rows → timeline_subjects.csv):
  ID         → subject_id  S{ID:04d}
  Titel      → subject_da
  Titel_e    → subject_en
  Gruppe     → group_da
  Gruppe_e   → group_en
  Timestamp  → discarded

tidstavle_rel (2,088 rows → timeline_subject_links.csv; 1 null row filtered):
  ID         → discarded (surrogate key)
  DID        → event_id   (FK → tidstavle_data.ID → T{DID:04d})
  EID        → subject_id (FK → tidstavle_emner.ID → S{EID:04d})
  Timestamp  → discarded

UNMAPPED / DOCUMENTED DIFFERENCES:
  • Kvartal='5' appears in some rows (biographical appendix entries for 1805).
    These rows describe family members and use a non-standard quarter value.
    Mapped to quarter='' with ordering preserved.
  • tidstavle_data spans IDs 1–1489 (1,446 rows); all rows have 13 columns.
  • tidstavle_rel row 1414 has DID=0 EID=0 (null/orphan row); filtered out.
  • No equivalent of tidstavle_aar as a standalone entity in Target C;
    year headings are denormalized into each event row for flat-file
    consumption without joins.
──────────────────────────────────────────────────────────────────────────
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sql", default=str(DEFAULT_SQL))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--report-only", action="store_true",
                    help="Print mapping and validation without writing CSVs")
    args = ap.parse_args()

    sql_path = Path(args.sql)
    out_dir  = Path(args.out)

    if not sql_path.exists():
        sys.exit(f"SQL file not found: {sql_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {sql_path} …", flush=True)
    sql_text = sql_path.read_text(encoding="utf-8")

    for tbl in ("tidstavle_aar", "tidstavle_data", "tidstavle_emner", "tidstavle_rel"):
        rows = parse_table(sql_text, tbl)
        print(f"  {tbl}: {len(rows)} rows", flush=True)

    print("\nParsing …", flush=True)
    aar_rows   = parse_table(sql_text, "tidstavle_aar")
    data_rows  = parse_table(sql_text, "tidstavle_data")
    emner_rows = parse_table(sql_text, "tidstavle_emner")
    rel_rows   = parse_table(sql_text, "tidstavle_rel")

    col_dist = {}
    for r in data_rows:
        col_dist[len(r)] = col_dist.get(len(r), 0) + 1
    print(f"  tidstavle_data column distribution: {dict(sorted(col_dist.items()))}")

    print("\nTransforming …", flush=True)
    aar_idx  = build_aar_index(aar_rows)
    events   = transform_data(data_rows, aar_idx)
    subjects = transform_subjects(emner_rows)
    links    = transform_links(rel_rows)
    print(f"  {len(events)} events, {len(subjects)} subjects, {len(links)} links")

    print("\nValidating …", flush=True)
    issues = validate(events, subjects, links)
    if issues:
        print("[VALIDATION ISSUES]")
        for issue in issues:
            print(f"  ⚠  {issue}")
    else:
        print("  ✓ No structural issues.")

    print_mapping_summary()

    if args.report_only:
        print("[--report-only: no CSVs written]")
        return

    t_path  = out_dir / "timeline.csv"
    ts_path = out_dir / "timeline_subjects.csv"
    tl_path = out_dir / "timeline_subject_links.csv"

    write_csv(t_path,  TIMELINE_FIELDS, events)
    write_csv(ts_path, SUBJECT_FIELDS,  subjects)
    write_csv(tl_path, LINK_FIELDS,     links)

    print("[OUTPUT]")
    print(f"  {t_path}  ({len(events)} rows)")
    print(f"  {ts_path}  ({len(subjects)} rows)")
    print(f"  {tl_path}  ({len(links)} rows)")
    print("\nPhase 3 complete — pause here for user review (Phase 4).")


if __name__ == "__main__":
    main()
