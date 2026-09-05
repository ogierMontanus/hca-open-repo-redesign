"""
Guards data/curated/person_emendations.tsv — the post-editorial
corrections laid over the printed register.

The whole point of the file is that it does NOT edit master1: a
correction is a separate, sourced claim, and master1 keeps saying what the
book says. That only works if the link between the two is checked. Each
emendation records the value it expects to find underneath it; when
master1 changes and that no longer matches, the correction is stale and
must be re-examined rather than applied to whatever now sits there.

See docs/data-model/person-editorial-emendations.md.
"""
import csv
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EMENDATIONS = ROOT / "data" / "curated" / "person_emendations.tsv"
SCRIPT = ROOT / "scripts" / "parsers" / "apply_person_emendations.py"

VALID_FIELDS = {"surname", "given_names", "birth_year", "death_year", "description"}
VALID_CONFIDENCE = {"certain", "probable", "proposed"}


@pytest.fixture(scope="module")
def rows():
    if not EMENDATIONS.exists():
        pytest.skip(f"{EMENDATIONS.relative_to(ROOT)} absent")
    with EMENDATIONS.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f, delimiter="\t")
                if (r.get("match_surname") or "").strip()]


def test_every_emendation_cites_a_source_and_a_reason(rows):
    """A correction without provenance is indistinguishable from a guess."""
    for r in rows:
        where = f"{r['match_surname']} [{r['match_refs']}] {r['field']}"
        assert (r.get("source") or "").strip(), f"{where}: mangler kilde"
        assert (r.get("date") or "").strip(), f"{where}: mangler dato"
        assert (r.get("notes") or "").strip(), f"{where}: mangler begrundelse"


def test_fields_and_confidence_are_known(rows):
    for r in rows:
        where = f"{r['match_surname']} [{r['match_refs']}] {r['field']}"
        assert r["field"] in VALID_FIELDS, f"{where}: ukendt felt"
        assert r["confidence"] in VALID_CONFIDENCE, f"{where}: ukendt confidence"


def test_emendations_still_match_master1():
    """Runs the validator: every `original` must still equal what master1
    holds, and every key must resolve to exactly one entry."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, (
        "person_emendations.tsv no longer matches master1:\n" + proc.stdout + proc.stderr
    )
