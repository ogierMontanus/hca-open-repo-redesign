"""Guard the additive person-reference merge (plan step 10c).

The merge folds the segmentation's page references into the live set. Its
whole safety argument is that it only ever *adds*: the V0.82 rows stay
untouched and keep their `Reg…` ids, so no person URL changes, nothing can be
lost, and the step is undone by dropping the added rows.

These tests hold that argument up. If any of them fails, the merge has stopped
being additive and the reversibility claim is void.
"""

import csv
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "data" / "normalized" / "references.csv"
ENTS = ROOT / "data" / "normalized" / "entities.csv"
PAGES = ROOT / "data" / "normalized_v094" / "diary_pages.csv"


def _rows(p, **kw):
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, **kw))


@pytest.fixture(scope="module")
def refs():
    return _rows(REFS)


@pytest.fixture(scope="module")
def committed_refs():
    """references.csv as git has it — the pre-merge state is the baseline."""
    out = subprocess.run(["git", "show", "HEAD:data/normalized/references.csv"],
                         cwd=ROOT, capture_output=True, encoding="utf-8")
    if out.returncode != 0:
        pytest.skip("no committed references.csv to compare against")
    return list(csv.DictReader(out.stdout.splitlines()))


def test_every_reference_resolves_to_an_entity(refs):
    ids = {r["entity_id"] for r in _rows(ENTS)}
    orphans = {r["entity_id"] for r in refs if r["entity_id"] not in ids}
    assert not orphans, f"{len(orphans)} references to unknown entities"


def test_merge_introduced_no_duplicate_citations(refs, committed_refs):
    """49 (entity, vol, page) duplicates pre-date the merge. It added none."""
    def dupes(rows):
        c = Counter((r["entity_id"], r["vol"], r["page"]) for r in rows)
        return {k for k, n in c.items() if n > 1}
    assert not (dupes(refs) - dupes(committed_refs)), "the merge created duplicates"


def test_no_person_lost_a_reference(refs, committed_refs):
    """The superset criterion from the plan's section J.6."""
    def pageset(rows):
        d = defaultdict(set)
        for r in rows:
            d[r["entity_id"]].add((r["vol"], r["page"]))
        return d
    before, after = pageset(committed_refs), pageset(refs)
    shrunk = [e for e, pages in before.items() if not pages <= after.get(e, set())]
    assert not shrunk, f"{len(shrunk)} entities lost references, e.g. {shrunk[:5]}"


@pytest.mark.skipif(not PAGES.exists(), reason="V0.94 not ingested")
def test_added_references_cite_pages_that_exist(refs, committed_refs):
    """The merge filters invalid citations; nothing invalid may slip in.

    The live set already contains 329 references to non-existent pages, which
    predate this and are reported by check_page_references.py. The merge must
    not add to them.
    """
    valid = {(r["vol"].strip(), r["page"].strip()) for r in _rows(PAGES)}
    old = {(r["page_id"], r["entity_id"], r["vol"], r["page"], r["seq"])
           for r in committed_refs}
    added = [r for r in refs
             if (r["page_id"], r["entity_id"], r["vol"], r["page"], r["seq"]) not in old]
    bad = [r for r in added if (r["vol"].strip(), r["page"].strip()) not in valid]
    assert not bad, f"{len(bad)} added references cite pages that do not exist"


def test_fused_entries_stayed_out(refs):
    """Scharff, Elvilda is the canary.

    Her register entry absorbed her neighbour's citation list — her own three
    pages sit in the description while 11_references_parsed runs to 275. She
    has 3 live references and must still have 3: if she has hundreds, the
    fusion guard in merge_person_references.py has stopped working and
    hundreds of pages are attributed to the wrong person.
    """
    scharff = [r for r in refs if r["entity_id"] == "Reg0111220"]
    assert len(scharff) < 20, (
        f"Reg0111220 (Scharff, Elvilda) now has {len(scharff)} references; "
        "a fused entry was merged"
    )
