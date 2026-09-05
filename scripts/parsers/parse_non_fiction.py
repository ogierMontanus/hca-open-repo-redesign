#!/usr/bin/env python3
"""Parse the non-fiction (Faglitteratur) slice of the canonical workbook
into a structured 13-column TSV.

See docs/pipeline/stages.md (Stage 2) for context, and
docs/data-model/source-data-characteristics.md for the pseudonym / source
/ uncertain-citation conventions encoded below.

Default slice: RegistryCategory='VÆRK-REGISTER',
WorkGenre='ANDRE FORFATTERE', RegistryForm='Faglitteratur'.

Column schema
-------------
01_Posttype            : standardpost | krydshenvisning
02_by_Andersen         : False throughout
03_genre               : NonFiction
04_main_title          : Full title string; embedded parens kept as-is
05_pseudonym           : Pen name / alias before Ͻ: in creator paren
06_creator             : Real name (after Ͻ:), or sole name if no Ͻ:
07_translator          : Extracted from 'oversat af' in creator paren
08_source              : Journal / newspaper / publication (paren containing year)
09_Se_ogsaa            : WEMI or translation reference
10_Krydshenvisning_til : Cross-reference target
11_uncertain_citation  : True when original title was inside [...]
12_Note                : Year-only parens, long inline notes, edition info
RegistryTitelID        : From source workbook

Usage:
    python parse_non_fiction.py [--xlsx PATH] [--output PATH]
"""

import argparse
import csv
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import load_registry_slice, resolve_ground_truth_xlsx


COLUMNS = [
    "01_Posttype", "02_by_Andersen", "03_genre",
    "04_main_title", "05_pseudonym", "06_creator", "07_translator",
    "08_source", "09_Se_ogsaa", "10_Krydshenvisning_til",
    "11_uncertain_citation", "12_Note", "RegistryTitelID",
]
GENRE = "NonFiction"

# ── Patterns ─────────────────────────────────────────────────────────────────

KRYDS_RE = re.compile(r"^(.+?),\s*[Ss]e:\s*(.+)$", re.DOTALL)
SE_OGSAA_RE = re.compile(
    r"\s*-\s*(?:Se ogsaa|Engelsk Oversættelse)\s*:?\s*(.+?)\.?\s*$",
    re.IGNORECASE,
)
PAREN_RE = re.compile(r"\(([^)]+)\)")
YEAR_RE = re.compile(r"\b\d{4}\b")
YEAR_ONLY_RE = re.compile(r"^\d{4}(-\d{2,4})?$")
OVERSAT_RE = re.compile(r",?\s*oversat\s+af\s+(.+)$", re.IGNORECASE)
PSEUDONYM_RE = re.compile(r"^(.+?)[,\s]+Ͻ:\s*(.+)$")
# "(ved A. Westrup)" -- an editor credit ("by/via A. Westrup"), same "ved"
# marker parse_novels_plays_tales.py recognises; the name after it is the
# real creator, so strip the particle rather than leaving "ved" glued to
# the front of what becomes 06_creator.
VED_PREFIX_RE = re.compile(r"^ved\s+", re.IGNORECASE)
BRACKET_DVS_RE = re.compile(r"\s*\[Ͻ:\s*([^\]]+)\]")
BRACKET_RE = re.compile(r"^\[([^\]]+)\](.*)", re.DOTALL)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_row(
    posttype: str,
    main_title: str,
    *,
    pseudonym: str = "",
    creator: str = "",
    translator: str = "",
    source: str = "",
    se_ogsaa: str = "",
    kryds_til: str = "",
    uncertain: str = "False",
    note: str = "",
    reg_id: str = "",
) -> dict:
    return {
        "01_Posttype": posttype,
        "02_by_Andersen": "False",
        "03_genre": GENRE,
        "04_main_title": main_title,
        "05_pseudonym": pseudonym,
        "06_creator": creator,
        "07_translator": translator,
        "08_source": source,
        "09_Se_ogsaa": se_ogsaa,
        "10_Krydshenvisning_til": kryds_til,
        "11_uncertain_citation": uncertain,
        "12_Note": note,
        "RegistryTitelID": reg_id,
    }


def split_pseudonym(raw: str) -> tuple[str, str]:
    m = PSEUDONYM_RE.match(raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", raw.strip()


def classify_paren(content: str) -> str:
    s = content.strip()
    if YEAR_ONLY_RE.match(s):
        return "year_note"
    if YEAR_RE.search(s):
        return "source"
    return "creator"


def looks_like_creator(s: str) -> bool:
    """Screens a creator candidate the same way the parser's siblings do
    (parse_novels_plays_tales.py's _looks_name_shaped, build_works_extra
    .py's _looks_like_artist) -- a paren with no year isn't automatically
    a name: "fransk Oversættelse" (a French-translation note, no
    translator named) and "heri Amores Christiani IVti med Bilag" (a
    content note -- what's included in this volume, not who wrote it)
    both default to classify_paren()'s "creator" bucket for lack of a
    year, but neither is one. A real name in this dataset is never
    lowercase-led."""
    return bool(s) and not s[0].islower()


# ── Parser ───────────────────────────────────────────────────────────────────

def parse_entry(raw_label: str, reg_id: str) -> dict:
    label = raw_label.replace("\xa0", " ").replace("\n", " ").strip()

    km = KRYDS_RE.match(label)
    if km:
        title_part = km.group(1).strip().rstrip(",")
        target = km.group(2).strip().rstrip(".")
        return make_row(
            "krydshenvisning", title_part,
            kryds_til=target, reg_id=reg_id,
        )

    uncertain = "False"
    bm = BRACKET_RE.match(label)
    if bm:
        uncertain = "True"
        inner = bm.group(1).strip()
        rest = bm.group(2).strip().lstrip("]").strip()
        label = (inner + " " + rest).strip() if rest else inner

    creator_from_bracket = ""
    bdm = BRACKET_DVS_RE.search(label)
    if bdm:
        creator_from_bracket = bdm.group(1).strip()
        label = (label[: bdm.start()] + label[bdm.end() :]).strip().rstrip(")")

    se_ogsaa = ""
    sm = SE_OGSAA_RE.search(label)
    if sm:
        se_ogsaa = sm.group(1).strip()
        label = label[: sm.start()].strip()

    note_parts: list[str] = []
    last_close = label.rfind(")")
    if last_close != -1:
        tail = label[last_close + 1 :].strip().rstrip(".")
        if len(tail) > 5:
            note_parts.append(tail)
            label = label[: last_close + 1].strip()

    parens = list(PAREN_RE.finditer(label))

    if not parens:
        main_title = label.strip().rstrip("., ")
        note = "; ".join(note_parts)
        pseudo, cre = split_pseudonym(creator_from_bracket) if creator_from_bracket else ("", "")
        return make_row(
            "standardpost", main_title,
            pseudonym=pseudo, creator=cre,
            uncertain=uncertain, se_ogsaa=se_ogsaa,
            note=note, reg_id=reg_id,
        )

    pseudonym = ""
    creator = creator_from_bracket
    translator = ""
    source = ""
    parens_to_strip: list[re.Match] = []

    idx_remaining = list(range(len(parens)))
    current_end = len(label)

    while idx_remaining:
        candidates = [i for i in idx_remaining if parens[i].end() <= current_end]
        if not candidates:
            break
        idx = candidates[-1]
        m = parens[idx]

        gap = label[m.end() : current_end]
        if gap.strip() and not re.match(r"^[).,\s]*$", gap):
            break

        content = m.group(1).strip()
        role = classify_paren(content)

        if role == "year_note":
            note_parts.insert(0, content)
            parens_to_strip.append(m)
            idx_remaining.remove(idx)
            current_end = m.start()

        elif role == "source":
            source = (content + "; " + source).strip("; ") if source else content
            parens_to_strip.append(m)
            idx_remaining.remove(idx)
            current_end = m.start()

        else:  # creator-type
            if not creator:
                om = OVERSAT_RE.search(content)
                if om:
                    translator = om.group(1).strip()
                    raw_creator = content[: om.start()].strip().rstrip(",")
                else:
                    raw_creator = content
                raw_creator = VED_PREFIX_RE.sub("", raw_creator).strip()
                if looks_like_creator(raw_creator):
                    pseudonym, creator = split_pseudonym(raw_creator)
                else:
                    # Not a name -- a content/language note that only
                    # landed here for lack of a year to route it to
                    # "source" instead. Keep it out of 06_creator; it's
                    # still consumed (not left dangling in the title).
                    # insert(0, ...), not append -- parens are walked
                    # right-to-left here, same as the year_note branch
                    # above, so this keeps note ordering left-to-right.
                    note_parts.insert(0, content)
                parens_to_strip.append(m)
                idx_remaining.remove(idx)
                current_end = m.start()
            else:
                break

    title_str = label
    for m in sorted(parens_to_strip, key=lambda x: x.start(), reverse=True):
        title_str = title_str[: m.start()] + title_str[m.end() :]
    main_title = re.sub(r"\s+", " ", title_str).strip().rstrip("., ")

    note = "; ".join(note_parts)

    return make_row(
        "standardpost", main_title,
        pseudonym=pseudonym, creator=creator, translator=translator,
        source=source, se_ogsaa=se_ogsaa,
        uncertain=uncertain, note=note, reg_id=reg_id,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def run(xlsx: pathlib.Path, dst: pathlib.Path) -> pathlib.Path:
    slice_rows = load_registry_slice(
        xlsx,
        category="VÆRK-REGISTER",
        genre="ANDRE FORFATTERE",
        form="Faglitteratur",
    )

    output: list[dict] = [parse_entry(title, reg_id) for title, reg_id in slice_rows]

    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        for r in output:
            w.writerow(r)

    n_std = sum(1 for r in output if r["01_Posttype"] == "standardpost")
    n_kryd = sum(1 for r in output if r["01_Posttype"] == "krydshenvisning")
    n_src = sum(1 for r in output if r["08_source"])
    n_trans = sum(1 for r in output if r["07_translator"])
    n_pseu = sum(1 for r in output if r["05_pseudonym"])
    n_unc = sum(1 for r in output if r["11_uncertain_citation"] == "True")
    n_note = sum(1 for r in output if r["12_Note"])
    n_se = sum(1 for r in output if r["09_Se_ogsaa"])

    print(f"Source : {xlsx.name}  (slice: ANDRE FORFATTERE / Faglitteratur)")
    print(f"Written: {dst}")
    print(f"Rows   : {len(output)}")
    print(f"  standardpost      : {n_std}")
    print(f"  krydshenvisning   : {n_kryd}")
    print(f"  with source       : {n_src}")
    print(f"  with translator   : {n_trans}")
    print(f"  with pseudonym    : {n_pseu}")
    print(f"  uncertain [...]   : {n_unc}")
    print(f"  with note         : {n_note}")
    print(f"  with Se ogsaa     : {n_se}")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", type=pathlib.Path, default=None)
    ap.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("data/parsed/non_fiction_parsed.tsv"),
    )
    args = ap.parse_args()
    xlsx = args.xlsx or resolve_ground_truth_xlsx()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run(xlsx, args.output)


if __name__ == "__main__":
    main()
