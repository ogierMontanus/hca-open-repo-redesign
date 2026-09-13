#!/usr/bin/env python3
"""Regression guards for the register integrity rules.

The rules themselves live in scripts/validation/. This file is what makes
them bite: it pins each one to what the data actually shows today, so a
cleaning pass that introduces a dangling reference, or a parser change that
starts cutting entries in the wrong place, fails here instead of shipping.

Two kinds of assertion, and the difference is deliberate:

  **Hard zero** for rules that no legitimate register entry can violate. A
  cross-reference cannot point at itself; a chain of redirects has no
  meaning in a printed index; an ordinary entry does not redirect; a
  sub-entry without its parent is orphaned. These are structural, so any
  count above zero is a defect, and the assertion says so.

  **A measured ceiling** for rules whose residual is genuine source damage —
  a target the 1977 editors printed for an entry that is not in the book, an
  OCR misread in one of the two labels. Those cannot be asserted to zero
  without either lying or deleting real findings. The ceiling is set at
  today's count, so the number can only go down; each is annotated with what
  it stood at when measured.

Raise a ceiling only after checking the new failures against the register
itself, and lower it whenever a cleaning pass fixes some — a ceiling left
slack after a fix stops guarding anything.

Run from the repo root:
  python -m pytest tests/test_index_integrity.py -v
"""

import collections
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts" / "validation"))

import check_indexes as C  # noqa: E402


@pytest.fixture(scope="module")
def counts():
    for p in ("data/normalized/entities.csv", "data/parsed/personregister_xi_parsed.tsv"):
        if not (REPO / p).exists():
            pytest.skip(f"{p} not present — run scripts/run_pipeline.py first")
    findings = C.run()
    return collections.Counter((r["index"], r["rule"]) for r in findings.rows), findings


def _n(counts, index, rule):
    return counts[0][(index, rule)]


def _detail(findings, index, rule, limit=6):
    rows = [r for r in findings.rows if r["index"] == index and r["rule"] == rule]
    return "; ".join(f"{r['id']} -> {r['detail']!r}" for r in rows[:limit])


# ── structural rules: no legitimate entry can violate these ────────────────

@pytest.mark.parametrize("index", ["work", "person", "place"])
def test_no_cross_reference_points_at_itself(counts, index):
    # "Napoli, se: Napoli" sends a reader in a circle. It is also the shape
    # a bad merge leaves behind, when a stub and its target are folded into
    # one row.
    n = _n(counts, index, "XR3-self-reference")
    assert n == 0, f"{index}: {n} self-referencing cross-reference(s): {_detail(counts[1], index, 'XR3-self-reference')}"


@pytest.mark.parametrize("index", ["work", "person", "place"])
def test_no_redirect_lands_on_another_redirect(counts, index):
    # The printed register never chains: every "se:" points at a
    # substantive entry. A stub pointing at a stub means the entry between
    # them was lost, and a reader following it arrives at another signpost.
    n = _n(counts, index, "XR4-chained-redirect")
    assert n == 0, f"{index}: {n} chained redirect(s): {_detail(counts[1], index, 'XR4-chained-redirect')}"


@pytest.mark.parametrize("index", ["music_register", "non_fiction", "novels_plays_tales"])
def test_ordinary_entries_do_not_redirect(counts, index):
    # Only a Posttype of krydshenvisning carries a Krydshenvisning_til. An
    # ordinary entry that has one was mis-typed by the parser — the row is
    # about to be published as a work with content AND as a signpost.
    n = _n(counts, index, "RV-entry-redirects")
    assert n == 0, f"{index}: {n} ordinary entr(ies) carrying a redirect: {_detail(counts[1], index, 'RV-entry-redirects')}"


@pytest.mark.parametrize("index", ["music_register", "non_fiction", "novels_plays_tales"])
def test_every_entry_is_identifiable(counts, index):
    # Identity is title OR incipit, never title alone: 30 songs in the music
    # register are known only by their first line and legitimately have no
    # title. Asserting on the title alone would fail on all 30 while missing
    # a row that has genuinely lost both.
    n = _n(counts, index, "RV-no-identity")
    assert n == 0, f"{index}: {n} row(s) with neither a title nor an incipit: {_detail(counts[1], index, 'RV-no-identity')}"


@pytest.mark.parametrize("index", ["music_register", "non_fiction", "novels_plays_tales"])
def test_every_entry_traces_to_its_source_row(counts, index):
    # RegistryTitelID is the provenance pointer back to the canonical
    # workbook. The containers the parser synthesises for a part_of with no
    # row of its own are exempt — they have nothing to point at — and the
    # rule knows that, so this can be a hard zero.
    n = _n(counts, index, "RV-no-provenance")
    assert n == 0, f"{index}: {n} row(s) without provenance: {_detail(counts[1], index, 'RV-no-provenance')}"


def test_every_sub_entry_keeps_its_parent(counts):
    # A dash sub-entry ("— Hans Datter") means nothing without the entry it
    # hangs from; alphabetical sorting has separated them before (the dash
    # sorts ahead of every letter), which is how 13 of them were orphaned.
    n = _n(counts, "personregister_xi", "RV-no-parent")
    assert n == 0, f"{n} orphaned sub-entr(ies): {_detail(counts[1], 'personregister_xi', 'RV-no-parent')}"


@pytest.mark.parametrize("index", ["music_register", "non_fiction", "novels_plays_tales"])
def test_work_register_stubs_carry_no_content(counts, index):
    # A cross-reference stub's content lives at its target. Content here
    # means a split cut on the wrong side and gave the signpost the entry's
    # creator, note or original title.
    n = _n(counts, index, "RV-stub-carries-content")
    assert n == 0, f"{index}: {n} stub(s) carrying content: {_detail(counts[1], index, 'RV-stub-carries-content')}"


@pytest.mark.parametrize("index", ["music_register", "non_fiction", "novels_plays_tales"])
def test_work_register_stubs_all_have_a_target(counts, index):
    # A cross-reference with nothing to point at is not a cross-reference:
    # it is an entry whose "se:" clause failed to parse, and it renders as a
    # dead stub. The person register has one such row and carries its own
    # ceiling for it; in the work registers this has always been zero.
    n = _n(counts, index, "XR1-no-target")
    assert n == 0, f"{index}: {n} targetless cross-reference(s): {_detail(counts[1], index, 'XR1-no-target')}"


# ── measured ceilings: residual source damage, each one down-only ──────────

# (index, rule, ceiling, what it stood at when measured and why)
CEILINGS = [
    ("work", "XR2-blind", 4,
     "4 targets the register prints for entries it does not contain "
     "(Englen Guldgod, and three cited in a contracted form)"),
    ("work", "XR2-malformed", 1,
     "1 — Reg001001 captured the column pointer 'Sp. 60.' where a title belongs"),
    ("person", "XR2-blind", 7, "7"),
    ("person", "XR2-overrun", 2,
     "2 rows whose 'se:' target swallowed the following entry — a splitter defect"),
    ("place", "XR2-blind", 2, "2 (Ronco, Warszzava)"),
    ("non_fiction", "XR2-blind", 3, "3"),
    ("non_fiction", "XR5-see-also-blind", 1, "1"),
    ("novels_plays_tales", "XR2-blind", 1, "1"),
    ("novels_plays_tales", "XR5-see-also-blind", 3, "3"),
    ("personregister_xi", "XR2-blind", 7, "7"),
    ("personregister_xi", "XR2-linewrap", 3,
     "3 targets still carrying an unrejoined column break — "
     "scripts/segmentation/archive/apply_hyphen_linewrap_fixes.py is the repair"),
    ("personregister_xi", "XR1-no-target", 1,
     "1 — PerXI01219 ('August, Le Locle 14.9.1833. I 175.') is an ordinary "
     "entry typed as a cross-reference; it has page references and no target"),
    ("personregister_xi", "RV-stub-carries-content", 1,
     "1 — the same PerXI01219 row, seen from the other side"),
    ("personregister_xi", "RV-no-content", 5,
     "5 entries with neither a description nor a page reference, i.e. a bare "
     "name — each looks truncated in the source (e.g. 'Kameliadamen,')"),
]


@pytest.mark.parametrize("index,rule,ceiling,note",
                         CEILINGS, ids=[f"{i}-{r}" for i, r, _, _ in CEILINGS])
def test_unresolved_reference_counts_do_not_grow(counts, index, rule, ceiling, note):
    n = _n(counts, index, rule)
    assert n <= ceiling, (
        f"{index}/{rule}: {n} finding(s), ceiling {ceiling} ({note}). "
        f"New: {_detail(counts[1], index, rule)}"
    )


def test_cross_references_overwhelmingly_resolve(counts):
    # The blunt proportion check, kept as a backstop under the specific
    # rules above: they pin known defect families, this one notices if the
    # resolver or a parser breaks in a way none of them anticipated.
    findings = counts[1]
    unresolved = [r for r in findings.rows if r["severity"] in C.UNRESOLVED]
    total = 584  # cross-reference targets across the four indexes, measured
    assert len(unresolved) <= 45, (
        f"{len(unresolved)} unresolved cross-reference(s) of roughly {total} "
        "(baseline 41) — a jump this size means a splitter or resolver "
        "regression, not new source damage"
    )
