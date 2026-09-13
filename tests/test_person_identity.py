"""Guard the person register's stable identifiers and the crosswalk built on them.

`01_entry_id` is a row number that renumbers whenever a row is inserted, so
nothing could rely on it as an identity. `00_person_id` is the replacement:
assigned once, carried thereafter, never re-derived from content. These tests
hold that property, because the moment an id moves, every crosswalk row and
every citation built on it is silently wrong.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "parsed" / "personregister_xi_parsed.tsv"
CROSSWALK = ROOT / "data" / "curated" / "person_id_crosswalk.csv"
ID_COL = "00_person_id"


@pytest.fixture(scope="module")
def master():
    with MASTER.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


@pytest.fixture(scope="module")
def crosswalk():
    with CROSSWALK.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_every_entry_has_a_stable_id(master):
    missing = [r["01_entry_id"] for r in master if not r.get(ID_COL)]
    assert not missing, f"{len(missing)} rows without {ID_COL}: {missing[:5]}"


def test_ids_are_unique(master):
    dupes = [i for i, n in Counter(r[ID_COL] for r in master).items() if n > 1]
    assert not dupes, f"duplicate ids: {dupes[:5]}"


def test_ids_are_well_formed(master):
    bad = [r[ID_COL] for r in master
           if not (r[ID_COL].startswith("HCAP") and r[ID_COL][4:].isdigit())]
    assert not bad, f"malformed ids: {bad[:5]}"


def test_id_is_the_first_column(master):
    assert list(master[0])[0] == ID_COL, (
        "the identifier should lead the row; if it moved, something rewrote "
        "the file without going through mint_person_ids.py"
    )


def test_ids_are_carried_not_recomputed(tmp_path, monkeypatch):
    """The property that distinguishes 00_person_id from 01_entry_id.

    Both currently agree row-for-row, because the ids were minted in file
    order and nothing has been inserted since. That is *not* evidence either
    way, which an earlier version of this test got wrong. What matters is the
    behaviour under change: insert a row at the top and re-run, and every
    existing id must stay on its own entry while the newcomer gets a fresh
    one. Positional ids would all shift by one.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "segmentation"))
    import mint_person_ids as mint

    work = tmp_path / "master.tsv"
    with MASTER.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
        fields = list(rows[0])
    before = {r["01_entry_id"]: r[ID_COL] for r in rows}

    newcomer = {k: "" for k in fields}
    newcomer["01_entry_id"] = "PerXI99999"
    newcomer["02_entry_type"] = "standardpost"
    newcomer["03_surname"] = "Aaaaardvark"
    with work.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows([newcomer] + rows)

    monkeypatch.setattr(mint, "MASTER", work)
    monkeypatch.setattr(sys, "argv", ["mint_person_ids.py"])
    mint.main()

    with work.open(encoding="utf-8", newline="") as f:
        after = list(csv.DictReader(f, delimiter="\t"))
    moved = [r["01_entry_id"] for r in after
             if r["01_entry_id"] in before and r[ID_COL] != before[r["01_entry_id"]]]
    assert not moved, f"{len(moved)} existing ids moved: {moved[:5]}"

    fresh = [r for r in after if r["01_entry_id"] == "PerXI99999"]
    assert fresh and fresh[0][ID_COL] not in before.values(), (
        "the inserted row should get a new id, not reuse an existing one"
    )


def test_crosswalk_covers_the_register(master, crosswalk):
    """Every person entry appears, matched or not. Silence is not an answer."""
    persons = {r[ID_COL] for r in master
               if r.get("02_entry_type") != "krydshenvisning"}
    covered = {r["person_id"] for r in crosswalk}
    missing = persons - covered
    assert not missing, f"{len(missing)} entries absent from the crosswalk"


def test_crosswalk_resolution_does_not_regress(crosswalk):
    """97.8 % resolved at the time of writing.

    A ceiling on *loss*: the rate should rise as the 209 review cases are
    worked through. A fall means the matcher or one of its inputs changed.
    """
    unresolved = sum(1 for r in crosswalk if r["tier"] in ("ambiguous", "none"))
    rate = 1 - unresolved / len(crosswalk)
    assert rate > 0.95, (
        f"crosswalk resolution fell to {rate:.1%} "
        f"({unresolved:,} unresolved of {len(crosswalk):,}). "
        "See data/review/person_crosswalk_review.csv."
    )


def test_resolved_rows_carry_a_reg_id(crosswalk):
    broken = [r["person_id"] for r in crosswalk
              if r["tier"] not in ("ambiguous", "none") and not r["reg_id"]]
    assert not broken, f"resolved rows without a reg_id: {broken[:5]}"


def test_one_reg_id_is_not_claimed_by_many_entries(crosswalk):
    """A live person matched by several register entries is a duplicate
    candidate, not a crosswalk. A few are expected; a lot means the matcher
    is collapsing distinct people."""
    claims = Counter(r["reg_id"] for r in crosswalk if r["reg_id"])
    contested = [k for k, n in claims.items() if n > 1]
    assert len(contested) < 250, (
        f"{len(contested):,} live ids claimed by more than one register entry"
    )
