"""Use V0.94 as a second opinion on data it does not yet own.

Two independent sources for the same field are worth more as a cross-check
than as a replacement, and that is the shape the V0.94 adoption actually took:
of the four "unambiguous wins" the migration plan listed, measuring turned one
into a non-win and left two blocked on identity rather than attributes.

These tests keep the agreement honest. If V0.94 and the live pipeline drift
apart, something changed upstream and someone should know which side moved.

They skip rather than fail when the V0.94 ingest has not been run, so a
checkout without `data/normalized_v094/` still passes.
"""

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
V094 = ROOT / "data" / "normalized_v094"
NORM = ROOT / "data" / "normalized"

pytestmark = pytest.mark.skipif(
    not (V094 / "entities.csv").exists(),
    reason="V0.94 not ingested — run scripts/normalization/hca_v094_to_csv.py",
)


def _rows(path, **kw):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, **kw))


def test_kb_links_agree_exactly():
    """The reason the KB link source was NOT switched.

    build_kb_links.py derives these from the OffSetTab rule and reports where
    the workbook disagrees — which caught vol I page 13. V0.94 states them
    without deriving, so it cannot make that check. Keeping both and requiring
    agreement is strictly better than replacing one with the other.
    """
    live = {(r["vol"], str(int(r["page"]))): r["kb_url"]
            for r in _rows(NORM / "kb_diary_links.csv")}
    v94 = {(r["vol"], str(int(r["page"]))): r["kb_url"].strip()
           for r in _rows(V094 / "diary_pages.csv") if r["kb_url"]}

    assert len(live) == len(v94) == 4413
    differing = {k for k in live.keys() & v94.keys() if live[k] != v94[k]}
    assert not differing, (
        f"{len(differing)} KB links disagree between the workbook rule and "
        f"V0.94, e.g. {sorted(differing)[:3]}. One source moved; find out which."
    )


def test_work_crosswalk_stays_complete():
    """OLDWorkID is the one identifier V0.94 carries that reaches the live data.

    3,590 of 3,590 at the time of writing. It is what would make a works
    cutover safe, so a drop is the single most important V0.94 regression to
    catch.
    """
    live_ids = {r["entity_id"] for r in _rows(NORM / "entities.csv")}
    walk = [r for r in _rows(V094 / "id_crosswalk.csv")
            if r["entity_type"] == "work"]
    resolved = sum(1 for r in walk if r["legacy_id"] in live_ids)
    assert walk, "no work rows in the V0.94 crosswalk"
    assert resolved == len(walk), (
        f"work crosswalk fell to {resolved:,}/{len(walk):,}"
    )


def test_place_identity_is_still_the_blocker():
    """Places are blocked on identity, not attributes — assert the diagnosis.

    If OLDLocationID ever starts resolving, the place adoption becomes a much
    smaller job and this test failing is the signal to revisit it.
    """
    live_ids = {r["entity_id"] for r in _rows(NORM / "entities.csv")}
    walk = [r for r in _rows(V094 / "id_crosswalk.csv")
            if r["entity_type"] == "place"]
    resolved = sum(1 for r in walk if r["legacy_id"] in live_ids)
    assert resolved == 0, (
        f"{resolved:,} place ids now resolve into the live register — "
        "the identity blocker described in scripts/_lib/sources.py has "
        "changed. Revisit the place adoption."
    )


def test_place_attributes_do_not_contradict_the_live_data():
    """V0.94's place country/category are a superset, not a disagreement.

    Measured: of 2,327 places shared by label, country disagrees on 1 and
    category on 5, and every disagreement is the live side being empty. A real
    contradiction — both sides non-empty and different — would mean one of
    them is wrong and needs a human.
    """
    live = {r["label"].strip().lower(): r
            for r in _rows(NORM / "steder_verified_categories.csv")}
    v94 = {r["label"].strip().lower(): r
           for r in _rows(V094 / "entities.csv") if r["entity_type"] == "place"}

    def real(v):
        v = (v or "").strip()
        return v if v not in ("", "0") else ""

    contradictions = []
    for k in live.keys() & v94.keys():
        for live_col, v94_col in (("country", "description"), ("category", "genre_h2")):
            a, b = real(live[k][live_col]), real(v94[k][v94_col])
            if a and b and a != b:
                contradictions.append((k, live_col, a, b))
    assert len(contradictions) < 20, (
        f"{len(contradictions)} places where both sources give a value and "
        f"they differ, e.g. {contradictions[:3]}"
    )


def test_v094_artist_is_not_the_same_field_as_person_derived():
    """Do not merge V0.94's Artist into person_derived. They differ in kind.

    Where both are filled and disagree, V0.94 names the AUTHOR of a literary
    work and the live regex names the ILLUSTRATOR pulled out of the title
    parenthesis. "Eventyr. Med 125 Ill. efter Originaltegninger af V.
    Pedersen" is "H.C. Andersen" to V0.94 and "V. Pedersen" to the regex; both
    are right about different questions.

    This test exists because the migration plan listed the Artist column as a
    win that would retire the regex, and it is the opposite. If the
    disagreement count ever collapses, the two sources have converged on one
    meaning and the merge becomes worth revisiting — which is a reason to look,
    not a reason to have merged.
    """
    live = {r["entity_id"]: r for r in _rows(NORM / "entities.csv")
            if r["entity_type"] == "work"}
    v94 = {r["entity_id"]: r for r in _rows(V094 / "entities.csv")
           if r["entity_type"] == "work"}
    walk = {r["v094_id"]: r["legacy_id"] for r in _rows(V094 / "id_crosswalk.csv")
            if r["entity_type"] == "work" and r["legacy_id"]}

    differ = 0
    for k, v in v94.items():
        reg = walk.get(k)
        if reg not in live:
            continue
        a = (live[reg].get("person_derived") or "").strip()
        b = (v.get("person_derived") or "").strip()
        if a and b and a != b:
            differ += 1
    assert differ > 100, (
        f"only {differ} work-artist disagreements between V0.94 and the live "
        "regex; they used to number 331. The two may have converged on one "
        "meaning — re-read scripts/_lib/sources.py before merging anything."
    )


def test_billedkunst_artists_still_come_from_the_regex():
    """V0.94 cannot supply the billedkunst artist facet.

    Across the 921 shared BILLEDKUNST works the live regex fills 267 and
    V0.94 fills 3. Swapping the source would empty the facet.
    """
    live = {r["entity_id"]: r for r in _rows(NORM / "entities.csv")
            if r["entity_type"] == "work"}
    v94 = {r["entity_id"]: r for r in _rows(V094 / "entities.csv")
           if r["entity_type"] == "work"}
    walk = {r["v094_id"]: r["legacy_id"] for r in _rows(V094 / "id_crosswalk.csv")
            if r["entity_type"] == "work" and r["legacy_id"]}

    live_filled = v94_filled = 0
    for k, v in v94.items():
        reg = walk.get(k)
        if reg not in live or live[reg].get("genre_h2") != "BILLEDKUNST":
            continue
        live_filled += bool((live[reg].get("person_derived") or "").strip())
        v94_filled += bool((v.get("person_derived") or "").strip())
    assert live_filled > 200, f"regex coverage fell to {live_filled}"
    assert v94_filled < live_filled, (
        f"V0.94 now fills {v94_filled} billedkunst artists against the "
        f"regex's {live_filled} — it may finally be the better source"
    )


def test_the_wor_to_Pag_label_corruption_has_not_spread():
    """18 live labels have "wor" replaced by "Pag" — Kenilworth as
    "KenilPagth", Household words as "Household Pagds".

    Upstream damage in the V0.82 workbook, reported by
    scripts/validation/check_label_corruption.py and deliberately not repaired
    here. This holds the line: the count should fall when the workbook is
    fixed, never rise.
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "validation"))
    import check_label_corruption as clc          # its rule, not a copy of it

    hits = [r["entity_id"] for r in _rows(NORM / "entities.csv")
            if clc.EMBEDDED_PAG.search(r.get("label") or "")
            and not clc.is_legitimate(r.get("label") or "")]
    assert len(hits) <= 18, (
        f"{len(hits)} corrupted labels, up from 18: {hits[:5]}. "
        "See data/review/label_corruption.csv. If the new one is a real "
        "Pag- name, add it to LEGITIMATE in check_label_corruption.py."
    )
