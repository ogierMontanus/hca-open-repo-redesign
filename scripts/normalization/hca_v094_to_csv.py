#!/usr/bin/env python3
"""
hca_v094_to_csv.py — ingest the V0.94 release into normalized CSVs.

Reads data/raw/HCA REPOSITORY V0.94/ and writes data/normalized_v094/, which
**nothing consumes**. This is a verification surface, exactly as
data/normalized_v092/ is: ingest, measure against the live data, decide, and
only then let a stage depend on it. `--report` writes the structural diff.

V0.94 is not a version bump of V0.92. It is five renamed, numbered registries
plus a specification workbook, and it differs from its predecessor in three
ways that matter:

**The star schema is gone.** V0.92 shipped FactDiaPerPag, FactDiaLocPag and
FactDiaLocPerPag as real fact tables. V0.94 folds the references back into the
dimension rows as space-separated `VOL-PAGE` lists — `FKDiaryPagIDs` on works,
`FKPageKeys` on places. So they must be split and re-joined here, and there is
no per-reference ordering to recover: the `seq` column that V0.82's
references.csv carries cannot be reconstructed, only invented.

**Identifiers are half-carried.** Works keep `OLDWorkID`, which is the live
`Reg…` id and resolves completely. Places keep `OLDLocationID`, which is
V0.92's `LOC…` scheme and resolves to nothing in the live data. The
specification workbook explains why: it defines ids as "deterministic ID for
unique 3-tuple / 5-tuple" — derived from content rather than carried — and a
content-derived id cannot survive a typo being fixed.

**Persons are absent entirely**, though the specification names a `Personer`
table and cites 9,520 of them.

Every sheet puts its title in row 1, a description in row 2, a blank in row 3,
and the real header in row 4. Data starts at row 5.

Usage:
    python scripts/normalization/hca_v094_to_csv.py
    python scripts/normalization/hca_v094_to_csv.py --report docs/v094-structural-diff.md
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl required:  pip install openpyxl")

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "data" / "raw" / "HCA REPOSITORY V0.94"
DEFAULT_OUT = ROOT / "data" / "normalized_v094"
LIVE = ROOT / "data" / "normalized"

HEADER_ROW = 4          # rows 1-3 are title, description, blank
FIRST_DATA_ROW = 5

WORKBOOKS = {
    "sites":     "1-SITES.xlsx",
    "calendar":  "2-CALENDAR.xlsx",
    "pages":     "3-DIARY-PAGES.xlsx",
    "locations": "4-LOCATION-Registry.xlsx",
    "works":     "5-WORK-Registry.xlsx",
}

ENTITY_FIELDS = ["entity_id", "entity_type", "category_h1", "genre_h2",
                 "form_h3", "subform_h4", "label", "description", "see",
                 "see_also", "year_derived", "date_derived", "person_derived"]
REFERENCE_FIELDS = ["page_id", "entity_id", "entity_label", "vol", "page", "seq"]
PAGE_FIELDS = ["page_id", "vol", "page", "year", "month", "day",
               "kb_url", "source_status"]
CALENDAR_FIELDS = ["date_id", "precision_decade", "precision_year",
                   "precision_month", "day_number_1800", "year", "month_no",
                   "month_day_no", "month_text", "day_text", "quarter",
                   "week", "iso_week"]
CROSSWALK_FIELDS = ["v094_id", "legacy_id", "entity_type", "label", "resolves"]

ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}


def s(v):
    """Stringify a cell, treating None as empty."""
    return "" if v is None else str(v).strip()


def vol_to_int(vol) -> int:
    sv = s(vol).upper()
    if sv in ROMAN_TO_INT:
        return ROMAN_TO_INT[sv]
    try:
        return int(sv)
    except ValueError:
        return 0


def page_handle(vol, page) -> str:
    """The Pag handle the rest of the platform joins on."""
    try:
        p = int(page)
    except (TypeError, ValueError):
        p = 0
    return f"Pag{vol_to_int(vol):02d}{p:04d}"


def sheet(src: Path, key: str):
    """Yield (header, rows) for a V0.94 workbook's first sheet."""
    path = src / WORKBOOKS[key]
    if not path.exists():
        sys.exit(f"missing workbook: {path}")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(min_row=HEADER_ROW, values_only=True))
    wb.close()
    if not rows:
        sys.exit(f"{path.name}: no rows at or after row {HEADER_ROW}")
    # A trailing '*' marks a required field in this release's own convention
    # (see 1-SITES.xlsx). Strip it for matching, keep it in `required`.
    raw = [s(c) for c in rows[0]]
    header = [h.rstrip("*").strip() for h in raw]
    required = {h.rstrip("*").strip() for h in raw if h.endswith("*")}
    return header, [r for r in rows[1:] if any(c is not None for c in r)], required


def col(header, *names):
    """Index of the first matching column. V0.94 spells some fields
    unexpectedly ('WorkTittle', 'Sequense'), so accept alternatives."""
    for n in names:
        if n in header:
            return header.index(n)
    sys.exit(f"none of {names} found in header: {header}")


ROMAN_RE = __import__("re").compile(r"^(?:I{1,3}|IV|VI{0,3}|IX|X)$")


def _complete_range_end(start: str, end: str) -> str:
    """'407'+'09' -> '409';  '157'+'58' -> '158';  '64'+'65' -> '65'.

    The registers abbreviate the closing page of a range to its trailing
    digits, as printed indexes conventionally do. Rebuild it from the start
    page's prefix, and reject anything that does not then run forwards."""
    if len(end) >= len(start):
        return end
    return start[: len(start) - len(end)] + end


def split_keys(cell):
    """Expand one `FKDiaryPagIDs` / `FKPageKeys` cell into (vol, page) pairs.

    The whole reference model of V0.94 lives in these strings, and 3.4 % of
    the tokens in the release are not the clean `VOL-PAGE` the name promises.
    Returns (pairs, problems) so the caller can count what it could not read
    rather than silently dropping — or, worse, silently misreading — it.

    Four token shapes occur:

      III-64        clean, 27,851 of them
      IX-64-65      a page range, 763. Naive right-splitting reads this as
                    volume "IX-64", page "65" — a silent corruption, which is
                    why ranges are expanded here rather than tolerated.
      VIII          a bare volume, 151. Whitespace was injected inside the
                    numeral upstream, so "VII-241" arrives as "VI" + "I-241".
                    Unrecoverable without guessing; reported.
      O-235         a mangled volume, 68. OCR damage ("O" for a numeral, "l"
                    for "1"). Reported.
    """
    pairs, problems = [], []
    for tok in s(cell).split():
        parts = tok.split("-")
        vol = parts[0]
        if not ROMAN_RE.match(vol):
            problems.append(("bare volume" if len(parts) == 1 else "bad volume", tok))
            continue
        nums = parts[1:]
        if not nums or not all(n.isdigit() for n in nums):
            problems.append(("non-numeric page", tok))
            continue
        if len(nums) == 1:
            pairs.append((vol, nums[0]))
        elif len(nums) == 2:
            start = nums[0]
            end = _complete_range_end(start, nums[1])
            if not end.isdigit() or int(end) < int(start) or int(end) - int(start) > 50:
                problems.append(("implausible range", tok))
                continue
            pairs.extend((vol, str(p)) for p in range(int(start), int(end) + 1))
        else:
            problems.append(("too many parts", tok))
    return pairs, problems


# ── builders ────────────────────────────────────────────────────────────────

def build_works(src):
    header, rows, req = sheet(src, "works")
    ix = {k: col(header, *v) for k, v in {
        "id": ("WorkID",), "title": ("WorkTittle", "WorkTitle"),
        "seq": ("Sequense", "Sequence"), "h1": ("TypeH1",),
        "h2": ("GenreH2",), "h3": ("FormH3",), "h4": ("SubFormH4",),
        "see": ("See",), "see_also": ("See also", "SeeAlso"),
        "artist": ("Artist",), "museum": ("MuseumEtc",), "city": ("City",),
        "status": ("SourceStatus",), "fk": ("FKDiaryPagIDs",),
        "old": ("OLDWorkID",),
    }.items()}

    ents, refs, walk, problems = [], [], [], []
    for r in rows:
        wid, old = s(r[ix["id"]]), s(r[ix["old"]])
        label = s(r[ix["title"]])
        # description carries what the live register buries in the label
        desc = " · ".join(x for x in (s(r[ix["artist"]]), s(r[ix["museum"]]),
                                      s(r[ix["city"]])) if x)
        ents.append({
            "entity_id": wid, "entity_type": "work",
            "category_h1": s(r[ix["h1"]]), "genre_h2": s(r[ix["h2"]]),
            "form_h3": s(r[ix["h3"]]), "subform_h4": s(r[ix["h4"]]),
            "label": label, "description": desc,
            "see": s(r[ix["see"]]), "see_also": s(r[ix["see_also"]]),
            "year_derived": "", "date_derived": "",
            "person_derived": s(r[ix["artist"]]),
        })
        walk.append({"v094_id": wid, "legacy_id": old, "entity_type": "work",
                     "label": label, "resolves": ""})
        pairs, probs = split_keys(r[ix["fk"]])
        for kind, tok in probs:
            problems.append({"entity_id": wid, "entity_type": "work",
                             "label": label, "kind": kind, "token": tok})
        for seq, (vol, page) in enumerate(pairs, 1):
            refs.append({"page_id": page_handle(vol, page), "entity_id": wid,
                         "entity_label": label, "vol": vol, "page": page,
                         "seq": seq})
    return ents, refs, walk, problems, rows, ix, header, req


def build_locations(src):
    header, rows, req = sheet(src, "locations")
    ix = {k: col(header, *v) for k, v in {
        "id": ("LocationID",), "label": ("Location",), "h1": ("TypeH1",),
        "country": ("Country",), "category": ("Category",),
        "lat": ("Latitude",), "lon": ("Longitude",),
        "status": ("SourceStatus",), "fk": ("FKPageKeys",),
        "old": ("OLDLocationID",),
    }.items()}

    ents, refs, walk, problems = [], [], [], []
    for r in rows:
        lid, old = s(r[ix["id"]]), s(r[ix["old"]])
        label = s(r[ix["label"]])
        lat, lon = s(r[ix["lat"]]), s(r[ix["lon"]])
        ents.append({
            "entity_id": lid, "entity_type": "place",
            "category_h1": s(r[ix["h1"]]), "genre_h2": s(r[ix["category"]]),
            "form_h3": "", "subform_h4": "",
            "label": label, "description": s(r[ix["country"]]),
            "see": "", "see_also": "",
            "year_derived": "", "date_derived": "",
            # same convention as the V0.92 ingester: coords ride here
            "person_derived": f"{lat},{lon}" if lat and lon else "",
        })
        walk.append({"v094_id": lid, "legacy_id": old, "entity_type": "place",
                     "label": label, "resolves": ""})
        pairs, probs = split_keys(r[ix["fk"]])
        for kind, tok in probs:
            problems.append({"entity_id": lid, "entity_type": "place",
                             "label": label, "kind": kind, "token": tok})
        for seq, (vol, page) in enumerate(pairs, 1):
            refs.append({"page_id": page_handle(vol, page), "entity_id": lid,
                         "entity_label": label, "vol": vol, "page": page,
                         "seq": seq})
    return ents, refs, walk, problems, rows, ix, header, req


def build_pages(src):
    header, rows, req = sheet(src, "pages")
    ix = {k: col(header, *v) for k, v in {
        "id": ("DiaryPagID",), "vol": ("Volumen",), "page": ("Page",),
        "year": ("Year",), "month": ("Month",), "day": ("Day",),
        "kb": ("KBLinkString",), "status": ("SourceStatus",),
    }.items()}
    out = []
    for r in rows:
        vol, page = s(r[ix["vol"]]), s(r[ix["page"]])
        out.append({
            "page_id": page_handle(vol, page), "vol": vol, "page": page,
            "year": s(r[ix["year"]]), "month": s(r[ix["month"]]),
            "day": s(r[ix["day"]]), "kb_url": s(r[ix["kb"]]),
            "source_status": s(r[ix["status"]]),
        })
    return out, rows, ix, header, req


def build_calendar(src):
    header, rows, req = sheet(src, "calendar")
    out = []
    for r in rows:
        vals = [s(c) for c in r[:len(CALENDAR_FIELDS)]]
        vals += [""] * (len(CALENDAR_FIELDS) - len(vals))
        out.append(dict(zip(CALENDAR_FIELDS, vals)))
    return out, header, req


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)}  ({len(rows):,} rows)")


# ── structural diff ─────────────────────────────────────────────────────────

def load_live():
    """The live entities and references, for measuring against."""
    ents, refs = {}, []
    ep, rp = LIVE / "entities.csv", LIVE / "references.csv"
    if ep.exists():
        with ep.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ents[row["entity_id"]] = row
    if rp.exists():
        with rp.open(encoding="utf-8") as f:
            refs = [(r["entity_id"], r["vol"], r["page"]) for r in csv.DictReader(f)]
    return ents, refs


# A bare 0 is used as a "no value" placeholder in a handful of cells. It
# stringifies to a non-empty "0", so counting it as data overstates coverage.
PLACEHOLDERS = {"", "0", "-", "(blank)", "n/a"}


def fill_rate(rows, ix, key):
    good = ph = 0
    for r in rows:
        v = s(r[ix[key]])
        if v in PLACEHOLDERS:
            if v and v != "":
                ph += 1
        else:
            good += 1
    return good, len(rows), ph


def report(dest, src, data):
    live_ents, live_refs = load_live()
    L = []
    A = L.append

    A("# V0.94 — structural diff\n")
    A("Generated by `scripts/normalization/hca_v094_to_csv.py --report`.\n")
    A(f"Source: `{src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}`\n")
    A("Nothing consumes `data/normalized_v094/`. This measures what adopting "
      "V0.94 would gain and cost, per entity type, so the decision is made on "
      "numbers rather than on the release notes.\n")

    # ── counts
    A("## Row counts against the live data\n")
    live_by_type = Counter(r["entity_type"] for r in live_ents.values())
    A("| Entity | V0.94 | live (`entities.csv`) | delta |")
    A("|---|---:|---:|---:|")
    for label, key, n in (("Works", "work", len(data["work_ents"])),
                          ("Places", "place", len(data["loc_ents"])),
                          ("Persons", "person", 0)):
        lv = live_by_type.get(key, 0)
        note = f"{n - lv:+,}" if n else "**absent from V0.94**"
        A(f"| {label} | {n:,} | {lv:,} | {note} |")
    A(f"| Diary pages | {len(data['pages']):,} | — | 10 volumes |")
    A(f"| Calendar rows | {len(data['calendar']):,} | — | — |\n")

    # ── crosswalk
    A("## Identifier crosswalk\n")
    A("Whether V0.94's `OLD…ID` columns reach the ids the live site uses.\n")
    A("| Entity | carries a legacy id | resolves into `entities.csv` | verdict |")
    A("|---|---:|---:|---|")
    for label, walk in (("Works", data["work_walk"]), ("Places", data["loc_walk"])):
        has = sum(1 for w in walk if w["legacy_id"])
        hit = sum(1 for w in walk if w["legacy_id"] in live_ents)
        verdict = ("complete — safe to cut over on id alone" if hit and hit == len(walk)
                   else "**unusable — a crosswalk must be derived**" if not hit
                   else "partial — review the gap")
        A(f"| {label} | {has:,} / {len(walk):,} | {hit:,} / {len(walk):,} | {verdict} |")
    A("")

    # ── references
    A("## References\n")
    A("V0.94 encodes references as space-separated `VOL-PAGE` lists inside the "
      "dimension row, not as fact tables. Expanded here and compared with the "
      "live `references.csv`.\n")
    A("Compared **per entity type** — a work reference is measured against the "
      "live work references, not against every reference in the file.\n")
    A("| | V0.94 | live | shared pages |")
    A("|---|---:|---:|---:|")
    for label, kind, refs in (("Works", "work", data["work_refs"]),
                              ("Places", "place", data["loc_refs"])):
        lv = [(v, p) for eid, v, p in live_refs
              if live_ents.get(eid, {}).get("entity_type") == kind]
        pairs = {(r["vol"], r["page"]) for r in refs}
        lv_pairs = set(lv)
        A(f"| {label} — reference rows | {len(refs):,} | {len(lv):,} | — |")
        A(f"| {label} — distinct (vol, page) | {len(pairs):,} | {len(lv_pairs):,} "
          f"| {len(pairs & lv_pairs):,} |")
    probs = data["problems"]
    A(f"\n### Reference keys that could not be read: **{len(probs):,}**\n")
    if probs:
        WHY = {
            "bare volume": "whitespace injected inside the numeral upstream, so `VII-241` arrives as `VI` + `I-241`",
            "bad volume": "OCR damage in the volume — `O` for a numeral, `l` for `1`",
            "non-numeric page": "the page part is not a number",
            "implausible range": "runs backwards, or spans more than 50 pages",
            "too many parts": "more hyphen-separated parts than a volume and a range",
        }
        A("| Kind | Count | Example | What it is |")
        A("|---|---:|---|---|")
        for kind, n in Counter(x["kind"] for x in probs).most_common():
            ex = next(x["token"] for x in probs if x["kind"] == kind)
            A(f"| {kind} | {n:,} | `{ex}` | {WHY.get(kind, '')} |")
        A(f"\nAcross **{len({x['entity_id'] for x in probs})}** register rows, "
          "listed in `data/normalized_v094/reference_problems.csv`.\n")
    A("> **Page ranges are expanded, not right-split.** 763 tokens have the form "
      "`IX-64-65` or `II-407-09` — a page range whose closing page is "
      "abbreviated to its trailing digits, as printed indexes conventionally "
      "do. Splitting on the last hyphen reads `II-407-09` as volume `II-407`, "
      "page `09`: silent corruption rather than visible failure. They are "
      "expanded to one pair per page, which is why the reference counts above "
      "exceed the raw token counts.\n")
    A("> `seq` in the emitted `references.csv` is a positional counter over each "
      "row's key list. It is **not** the live `seq`, which records order of "
      "mention. V0.94 cannot express that, so it cannot be recovered from it.\n")

    # ── fill rates
    A("## Column fill rates\n")
    A("Columns V0.94 provisions but may not populate — the difference between "
      "a field arriving and a field being usable.\n")
    A("| Registry | Column | Filled | Note |")
    A("|---|---|---:|---|")
    for reg, rows, ix, cols in data["fill"]:
        for key, note in cols:
            got, tot, ph = fill_rate(rows, ix, key)
            pct = (got / tot * 100) if tot else 0
            flag = " **empty**" if got == 0 else ""
            if ph:
                flag += f" — {ph} placeholder `0`"
            A(f"| {reg} | `{key}` | {got:,} / {tot:,} ({pct:.0f} %){flag} | {note} |")
    A("")

    # ── status
    A("## Editorial status\n")
    A("| Registry | `SourceStatus` |")
    A("|---|---|")
    for reg, rows, ix in data["status"]:
        c = Counter(s(r[ix["status"]]) or "(blank)" for r in rows)
        A(f"| {reg} | " + ", ".join(f"{k} {v:,}" for k, v in c.most_common()) + " |")
    A("")

    A("## What this says\n")
    A("- The **works register has arrived** and its identifiers carry, so works "
      "can be adopted on evidence rather than on faith.\n"
      "- The **place register cannot be adopted on its ids**; its attributes "
      "(country, category) are the valuable part and can be joined on label.\n"
      "- **Persons are absent**, so V0.82 remains the person spine regardless "
      "of anything else here.\n"
      "- **Empty columns are not future-proofing**: coordinates and "
      "cross-references are provisioned and unpopulated, so every derivation "
      "that fills them today must stay.\n"
      "- **Reference ordering is lost** in V0.94's encoding and cannot be "
      "reconstructed — only re-invented.\n")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(L), encoding="utf-8")
    print(f"  wrote {dest.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--source", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--report", type=Path, default=None,
                    help="also write a structural-diff markdown report here")
    args = ap.parse_args()

    src, out = args.source.resolve(), args.out.resolve()
    if not src.is_dir():
        sys.exit(f"--source is not a directory: {src}")
    print(f"Ingesting V0.94 from {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src}")

    work_ents, work_refs, work_walk, work_probs, work_rows, work_ix, _, work_req = build_works(src)
    loc_ents, loc_refs, loc_walk, loc_probs, loc_rows, loc_ix, _, loc_req = build_locations(src)
    pages, page_rows, page_ix, _, page_req = build_pages(src)
    calendar, _, _ = build_calendar(src)

    problems = work_probs + loc_probs

    write_csv(out / "entities.csv", ENTITY_FIELDS, work_ents + loc_ents)
    write_csv(out / "references.csv", REFERENCE_FIELDS, work_refs + loc_refs)
    write_csv(out / "diary_pages.csv", PAGE_FIELDS, pages)
    write_csv(out / "calendar.csv", CALENDAR_FIELDS, calendar)
    # Mark whether each legacy id actually reaches the live register, so the
    # crosswalk is usable on its own rather than only via the report.
    live_ids = set()
    live_ents_path = LIVE / "entities.csv"
    if live_ents_path.exists():
        with live_ents_path.open(encoding="utf-8") as f:
            live_ids = {r["entity_id"] for r in csv.DictReader(f)}
    for w in work_walk + loc_walk:
        w["resolves"] = ("yes" if w["legacy_id"] in live_ids
                         else "no" if w["legacy_id"] else "absent")
    write_csv(out / "id_crosswalk.csv", CROSSWALK_FIELDS, work_walk + loc_walk)
    write_csv(out / "reference_problems.csv",
              ["entity_id", "entity_type", "label", "kind", "token"], problems)

    if args.report:
        report(args.report.resolve(), src, {
            "work_ents": work_ents, "loc_ents": loc_ents,
            "work_refs": work_refs, "loc_refs": loc_refs,
            "work_walk": work_walk, "loc_walk": loc_walk,
            "pages": pages, "calendar": calendar, "problems": problems,
            "fill": [
                ("Work", work_rows, work_ix, [
                    ("artist", "retires the title-parenthesis artist regex"),
                    ("museum", "new — no live equivalent"),
                    ("city", "new — no live equivalent"),
                    ("see", "structured cross-references"),
                    ("see_also", "structured cross-references"),
                    ("old", "crosswalk to the live `Reg…` ids")]),
                ("Location", loc_rows, loc_ix, [
                    ("country", "would supersede `steder_verified_categories.csv`"),
                    ("category", "would supersede the same"),
                    ("lat", "would retire the Rejser/SV14 reconciliation"),
                    ("lon", "same"),
                    ("old", "crosswalk to the live ids")]),
                ("Diary page", page_rows, page_ix, [
                    ("kb", "would retire `build_kb_links.py` and its .xlsm")]),
            ],
            "status": [("Work", work_rows, work_ix),
                       ("Location", loc_rows, loc_ix),
                       ("Diary page", page_rows, page_ix)],
        })

    print("Done.")


if __name__ == "__main__":
    main()
