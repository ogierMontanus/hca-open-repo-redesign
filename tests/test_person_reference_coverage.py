"""Guard the person register's coverage against the independent transcription.

These are the regression tests the segmentation record asks for and that did
not exist: its coverage measurement was carried out by hand and written up as
prose, so every later change to the register has been unmeasurable, and it
notes explicitly that nothing catches a future repeat of the duplicate classes
that were found reactively.

The bounds are deliberately loose. They exist to catch a *change of shape* —
a batch import that silently doubles entries, a parser re-run that discards
the cleaning chain — not to pin the register to today's figures. Tighten them
only after re-measuring, exactly as the record says of the row-count test.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validation" / "compare_to_reference.py"
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import compare_to_reference as ctr  # noqa: E402


@pytest.fixture(scope="module")
def measured():
    ours = ctr.load_ours()
    ref, stubs = ctr.load_reference()
    ours_by_sig = ctr.index_by_signature(ours)
    ref_by_sig = ctr.index_by_signature(ref)
    ours_cores = {r["core"] for r in ours}
    ref_cores = {r["core"] for r in ref}
    only_ours = [r for r in ours if r["core"] not in ref_cores]
    only_ref = [r for r in ref if r["core"] not in ours_cores]
    _, real_ours = ctr.classify(only_ours, ref, ref_by_sig)
    _, real_ref = ctr.classify(only_ref, ours, ours_by_sig)
    return {
        "ours": ours, "ref": ref, "stubs": stubs,
        "real_ours": real_ours, "real_ref": real_ref,
        "dups": ctr.duplicate_scan(ours),
    }


def test_both_sides_load(measured):
    assert len(measured["ours"]) > 9000
    assert len(measured["ref"]) > 9000


def test_reference_redirect_share_is_plausible(measured):
    """~690 of the transcription's rows are 'se:' redirects.

    This guards the classifier, not the data. An earlier draft treated every
    row without a tabulated citation as a redirect and excluded 1,276 — 594
    of them real people — which inflated the apparent surplus by roughly that
    number. If this count drifts far, the redirect pattern has stopped
    matching one of the spellings the register prints ('ogsaa' and 'også').
    """
    assert 550 <= measured["stubs"] <= 850


def test_net_difference_stays_small(measured):
    """The two sides are practically coverage-equal.

    The last hand measurement reached a net of ~10 real entries. Anything in
    the low tens means the register still covers what the transcription does;
    a jump to the hundreds means a batch operation changed the segmentation
    and nobody measured it.
    """
    net = abs(len(measured["real_ours"]) - len(measured["real_ref"]))
    assert net < 120, (
        f"net real difference is {net}: "
        f"{len(measured['real_ours'])} unmatched here, "
        f"{len(measured['real_ref'])} unmatched in the reference. "
        "Re-measure with scripts/validation/compare_to_reference.py --write."
    )


def test_duplicate_candidates_do_not_grow(measured):
    """Known weakness #3, now actually tested.

    66 groups at the time of writing. The bound is a ceiling on *growth*:
    these are candidates for review, not confirmed duplicates, and the number
    should fall as they are worked through — never rise.
    """
    n = len(measured["dups"])
    assert n <= 90, (
        f"{n} duplicate-candidate groups, up from 66. A new import may have "
        "reintroduced the twins the dedupe passes removed. See "
        "data/curated/person_duplicate_candidates.csv."
    )


def test_given_name_compatibility_separates_families_from_duplicates():
    """The filter that makes the duplicate scan usable.

    Siblings share a surname, a page and nothing else; without this test the
    scan returns ~500 groups that are mostly families.
    """
    ok = ctr.given_names_compatible
    assert ok("", "Carl")                    # bare surname vs named
    assert ok("C.", "Carl")                  # initial vs full
    assert ok("J. C.", "Jens Christian")     # two initials
    assert ok("Carl", "Carl")
    assert not ok("Frieda", "Ida")           # the Anholm sisters
    assert not ok("Caroline", "Vilhelm")


def test_script_runs_end_to_end():
    r = subprocess.run([sys.executable, str(SCRIPT), "--limit", "0"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "NET real difference" in r.stdout
