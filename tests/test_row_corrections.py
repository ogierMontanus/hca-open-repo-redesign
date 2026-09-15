"""
Tests for suggest_row_corrections.

The thing worth protecting here is not that it finds fusions — it is that it
finds the *right kind* of fusion and refuses the rest. Every test below is a
case the scanner actually produces.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "src", ROOT / "scripts" / "segmentation" / "suggest_row_corrections.py")
src = importlib.util.module_from_spec(spec)
sys.modules["src"] = src
spec.loader.exec_module(src)


def row(pid, surname="Ahrenberg", given="", desc="", parsed=""):
    return {"00_person_id": pid, "01_entry_id": pid[-3:], "02_entry_type": "person",
            "03_surname": surname, "04_given_names": given, "05_sort_key": surname,
            "06_birth_year": "", "07_death_year": "", "08_year_note": "",
            "09_description": desc, "10_references_raw": "",
            "11_references_parsed": parsed, "12_see_also": "", "13_raw_text": ""}


# ---- the citation run -------------------------------------------------------

def test_expands_a_page_range_under_its_volume():
    assert src.expand("I", "298 383-85") == ["I:298", "I:383", "I:384", "I:385"]


def test_an_abbreviated_range_end_is_completed_from_its_start():
    # "407-09" is 407-409, not volume II-407 page 09 — the bug that cost
    # about a thousand references when the V0.94 ingester right-split it
    assert src.expand("II", "407-09") == ["II:407", "II:408", "II:409"]
    assert src.expand("II", "500-10")[-1] == "II:510"


def test_an_implausible_range_is_read_as_a_single_page():
    # 400 consecutive pages about one person is a misread, not a citation
    assert src.expand("II", "100-990") == ["II:100"]


def test_recovers_only_citations_not_already_carried():
    r = row("HCAP1", desc="Rektor. I 298 383. Ahrens (Arenz), Portugiser.",
            parsed="I:298")
    found = src.find_splits([r], {"ahrenberg"})
    t1 = [f for f in found if f["tier"] == "1"]
    assert t1 and t1[0]["proposal"] == "I:383"      # I:298 was already there


# ---- where the row is cut ---------------------------------------------------

def test_the_tail_keeps_its_first_character():
    # REF_FUSED ends on \S, which used to eat the next entry's initial letter
    r = row("HCAP2", given="Aimé's Far. VII 89 174. Amé", desc="")
    found = src.find_splits([r], {"ahrenberg"})
    trim = [f for f in found if f["action"] == "trim the column"]
    assert trim and trim[0]["evidence"].startswith("Amé")


def test_a_row_fused_twice_is_cut_at_the_last_boundary():
    r = row("HCAP3", desc="Digter. I 12. Bo, Hans, Præst. II 34. Cras, Ida, Frue (1801).")
    found = src.find_splits([r], {"ahrenberg"})
    trim = [f for f in found if f["action"] == "trim the column"]
    assert trim and trim[0]["evidence"].startswith("Cras")


# ---- what counts as a new entry --------------------------------------------

def test_an_alphabet_divider_is_not_a_name():
    assert src.tail_head("X. Xenophon, græsk Historiker") == "Xenophon"
    assert src.tail_head("F. Faaborg, Christian") == "Faaborg"


def test_a_genitive_is_a_relation_not_an_entry():
    assert src.tail_head("Amé's Far") is None


def test_a_bare_initial_is_not_an_entry():
    assert src.tail_head("R. R.") is None


def test_no_split_is_proposed_when_the_tail_already_has_its_own_row():
    r = row("HCAP4", desc="Rektor. I 298. Ahrens (Arenz), Portugiser.")
    found = src.find_splits([r], {"ahrenberg", "ahrens"})
    assert not [f for f in found if f["action"] == "split out a new row"]
    assert [f for f in found if "already exists" in f["action"]]


def test_a_split_is_proposed_when_it_does_not():
    r = row("HCAP5", desc="Rektor. I 298. Ahrens (Arenz), Portugiser.")
    found = src.find_splits([r], {"ahrenberg"})
    assert [f for f in found if f["action"] == "split out a new row"]


# ---- the reverse defect -----------------------------------------------------

def test_scanner_confusions_are_told_from_lookalike_names():
    assert src.ocr_confusable("Amesen Kali", "Arnesen Kali")      # rn -> m
    assert src.ocr_confusable("Clausen-Schiitz", "Clausen-Schütz")  # ii -> ü
    assert src.ocr_confusable("Golloredo-Mansfeld", "Colloredo-Mansfeld")
    assert not src.ocr_confusable("Jensen", "Jørgensen")
    assert not src.ocr_confusable("Philipsen", "Philips")


def test_one_shared_page_is_not_evidence_of_a_duplicate():
    rows = [row("HCAP6", "Droscher", parsed="I:10"),
            row("HCAP7", "Dröscher", parsed="I:10")]
    assert not src.find_merges(rows)


def test_two_shared_pages_under_a_confusable_name_are():
    rows = [row("HCAP6", "Droscher", parsed="I:10;I:11"),
            row("HCAP7", "Dröscher", parsed="I:10;I:11")]
    m = src.find_merges(rows)
    assert m and m[0]["kind"] == "ocr_twin"


# ---- what the proposal is allowed to change --------------------------------

def test_the_proposal_never_overwrites_parsed_references():
    rows = [row("HCAP8", desc="Rektor. I 298 383. Ahrens, Portugiser.",
                parsed="I:298")]
    fields = list(rows[0].keys())
    found = src.find_splits(rows, {"ahrenberg"})
    proposed, out_fields, n1, n2 = src.apply_safe(rows, fields, found)
    assert proposed[0]["11_references_parsed"] == "I:298"
    assert proposed[0][src.RECOVERED_COL] == "I:383"
    assert src.RECOVERED_COL in out_fields


def test_the_proposal_keeps_every_row():
    rows = [row(f"HCAP{i}", desc="Rektor. I 1. Bo, Hans.") for i in range(5)]
    fields = list(rows[0].keys())
    found = src.find_splits(rows, set())
    proposed, _, _, _ = src.apply_safe(rows, fields, found)
    assert len(proposed) == len(rows)          # a split is proposed, never applied


def test_the_real_register_is_never_written():
    assert src.MASTER != src.PROPOSED
    assert src.PROPOSED.name.endswith(".proposed.tsv")
