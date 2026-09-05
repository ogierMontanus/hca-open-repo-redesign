#!/usr/bin/env python3
"""
parse_rejser_htm.py
-------------------
Parses data/raw/Rejser_HCA_X.htm (the geocoded travel table from
rejser.hcax.dk) and writes TSV files to data/normalized/:

  rejser.tsv           — flat travel table, one row per leg
  rejser_journeys.tsv  — per-journey metadata (title, dates, description)

Ignores embedded <img> elements (the rejsekort .jpg maps) per
docs/data-model/october-pipeline.md.

Stdlib only — no dependencies.
"""

import argparse
import csv
import os
import re
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTM_DEFAULT = os.path.join(ROOT, "data", "raw", "Rejser_HCA_X.htm")
OUT_DIR = os.path.join(ROOT, "data", "normalized")

DATA_HEADERS = [
    "RejseID",
    "DestinationType",
    "Destination_DA",
    "Destination_EN",
    "Destination_ORG",
    "ArrivalDate",
    "DepartureDate",
    "ArrivalMethod",
    "Latitude",
    "Longitude",
]

JOURNEY_HEADERS = [
    "RejseID",
    "Title",
    "YearRange",
    "Departure",
    "Return",
    "Description",
    "Countries",
    "Cost",
]


class RejserParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_tr = False
        self.in_cell = False
        self.cell_tag = None
        self.cell_text = []
        self.row_cells = []
        self.is_header_row = False
        self.is_travelinfo_row = False
        self.cell_classes = []
        self.rows_data = []
        self.rows_travelinfo = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_tr = True
            self.row_cells = []
            self.is_header_row = False
            self.is_travelinfo_row = "travelinfo" in attrs_d.get("class", "")
        elif tag in ("td", "th") and self.in_tr:
            self.in_cell = True
            self.cell_tag = tag
            self.cell_text = []
            if "travelinfo" in attrs_d.get("class", ""):
                self.is_travelinfo_row = True
            if tag == "th":
                self.is_header_row = True
        elif tag == "br" and self.in_cell:
            self.cell_text.append("\n")
        elif tag == "img":
            pass

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if not self.is_header_row and self.row_cells:
                if self.is_travelinfo_row:
                    self.rows_travelinfo.append(self.row_cells)
                else:
                    self.rows_data.append(self.row_cells)
        elif tag in ("td", "th") and self.in_cell:
            text = "".join(self.cell_text)
            text = re.sub(r"[ \t]+", " ", text).strip()
            self.row_cells.append(text)
            self.in_cell = False
            self.cell_tag = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell_text.append(data)


JOURNEY_LABEL_RE = re.compile(r"^Rejse\s+(\d+),\s*(.+)$")
LABEL_VALUE_RE = re.compile(r"^([A-ZÆØÅa-zæøå ]+):\s*(.*)$")


def parse_travelinfo(cell_text):
    """Pull Title, YearRange, Departure, Return, Description, Countries, Cost
    out of the multi-line content of a travelinfo cell."""
    lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
    meta = {
        "RejseID": "",
        "Title": "",
        "YearRange": "",
        "Departure": "",
        "Return": "",
        "Description": "",
        "Countries": "",
        "Cost": "",
    }
    for line in lines:
        m = JOURNEY_LABEL_RE.match(line)
        if m:
            meta["RejseID"] = m.group(1)
            meta["YearRange"] = m.group(2).strip()
            meta["Title"] = line
            continue
        m = LABEL_VALUE_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        if key == "afgang":
            meta["Departure"] = val
        elif key == "hjemkomst":
            meta["Return"] = val
        elif key == "beskrivelse":
            meta["Description"] = val
        elif key == "lande":
            meta["Countries"] = val
        elif key.startswith("samlet udgift"):
            meta["Cost"] = val
    return meta


def split_coords(s):
    s = (s or "").strip()
    if "," not in s:
        return "", ""
    a, b = s.split(",", 1)
    return a.strip(), b.strip()


def write_tsv(path, headers, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, delimiter="\t",
                           quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  Wrote {len(rows):,} rows → {os.path.relpath(path, ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--input", default=HTM_DEFAULT)
    args = ap.parse_args()

    print(f"Parsing {os.path.relpath(args.input, ROOT)}…")
    with open(args.input, encoding="utf-8") as f:
        html = f.read()

    p = RejserParser()
    p.feed(html)

    print(f"  {len(p.rows_data):,} data rows, "
          f"{len(p.rows_travelinfo):,} travelinfo rows")

    data_rows = []
    for cells in p.rows_data:
        if len(cells) < 9:
            continue
        rejse_id, dest_type, da, en, org, arr, dep, method, coords = cells[:9]
        lat, lon = split_coords(coords)
        data_rows.append({
            "RejseID": rejse_id.strip(),
            "DestinationType": dest_type.strip(),
            "Destination_DA": da.strip(),
            "Destination_EN": en.strip(),
            "Destination_ORG": org.strip(),
            "ArrivalDate": arr.strip(),
            "DepartureDate": dep.strip(),
            "ArrivalMethod": method.strip(),
            "Latitude": lat,
            "Longitude": lon,
        })

    journey_rows = []
    prev_id = None
    for cells in p.rows_travelinfo:
        text = "\n".join(cells)
        meta = parse_travelinfo(text)
        if not meta["RejseID"]:
            continue
        if meta["RejseID"] == prev_id:
            continue
        prev_id = meta["RejseID"]
        journey_rows.append(meta)

    write_tsv(os.path.join(OUT_DIR, "rejser.tsv"), DATA_HEADERS, data_rows)
    write_tsv(os.path.join(OUT_DIR, "rejser_journeys.tsv"), JOURNEY_HEADERS, journey_rows)


if __name__ == "__main__":
    main()
