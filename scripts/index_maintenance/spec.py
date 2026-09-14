"""
spec.py — what the engine needs to know about one index.

Everything index-specific lives here and nowhere else. Adding works, places,
organisations or subjects means adding an `IndexSpec` below, not touching
`core.py`.

An index qualifies if it has three things, which all of this project's
registers do:

  a label       the human-readable name or title, used for the first match
  a signature   evidence of identity that survives a re-spelling. For every
                register here that is the set of diary pages the entry cites.
                It is what separates "the same person spelled differently"
                from "a different person with a similar name", and it is the
                only reason split and merge detection can work at all.
  a stable id   a column the engine owns: minted once, carried thereafter.

If an index has no signature, the engine can still carry ids across a rename
but cannot tell a split from two unrelated new rows. Say so in the spec rather
than pretending otherwise.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]

# Year parentheses are removed wholesale, not just the trailing one — removing
# only the last was a real bug in the hand method this replaces.
YEAR_PAREN = re.compile(
    r"\((?=[^)]*\d)[^)]*(?:\d{3,4}|f\.\s*Chr\.|død|ca\.)[^)]*\)", re.I)


def fold(label: str) -> str:
    """The normalised comparison key. NFKD-strip diacritics, drop every year
    parenthesis, fold punctuation, upper-case.

    Kept identical to scripts/validation/compare_to_reference.py's fold_name:
    that one was calibrated against this corpus, and two normalisers that
    almost agree are worse than one."""
    s = YEAR_PAREN.sub(" ", label or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("æ", "ae").replace("Æ", "AE")
    s = s.replace("ø", "o").replace("Ø", "O")
    s = re.sub(r"[^A-Za-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def parse_vol_page(cell: str, sep: str = ";") -> frozenset:
    """'I:272;I:298' -> {('I','272'), ('I','298')}"""
    out = set()
    for tok in (cell or "").split(sep):
        tok = tok.strip()
        if ":" in tok:
            v, _, p = tok.rpartition(":")
            if v.strip() and p.strip().isdigit():
                out.add((v.strip(), p.strip()))
    return frozenset(out)


@dataclass(frozen=True)
class IndexSpec:
    """One register the engine can maintain."""

    name: str                       # "person" — names the ledger and reports
    path: Path                      # the index file the engine owns
    id_column: str                  # the column the engine mints into
    id_prefix: str                  # "HCAP"
    id_width: int = 5
    delimiter: str = "\t"

    # How to read a row. Kept as callables so an index with an odd shape does
    # not force a column-naming convention on every other one.
    label_of: Callable[[dict], str] = lambda r: r.get("label", "")
    signature_of: Callable[[dict], frozenset] = lambda r: frozenset()
    is_entry: Callable[[dict], bool] = lambda r: True   # skip redirect stubs

    # Files whose rows point at this index by id, and the column that does it.
    # Rewritten when a merge retires an id.
    reference_files: tuple = ()

    notes: str = ""

    @property
    def ledger_path(self) -> Path:
        return ROOT / "data" / "curated" / f"{self.name}_id_ledger.csv"

    @property
    def report_path(self) -> Path:
        return ROOT / "data" / "review" / f"{self.name}_index_update_review.csv"

    def read(self) -> tuple:
        if not self.path.exists():
            sys.exit(f"missing index: {self.path}")
        with self.path.open(encoding="utf-8", newline="") as f:
            r = csv.DictReader(f, delimiter=self.delimiter)
            return list(r), list(r.fieldnames or [])


# ── the registers ───────────────────────────────────────────────────────────

def _person_label(r):
    surname = (r.get("03_surname") or "").strip()
    given = (r.get("04_given_names") or "").strip()
    return f"{surname}, {given}".strip(", ") if given else surname


PERSON = IndexSpec(
    name="person",
    path=ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv",
    id_column="00_person_id",
    id_prefix="HCAP",
    label_of=_person_label,
    signature_of=lambda r: parse_vol_page(r.get("11_references_parsed", "")),
    is_entry=lambda r: r.get("02_entry_type") != "krydshenvisning",
    reference_files=(
        (ROOT / "data" / "curated" / "person_id_crosswalk.csv", ",", "person_id"),
    ),
    notes="The register this framework was built from. Its signature is the "
          "parsed VOL:PAGE citation set, which carried 97.8 % of a 9,669-row "
          "crosswalk.",
)

# Declared to prove the engine is not person-shaped. Not yet wired into a
# run: the work register's own ids are still the V0.82 Reg… ids, and giving
# it a second id space before the V0.94 question is settled would create
# exactly the ambiguity this framework exists to prevent.
WORK = IndexSpec(
    name="work",
    path=ROOT / "data" / "normalized" / "entities.csv",
    id_column="entity_id",
    id_prefix="Reg",
    id_width=6,
    delimiter=",",
    label_of=lambda r: r.get("label", ""),
    signature_of=lambda r: frozenset(),   # references live in references.csv
    is_entry=lambda r: r.get("entity_type") == "work",
    notes="Declared, not wired. Works are identified by the live Reg… ids and "
          "their citations live in references.csv rather than in the row, so "
          "signature_of would have to join before it could answer. See "
          "docs/index-maintenance.md, 'Adding an index'.",
)

REGISTRY = {s.name: s for s in (PERSON, WORK)}
