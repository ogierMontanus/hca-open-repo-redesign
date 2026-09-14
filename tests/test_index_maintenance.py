"""Exercise the index-maintenance engine, split included.

The split case is the reason this framework exists and the reason it has to be
tested synthetically: no register has been split yet. Waiting for the first
real one to find out whether the id allocation behaves would be finding out at
the worst possible moment.

Each test builds a small index in a temp directory with its own `IndexSpec`,
so nothing here touches the committed registers.
"""

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from index_maintenance import core                                   # noqa: E402
from index_maintenance.spec import IndexSpec, parse_vol_page         # noqa: E402

TODAY = "2026-09-14"
FIELDS = ["id", "name", "pages"]


def _spec(tmp_path) -> IndexSpec:
    return IndexSpec(
        name="t", path=tmp_path / "index.csv", id_column="id",
        id_prefix="TST", id_width=4, delimiter=",",
        label_of=lambda r: r.get("name", ""),
        signature_of=lambda r: parse_vol_page(r.get("pages", "")),
    )


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _run(spec, previous, incoming, ledger=None):
    ledger = ledger if ledger is not None else {}
    minter = core.Minter(spec, ledger, previous)
    pairs, pu, nu, amb = core.match(spec, previous, incoming)
    outcome = core.classify(spec, previous, incoming, pairs, pu, nu,
                            minter, ledger, TODAY, amb)
    return outcome, ledger


# ── the requirement: a split mints only for the new halves ──────────────────

def test_split_keeps_the_parent_id_on_the_continuation(tmp_path):
    """One entry becomes two. The half that inherits most of the parent's
    citations keeps the id; only the other half is minted.

    This is the behaviour that makes a split safe for existing references:
    most citations to the parent still land on a row that legitimately owns
    them, and the ledger explains the rest."""
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Hansen, Jens", "pages": "I:10;I:11;I:12;II:5"}]
    incoming = [
        {"id": "", "name": "Hansen, Jens", "pages": "I:10;I:11;I:12"},   # continuation
        {"id": "", "name": "Hansen, Jens", "pages": "II:5"},             # the new half
    ]
    outcome, ledger = _run(spec, previous, incoming)

    assert incoming[0]["id"] == "TST0001", "the continuation must keep the parent id"
    assert incoming[1]["id"] and incoming[1]["id"] != "TST0001"
    assert len(outcome.minted) == 1, "exactly one new id for a two-way split"
    assert outcome.minted[0][2].startswith("split from TST0001")
    assert outcome.splits and outcome.splits[0][0] == "TST0001"
    assert ledger["TST0001"]["status"] == "active"
    assert "split" in ledger["TST0001"]["note"]
    assert ledger[incoming[1]["id"]]["note"] == "split from TST0001"


def test_split_three_ways_mints_two(tmp_path):
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Lund", "pages": "I:1;I:2;I:3;I:4;II:9;III:7"}]
    incoming = [
        {"id": "", "name": "Lund", "pages": "I:1;I:2;I:3;I:4"},
        {"id": "", "name": "Lund", "pages": "II:9"},
        {"id": "", "name": "Lund", "pages": "III:7"},
    ]
    outcome, _ = _run(spec, previous, incoming)
    assert incoming[0]["id"] == "TST0001"
    assert len({r["id"] for r in incoming}) == 3, "every row gets a distinct id"
    assert len(outcome.minted) == 2


def test_split_that_cannot_be_decided_is_escalated(tmp_path):
    """Two halves with equal claim to the parent's citations.

    Nothing is assigned and the case is reported. Picking one at random would
    silently move every existing citation to whichever row sorted first."""
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Berg", "pages": "I:1;I:2"}]
    incoming = [
        {"id": "", "name": "Berg", "pages": "I:1"},
        {"id": "", "name": "Berg", "pages": "I:2"},
    ]
    outcome, _ = _run(spec, previous, incoming)
    assert any(k == "split-tie" for k, _, _ in outcome.conflicts)
    assert not outcome.splits


# ── merges ──────────────────────────────────────────────────────────────────

def test_merge_retires_the_loser_and_records_where_it_went(tmp_path):
    spec = _spec(tmp_path)
    previous = [
        {"id": "TST0001", "name": "Sand, A.", "pages": "I:1;I:2;I:3"},
        {"id": "TST0002", "name": "Sand, A.", "pages": "I:9"},
    ]
    incoming = [{"id": "", "name": "Sand, A.", "pages": "I:1;I:2;I:3;I:9"}]
    outcome, ledger = _run(spec, previous, incoming)

    assert incoming[0]["id"] == "TST0001", "the id with the greater overlap survives"
    assert outcome.merges == [("TST0001", ["TST0002"])]
    assert ledger["TST0002"]["status"] == "merged"
    assert ledger["TST0002"]["superseded_by"] == "TST0001"


def test_references_follow_a_merge(tmp_path):
    """A citation to a retired id is rewritten to the survivor."""
    spec_base = _spec(tmp_path)
    refs = tmp_path / "refs.csv"
    with refs.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["who", "note"])
        w.writeheader()
        w.writerows([{"who": "TST0002", "note": "a"}, {"who": "TST0001", "note": "b"}])
    spec = IndexSpec(
        name=spec_base.name, path=spec_base.path, id_column="id",
        id_prefix="TST", id_width=4, delimiter=",",
        label_of=spec_base.label_of, signature_of=spec_base.signature_of,
        reference_files=((refs, ",", "who"),),
    )
    outcome = core.Outcome(merges=[("TST0001", ["TST0002"])])
    touched = core.rewrite_references(spec, outcome, apply=True)
    assert touched and touched[0][1] == 1
    with refs.open(encoding="utf-8") as f:
        assert {r["who"] for r in csv.DictReader(f)} == {"TST0001"}


# ── carrying, minting, withdrawal ───────────────────────────────────────────

def test_rerunning_against_itself_changes_nothing(tmp_path):
    """Idempotence. An earlier engine matched rows all-to-all when a key was
    ambiguous on both sides, which turned two same-named people into a merge
    and gave them one id between them."""
    spec = _spec(tmp_path)
    rows = [
        {"id": "TST0001", "name": "Aa", "pages": "I:1"},
        {"id": "TST0002", "name": "Bb", "pages": "I:2"},
        {"id": "TST0003", "name": "Aa", "pages": "I:3"},   # same label, different person
    ]
    previous = [dict(r) for r in rows]
    incoming = [dict(r) for r in rows]
    outcome, _ = _run(spec, previous, incoming)
    assert len(outcome.carried) == 3
    assert not outcome.minted and not outcome.merges and not outcome.splits
    assert not outcome.conflicts
    assert [r["id"] for r in incoming] == ["TST0001", "TST0002", "TST0003"]


def test_a_renamed_entry_keeps_its_id_via_the_signature(tmp_path):
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Mogensen, Jorgen", "pages": "I:4;I:5"}]
    incoming = [{"id": "", "name": "Mogensen, Jørgen", "pages": "I:4;I:5"}]
    outcome, _ = _run(spec, previous, incoming)
    assert incoming[0]["id"] == "TST0001"
    assert not outcome.minted


def test_only_genuinely_new_entries_are_minted(tmp_path):
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Old", "pages": "I:1"}]
    incoming = [
        {"id": "", "name": "Old", "pages": "I:1"},
        {"id": "", "name": "Brand New", "pages": "X:99"},
    ]
    outcome, ledger = _run(spec, previous, incoming)
    assert incoming[0]["id"] == "TST0001"
    assert len(outcome.minted) == 1
    assert outcome.minted[0][2] == "new entry"
    assert ledger[incoming[1]["id"]]["first_seen"] == TODAY


def test_a_vanished_entry_is_withdrawn_not_deleted(tmp_path):
    spec = _spec(tmp_path)
    previous = [
        {"id": "TST0001", "name": "Stays", "pages": "I:1"},
        {"id": "TST0002", "name": "Goes", "pages": "I:2"},
    ]
    incoming = [{"id": "", "name": "Stays", "pages": "I:1"}]
    outcome, ledger = _run(spec, previous, incoming)
    assert outcome.withdrawn == [("TST0002", "Goes")]
    assert ledger["TST0002"]["status"] == "withdrawn"


def test_a_minted_id_never_reuses_a_retired_number(tmp_path):
    """A retired id must stay retired: reusing the number would silently
    re-point every old citation at a different entity."""
    spec = _spec(tmp_path)
    ledger = {"TST0009": {"id": "TST0009", "status": "withdrawn",
                          "superseded_by": "", "first_seen": TODAY, "note": ""}}
    minter = core.Minter(spec, ledger, [])
    assert minter.mint() == "TST0010"


# ── validation ──────────────────────────────────────────────────────────────

def test_validate_catches_duplicate_and_malformed_ids(tmp_path):
    spec = _spec(tmp_path)
    rows = [
        {"id": "TST0001", "name": "A", "pages": ""},
        {"id": "TST0001", "name": "B", "pages": ""},
        {"id": "nonsense", "name": "C", "pages": ""},
        {"id": "", "name": "D", "pages": ""},
    ]
    kinds = {k for k, _, _ in core.validate(spec, rows, {})}
    assert {"duplicate-id", "malformed-id", "missing-id"} <= kinds


def test_validate_notices_a_ledger_that_has_drifted(tmp_path):
    spec = _spec(tmp_path)
    ledger = {"TST0007": {"id": "TST0007", "status": "active",
                          "superseded_by": "", "first_seen": TODAY, "note": ""}}
    kinds = {k for k, _, _ in core.validate(spec, [], ledger)}
    assert "ledger-drift" in kinds


# ── the engine is not person-shaped ─────────────────────────────────────────

def test_the_same_engine_runs_an_index_with_different_columns(tmp_path):
    """A place-shaped index: different id prefix, different column names, and
    a signature built from a different field. No engine change."""
    spec = IndexSpec(
        name="place", path=tmp_path / "places.csv", id_column="place_id",
        id_prefix="HCAL", id_width=6, delimiter=",",
        label_of=lambda r: r.get("place_name", ""),
        signature_of=lambda r: parse_vol_page(r.get("cited", ""), sep=" "),
    )
    previous = [{"place_id": "HCAL000001", "place_name": "Odense", "cited": "I:1 I:2"}]
    incoming = [
        {"place_id": "", "place_name": "Odense", "cited": "I:1 I:2"},
        {"place_id": "", "place_name": "Nyborg", "cited": "III:3"},
    ]
    outcome, _ = _run(spec, previous, incoming)
    assert incoming[0]["place_id"] == "HCAL000001"
    assert incoming[1]["place_id"].startswith("HCAL")
    assert len(outcome.minted) == 1


# ── the two rules the synthetic split on real data forced ───────────────────

def test_a_renamed_split_half_is_still_recognised_as_a_split(tmp_path):
    """A split normally renames at least one half — that is the point of it.

    So the label cannot see the relationship and, without a signature rule,
    the new half is minted as an unrelated "new entry" and the ledger loses
    the link to its parent. A child cites a subset of what the undivided
    entry cited, which is what finds it.
    """
    spec = _spec(tmp_path)
    previous = [{"id": "TST0001", "name": "Aaberg", "pages": "I:1;I:2;I:3;I:4"}]
    incoming = [
        {"id": "", "name": "Aaberg", "pages": "I:1;I:2;I:3"},
        {"id": "", "name": "Aaberg, the younger", "pages": "I:4"},   # renamed half
    ]
    outcome, ledger = _run(spec, previous, incoming)
    assert outcome.splits, "the renamed half should be attributed to its parent"
    assert outcome.splits[0][0] == "TST0001"
    assert ledger[incoming[1]["id"]]["note"] == "split from TST0001"


def test_an_unrelated_superset_does_not_claim_a_split_child(tmp_path):
    """Busy entries cite supersets of everyone's pages by coincidence.

    On the real register the two-page child of Åberg had *two* previous
    entries whose citations enclosed it, only one of which was the parent.
    The label breaks the tie; a candidate sharing no label token is not a
    parent at all.
    """
    spec = _spec(tmp_path)
    previous = [
        {"id": "TST0001", "name": "Aaberg", "pages": "I:1;I:2;I:3;I:4"},
        {"id": "TST0002", "name": "Unrelated Busybody", "pages": "I:1;I:2;I:3;I:4;I:9;II:2"},
    ]
    incoming = [
        {"id": "", "name": "Aaberg", "pages": "I:1;I:2;I:3"},
        {"id": "", "name": "Aaberg, the younger", "pages": "I:4"},
    ]
    outcome, ledger = _run(spec, previous, incoming)
    assert outcome.splits and outcome.splits[0][0] == "TST0001", \
        "the parent must be the one sharing the heading, not the busiest one"


def test_a_same_label_bucket_is_split_by_signature_before_giving_up(tmp_path):
    """Two people with the same name, ids stripped: the label says nothing,
    but the citations still do."""
    spec = _spec(tmp_path)
    previous = [
        {"id": "TST0001", "name": "Jensen, Jens", "pages": "I:1;I:2"},
        {"id": "TST0002", "name": "Jensen, Jens", "pages": "V:7"},
    ]
    incoming = [
        {"id": "", "name": "Jensen, Jens", "pages": "V:7"},
        {"id": "", "name": "Jensen, Jens", "pages": "I:1;I:2"},
    ]
    outcome, _ = _run(spec, previous, incoming)
    assert incoming[0]["id"] == "TST0002"
    assert incoming[1]["id"] == "TST0001"
    assert not outcome.conflicts


def test_identical_label_and_identical_signature_is_escalated(tmp_path):
    """When nothing distinguishes two rows, assigning ids would be a coin
    flip. Ten such pairs exist in the live person register."""
    spec = _spec(tmp_path)
    previous = [
        {"id": "TST0001", "name": "Twin", "pages": "I:1"},
        {"id": "TST0002", "name": "Twin", "pages": "I:1"},
    ]
    incoming = [
        {"id": "", "name": "Twin", "pages": "I:1"},
        {"id": "", "name": "Twin", "pages": "I:1"},
    ]
    outcome, _ = _run(spec, previous, incoming)
    assert any(k == "ambiguous-both-sides" for k, _, _ in outcome.conflicts)
    assert not outcome.minted, "no id may be guessed at here"
