#!/usr/bin/env python3
"""
suggest_review_fixes.py
------------------------
Adds a 15_suggested_fix column to data/curated/personregister_xi_review.tsv,
attempting an automatic lookup for the "'se:'-mål ... findes ikke som
opslag" rows (a "se:" cross-reference target that doesn't match any
03_surname actually present in the register).

Two lookup passes, in order:
  1. Minor cleanup: strip a line-wrap hyphen + space inside the target
     ("Guer- cino" -> "Guercino", "Sachsen-Co- burg-Gotha" ->
     "Sachsen-Coburg-Gotha") and retry an exact match against the known
     surnames.
  2. Fuzzy match: if still unresolved, look for a known surname that
     differs by only 1-2 characters (difflib.get_close_matches on the
     FIRST comma-separated token of the target, since the target is
     "Surname[, Given names]"). Only a single, reasonably confident
     match is suggested; ties or weak matches are left blank rather
     than guessed.

This never edits 03_surname/12_see_also in the parsed data -- it only
annotates the review file for a human to confirm. Re-run
parse_personregister_xi.py first if the parsed TSV has changed; this
script always re-reads it fresh.

Run from the repo root:
  python scripts/parsers/suggest_review_fixes.py
"""
import csv
import difflib
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")
REVIEW_TSV = os.path.join(ROOT, "data", "curated", "personregister_xi_review.tsv")

# A line-wrap hyphen followed by whitespace inside a word ("Guer- cino",
# "Sachsen-Co- burg-Gotha") -- the hyphen is a genuine line-break
# artifact, not a real compound-word hyphen (a real one, e.g.
# "Burdet-Coutts", is never followed by a space in the source). Rejoined
# without the hyphen, matching how OCR reflow already de-hyphenates a
# soft-hyphen break elsewhere in the parser.
WRAP_HYPHEN_RE = re.compile(r"(\w)-\s+(\w)")


def clean_wrap_hyphen(name: str) -> str:
    return WRAP_HYPHEN_RE.sub(r"\1\2", name)


def target_surname_token(target: str) -> str:
    """The target field is 'Surname[, Given names]' -- only the surname
    part is looked up against 03_surname (given names are free text and
    would never match)."""
    return target.split(",")[0].strip()


# A roman-numeral-only difference ("Pius II" vs "Pius III") looks like a
# tiny edit but names a DIFFERENT person -- must never be suggested.
ROMAN_TAIL_RE = re.compile(r"\b[IVXLCDM]+\s*$")


def edit_op_count(a: str, b: str) -> int:
    """Total inserted+deleted+replaced characters between a and b (NOT a
    0-1 similarity ratio) -- the user asked for '1 or 2 letters spelled
    differently', which only a raw character-count threshold captures.
    A high difflib ratio alone accepts dangerous near-misses like "Pius
    II" vs "Pius III" (ratio 0.93) as readily as safe ones."""
    sm = difflib.SequenceMatcher(None, a, b)
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def suggest_fix(target: str, surnames_sorted: list[str], surnames_set: set[str]) -> str:
    token = target_surname_token(target)
    if not token:
        return ""

    # Pass 1: line-wrap hyphen cleanup, exact match.
    cleaned = clean_wrap_hyphen(token)
    if cleaned != token and cleaned in surnames_set:
        return f"'{cleaned}' (fjernet ombrydningsbindestreg)"

    # Pass 2: fuzzy match on the (cleaned) token against known surnames,
    # capped at a genuine 1-2 CHARACTER difference (not a similarity
    # ratio, which scales with word length and false-positives on short
    # names). Roman-numeral-only differences are rejected outright --
    # they name a different entity, not a typo of the same one. Short
    # tokens (<6 chars, e.g. "Borgo") are skipped entirely: a 1-2
    # character edit on a short name is a large fraction of the whole
    # word and matches several genuinely different, equally-plausible
    # surnames (checked: "Borgo" is within 1-2 edits of "Borgen",
    # "Boberg", "Broberg" -- all different people), so no single
    # suggestion is safe there.
    candidate_source = cleaned if cleaned != token else token
    if len(candidate_source) < 6:
        return ""
    matches = difflib.get_close_matches(candidate_source, surnames_sorted, n=3, cutoff=0.7)
    close = [
        m for m in matches
        if m != token
        and edit_op_count(candidate_source, m) <= 2
        and not (ROMAN_TAIL_RE.search(candidate_source) and ROMAN_TAIL_RE.search(m))
    ]
    if len(close) == 1:
        return f"'{close[0]}' (fuzzy match, muligt OCR-bogstavfejl)"
    # 0 or >=2 candidates: nothing safe to suggest (ambiguous or no hit).
    return ""


# A royal/noble title carried in the referring entry's own given-names
# field ("Victoria, Dronning" -> title "Dronning"). Used to disambiguate
# between several rulers of the same name under one country entry
# (e.g. "Victoria, Dronning af -" vs "Victoria, Prinsesse af —").
TITLE_RE = re.compile(r"\b(Dronning|Konge|Kejser|Kejserinde|Prins|Prinsesse|Hertug|Hertuginde|Kurfyrste|Storhertug|Storhertuginde)\b")


def suggest_country_ruler_fix(row: dict, parsed_rows: list[dict]) -> str:
    """A "se:" target naming a COUNTRY/dynasty is not itself a person
    entry -- the register files such people under the country, with the
    person's name in the given-names field ("Storbritannien og Irland |
    Victoria, Dronning af -"). So the lookup has to combine the target
    country with the referring entry's OWN name: "Victoria, Dronning,
    se: Storbritannien" resolves to the "Storbritannien og Irland" entry
    whose given-names start with "Victoria".

    A target may name two countries ("Danmark og Wales"), in which case
    each is looked up separately and all hits are reported -- that form
    is a genuine one-to-many cross-reference, not an ambiguity to
    suppress.
    """
    person = row["03_surname"].strip()
    if not person:
        return ""
    target = clean_wrap_hyphen(row["12_see_also"].strip()).rstrip(".")
    # Only the country part matters; drop any ", Given name" tail the
    # target itself carries (e.g. "Sverrig-Norge, Karl XIV Johan").
    target_head = target.split(",")[0].strip()
    countries = [c.strip() for c in re.split(r"\s+og\s+", target_head) if c.strip()]
    if not countries:
        return ""

    title_m = TITLE_RE.search(row["04_given_names"])
    title = title_m.group(1) if title_m else ""

    hits = []
    for country in countries:
        country_hits = [
            p for p in parsed_rows
            if p["03_surname"].startswith(country)
            and re.match(rf"{re.escape(person)}\b", p["04_given_names"].strip())
        ]
        if title and len(country_hits) > 1:
            titled = [p for p in country_hits if title in p["04_given_names"]]
            if titled:
                country_hits = titled
        hits.extend(country_hits)

    if not hits:
        return ""
    if len(hits) > 3:
        return ""  # too many to be a useful suggestion
    shown = "; ".join(f"{h['01_entry_id']} ({h['03_surname']}: {h['04_given_names']})" for h in hits)
    return f"{shown} (land + herskernavn)"


def suggest_alternatives_fix(target: str, surnames_set: set[str]) -> str:
    """A target naming two spelling variants ("Bruhn og Bruun", "Kaiser
    og Kayser", "Schou og Schouw") is a one-to-many cross-reference, not
    a single mistyped name -- look each variant up separately and report
    those that exist as their own entries."""
    cleaned = clean_wrap_hyphen(target.strip()).rstrip(".")
    if " og " not in cleaned or "," in cleaned:
        return ""
    variants = [v.strip() for v in re.split(r"\s+og\s+", cleaned) if v.strip()]
    if len(variants) < 2:
        return ""
    found = [v for v in variants if v in surnames_set]
    if not found:
        return ""
    return f"{', '.join(repr(v) for v in found)} (opslag pr. stavevariant)"


def suggest_reversed_name_fix(target: str, parsed_rows: list[dict], surnames_set: set[str]) -> str:
    """A target given in natural order ("Giulio Romano") when the
    register files it either as one whole surname ("Giulio Romano" --
    the register keeps some Italian artist names unsplit) or inverted
    into surname+given ("Romano, Giulio"). Exact matches only -- no
    fuzzy matching, so this cannot mis-fire."""
    raw = target.strip().rstrip(".")
    cleaned = clean_wrap_hyphen(raw)
    if "," in cleaned:
        return ""
    # The whole target is itself a surname entry, unsplit. (A target
    # that only needed the line-wrap hyphen removed is reported by the
    # caller's earlier hyphen pass, so only flag this when the target
    # was already hyphen-clean -- otherwise the label would misdescribe
    # what was actually fixed.)
    if cleaned in surnames_set:
        if cleaned == raw:
            return f"'{cleaned}' (opslag med hele navnet som opslagsord)"
        return ""
    tokens = cleaned.split()
    if len(tokens) != 2:
        return ""
    given, surname = tokens
    for p in parsed_rows:
        if p["03_surname"] == surname and p["04_given_names"].strip().startswith(given):
            return f"{p['01_entry_id']} ({p['03_surname']}, {p['04_given_names']}) (omvendt navnerækkefølge)"
    return ""


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        parsed_rows = list(csv.DictReader(f, delimiter="\t"))
    surnames_set = {r["03_surname"] for r in parsed_rows}
    surnames_sorted = sorted(surnames_set)

    with open(REVIEW_TSV, encoding="utf-8") as f:
        review_rows = list(csv.DictReader(f, delimiter="\t"))

    resolved = 0
    by_country = 0
    for r in review_rows:
        reason = r["14_review_reason"]
        suggestion = ""
        if "'se:'-mål" in reason and "findes ikke som opslag" in reason and r["12_see_also"]:
            # Country/dynasty targets first: a fuzzy surname match would
            # otherwise mis-suggest an unrelated person for these.
            suggestion = suggest_country_ruler_fix(r, parsed_rows)
            if suggestion:
                by_country += 1
            else:
                # Exact-match strategies before fuzzy: an "X og Y"
                # variant pair or an inverted name resolves precisely,
                # while a fuzzy surname match on the same string would
                # be a guess.
                suggestion = (
                    suggest_alternatives_fix(r["12_see_also"], surnames_set)
                    or suggest_reversed_name_fix(r["12_see_also"], parsed_rows, surnames_set)
                    or suggest_fix(r["12_see_also"], surnames_sorted, surnames_set)
                )
            if suggestion:
                resolved += 1
        r["15_suggested_fix"] = suggestion

    fieldnames = list(review_rows[0].keys())
    with open(REVIEW_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(review_rows)

    see_fail_count = sum(
        1 for r in review_rows
        if "'se:'-mål" in r["14_review_reason"] and "findes ikke som opslag" in r["14_review_reason"]
    )
    print(f"wrote {os.path.relpath(REVIEW_TSV, ROOT)}")
    print(f"  {see_fail_count} 'se:'-target-not-found rows; {resolved} got a suggested fix "
          f"({by_country} via land + herskernavn)")


if __name__ == "__main__":
    main()
