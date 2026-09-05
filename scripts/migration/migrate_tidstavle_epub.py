"""migrate_tidstavle_epub.py — Phase 6: extract Tidstavle content from
hcadag-20240911.epub (Input A) as supplementary CSVs.

The epub contains a published condensed timeline (168 events, DA only) plus
5 editorial narrative paragraphs that have no equivalent in the SQL database.
Both are extracted as supplements to the Phase 3 SQL-derived CSVs; they do
not replace timeline.csv.

Produces two CSV files in data/normalized_v092/:
  timeline_epub_events.csv     — 168 curated events (DA only, dated)
  timeline_epub_narratives.csv — 5 editorial narrative paragraphs

Usage:
  python scripts/migration/migrate_tidstavle_epub.py [--epub PATH] [--out DIR]
"""

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EPUB = REPO_ROOT.parent / "hca_db_export" / "diary-data" / "hcadag-20240911.epub"
DEFAULT_OUT  = REPO_ROOT / "data" / "normalized_v092"

# The 10 Tidstavle sections in reading order (from epub nav).
# Each tuple: (xhtml filename, nav label, section start year)
SECTIONS = [
    ("hcadag01_031_XXXI.xhtml", "Tidstavle 1825-1834", 1825),
    ("hcadag02_012_XII.xhtml",  "Tidstavle 1836-1844", 1836),
    ("hcadag03_013_XIII.xhtml", "Tidstavle 1845-1850", 1845),
    ("hcadag04_013_XIII.xhtml", "Tidstavle 1851-1860", 1851),
    ("hcadag05_012_XII.xhtml",  "Tidstavle 1861-1863", 1861),
    ("hcadag06_009_IX.xhtml",   "Tidstavle 1864-1865", 1864),
    ("hcadag07_009_IX.xhtml",   "Tidstavle 1866-1867", 1866),
    ("hcadag08_010_X.xhtml",    "Tidstavle 1868-1870", 1868),
    ("hcadag09_008_VIII.xhtml", "Tidstavle 1871-1872", 1871),
    ("hcadag10_012_XII.xhtml",  "Tidstavle 1873-1875", 1873),
]

EVENT_FIELDS = [
    "seq", "year_inferred", "date_raw", "text_da",
    "section_label", "source_file",
]
NARRATIVE_FIELDS = [
    "seq", "section_label", "year_context", "text_da", "source_file",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("\n", " ").strip()


def read_xhtml(epub_zip: zipfile.ZipFile, fname: str) -> str:
    """Read one EPUB/… xhtml file from the zip."""
    for name in epub_zip.namelist():
        if name.endswith(fname):
            return epub_zip.read(name).decode("utf-8")
    raise FileNotFoundError(f"{fname} not found in epub")


def infer_year_from_date(date_raw: str, fallback: int) -> int:
    """Extract explicit year from date string; return fallback if absent."""
    m = re.search(r"\b(1[89]\d{2})\b", date_raw)
    if m:
        return int(m.group(1))
    return fallback


# ---------------------------------------------------------------------------
# Section parser
# ---------------------------------------------------------------------------

def parse_section(epub_zip: zipfile.ZipFile,
                  fname: str, section_label: str, section_start_year: int):
    """Parse one Tidstavle xhtml section.

    Returns (events, narratives) where each item is a dict.
    Year assignment:
      1. Explicit four-digit year in the date string wins.
      2. Last-seen <header><i>YYYY</i></header> within the section.
      3. Section start year as final fallback.
    """
    html = read_xhtml(epub_zip, fname)
    main_m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL)
    if not main_m:
        return [], []
    main = main_m.group(1)

    events: list[dict] = []
    narratives: list[dict] = []
    current_year = section_start_year

    # Split into tokens so we preserve ordering.
    tokens = re.split(
        r"(<header>.*?</header>|<table>.*?</table>|<p\s+class=\"p\">.*?</p>)",
        main, flags=re.DOTALL,
    )
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue

        year_m = re.match(r"<header><i>(\d{4})</i></header>", tok)
        if year_m:
            current_year = int(year_m.group(1))
            continue

        if tok.startswith("<table>"):
            for tr in re.finditer(r"<tr>(.*?)</tr>", tok, re.DOTALL):
                tds = re.findall(r"<td>(.*?)</td>", tr.group(1), re.DOTALL)
                if len(tds) >= 2:
                    date_raw = strip_tags(tds[0])
                    year_inferred = infer_year_from_date(date_raw, current_year)
                    events.append({
                        "year_inferred": year_inferred,
                        "date_raw":      date_raw,
                        "text_da":       strip_tags(tds[1]),
                        "section_label": section_label,
                        "source_file":   fname,
                    })
            continue

        if tok.startswith("<p"):
            text = strip_tags(tok)
            if text:
                narratives.append({
                    "section_label": section_label,
                    "year_context":  current_year,
                    "text_da":       text,
                    "source_file":   fname,
                })

    return events, narratives


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epub", default=str(DEFAULT_EPUB))
    ap.add_argument("--out",  default=str(DEFAULT_OUT))
    args = ap.parse_args()

    epub_path = Path(args.epub)
    out_dir   = Path(args.out)
    if not epub_path.exists():
        sys.exit(f"epub not found: {epub_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {epub_path} …", flush=True)

    all_events:     list[dict] = []
    all_narratives: list[dict] = []

    with zipfile.ZipFile(epub_path) as z:
        for fname, label, start_year in SECTIONS:
            evts, narrs = parse_section(z, fname, label, start_year)
            all_events.extend(evts)
            all_narratives.extend(narrs)
            print(f"  {label}: {len(evts)} events, {len(narrs)} narratives")

    # Assign global sequence numbers
    for i, e in enumerate(all_events, 1):
        e["seq"] = i
    for i, n in enumerate(all_narratives, 1):
        n["seq"] = i

    print(f"\nTotal: {len(all_events)} events, {len(all_narratives)} narratives")

    # Year distribution
    from collections import Counter
    yd = Counter(e["year_inferred"] for e in all_events)
    print(f"Year distribution: { {y: yd[y] for y in sorted(yd)} }")

    evt_path  = out_dir / "timeline_epub_events.csv"
    narr_path = out_dir / "timeline_epub_narratives.csv"

    write_csv(evt_path,  EVENT_FIELDS,     all_events)
    write_csv(narr_path, NARRATIVE_FIELDS, all_narratives)

    print("\n[OUTPUT]")
    print(f"  {evt_path}  ({len(all_events)} rows)")
    print(f"  {narr_path}  ({len(all_narratives)} rows)")
    print("\nPhase 6 complete.")


if __name__ == "__main__":
    main()
