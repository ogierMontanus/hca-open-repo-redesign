"""
name_normalize.py
-------------------
Shared name/title normalization for the collin_letters_*_match.py
scripts. Two ranked levels, not one:

  1. `primary_keys(s)` -- the folds actually measured to help, applied
     unconditionally where safe:
       - æ -> ae, ø -> o always (ø/æ have no shared NFD decomposition
         with a plain letter, so without an explicit rule they either
         collide wrongly or silently vanish as non-alphanumeric -- this
         is the ö<->ø case: NFD reduces ö to bare "o" on its own, ø needs
         the explicit rule to land on the same "o").
       - å <-> "aa" tried BOTH ways (returns two keys), not folded to one.
         Doubling å to "aa" (the pre-1948 orthography convention, e.g.
         Aabenraa/Åbenrå) was measured against both the place index and
         the person index: 0 new matches gained in either, 1 lost in
         each (Håckeberga vs. the register's Häckeberga; Wingård vs. the
         register's Wingard) -- both losses share one shape: the
         register side had ALREADY dropped the diacritic to a bare "a"
         (an unrelated å/ä variant, or the diacritic just not being
         carried over), which NFD's own undoubled reduction handles for
         free and doubling breaks. Trying both keeps whatever upside
         doubling has for a future name that genuinely needs it, without
         that cost.
     See docs/data-model/collin-place-index.md and
     docs/data-model/collin-person-index.md for the measured numbers.

  2. `edge_case_key(s)` -- a general, uncalibrated fallback: strip EVERY
     Unicode diacritic uniformly (not just the Danish letters checked
     above), covering characters no one has hand-verified here (ü, é,
     ñ, ...). Only tried if (1) finds no unique match. A hit here is
     real signal -- the non-diacritic letters of the name matched
     exactly -- but ranks below a primary-key match precisely because
     the specific diacritic-only difference wasn't individually checked
     the way å/ø were. Callers should tag these with their own tier
     (e.g. "exact_diacritic_edge_case") rather than folding them into
     an unqualified "exact", so a human can tell at a glance which
     matches rest on a calibrated rule vs. an uncalibrated one.
"""

import re
import unicodedata


def _strip_combining(s):
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def primary_keys(s, keep_spaces=False):
    """Returns a set of 1-2 normalized keys. keep_spaces=True is for
    multi-word titles (works); False collapses to letters only (names)."""
    s = (s or "").strip()
    s = s.replace("æ", "ae").replace("Æ", "AE")
    s = s.replace("ø", "o").replace("Ø", "O")
    doubled = s.replace("å", "aa").replace("Å", "AA")
    pattern = r"[^A-Za-z0-9 ]" if keep_spaces else r"[^A-Za-z]"

    def finish(t):
        t = _strip_combining(t)
        t = re.sub(pattern, " " if keep_spaces else "", t)
        t = re.sub(r"\s+", " ", t).strip() if keep_spaces else t
        return t.upper()

    return {finish(doubled), finish(s)}


def edge_case_key(s, keep_spaces=False):
    """One coarse key: every diacritic stripped uniformly, no per-letter
    calibration. Deliberately separate from primary_keys() -- see module
    docstring."""
    s = (s or "").strip()
    t = _strip_combining(s)
    pattern = r"[^A-Za-z0-9 ]" if keep_spaces else r"[^A-Za-z]"
    t = re.sub(pattern, " " if keep_spaces else "", t)
    if keep_spaces:
        t = re.sub(r"\s+", " ", t).strip()
    return t.upper()
