#!/usr/bin/env python3
"""
parse_person_role.py
---------------------
Derives a "Rolle / Erhverv" (role/occupation) facet for every person in
PERSON-REGISTER, from two independent sources, combined (a person can carry
more than one role):

  A) VÆRK-REGISTER occurrence — a person who authored a BILLEDKUNST work is
     tagged "Kunstner/Billedkunst", a BIBLIOTEK work "Forfatter/Digter", a
     TEATER & MUSIK work "Musiker/Scenekunst". Resolved via the exact same
     nameKey() surname+initials matching mockup/js/entity-refs.js already
     uses for worksByAuthor() — so this agrees with what a reader already
     sees on a person's own detail page, rather than inventing a second,
     possibly-inconsistent name-matching scheme.

  B) A harvest from PERSON-REGISTER's own description field, in the two
     steps the task asked for:
       1. Frequency count of every capitalized-initial word across all
          9,466 descriptions that carry one (see the harvest print at the
          bottom of this docstring's development history — 6,175 distinct
          candidate terms; top ones: professor 323, forfatter 304,
          kammerherre 263, maler 248, sognepræst 240, digter 238, …).
       2. The high-frequency terms from that harvest are hand-clustered
          into data/curated/person_role_terms_da.csv — ~185 terms grouped
          into 9 buckets (Gejstlig, Militær, Adel/Kongelig/Hof,
          Embedsmand/Jura/Politik, Handel/Erhverv, Akademiker/Lærd,
          Kunstner/Billedkunst, Musiker/Scenekunst, Forfatter/Digter) —
          "10 or so" buckets suitable for a filter panel, per the brief.
          A term not in the CSV contributes nothing; a person matching no
          term and with no VÆRK-REGISTER role gets an empty role list —
          NOT an error, the same way "Endnu ubestemt" is a legitimate
          category on the Køn facet, not a parsing failure.

A person's family-relation clause ("Søn af X, Broder til Fru Y, ...") is
stripped before harvesting — same referent-safety concern
parse_person_gender.py already had to solve: a title/occupation word
describing a RELATIVE, not the register subject, must not be attributed to
the subject. RELATION_RE below strips the whole clause rather than just the
marker word, since an occupation harvest (unlike gender) has no reliable
per-word "is this predicative" check to fall back on.

Run after scripts/build_mockup/build_works_extra.py (reads its output,
mockup/data/works-extra.js, for the værk-register role source).

Writes data/normalized/person_role.csv:
  entity_id, roller, kilde_vaerk, kilde_beskrivelse_termer

  roller                    — semicolon-joined bucket names, e.g.
                               "Gejstlig;Akademiker/Lærd"
  kilde_vaerk                — semicolon-joined wing labels that
                               contributed via source A (empty if none)
  kilde_beskrivelse_termer   — semicolon-joined harvested terms that
                               contributed via source B (empty if none;
                               kept for audit — see report() below)
"""

import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTITIES = os.path.join(ROOT, "data", "normalized", "entities.csv")
REFS = os.path.join(ROOT, "data", "normalized", "references.csv")
# Built register cards from the publication repo (hca-open-repo). They are a
# BUILD artefact, so they live in the other repository; point
# HCA_MOCKUP_DATA_DIR at its mockup/data/ folder, or keep the two repos as
# siblings and the default below finds it.
MOCKUP_DATA_DIR = os.environ.get(
    "HCA_MOCKUP_DATA_DIR",
    os.path.join(ROOT, os.pardir, "hca-open-repo", "mockup", "data"),
)
WORKS_EXTRA_JS = os.path.join(MOCKUP_DATA_DIR, "works-extra.js")
TERMS_CSV = os.path.join(ROOT, "data", "curated", "person_role_terms_da.csv")
OUT_CSV = os.path.join(ROOT, "data", "normalized", "person_role.csv")

WING_BUCKET = {
    "billedkunst.html": "Kunstner/Billedkunst",
    "bibliotek.html": "Forfatter/Digter",
    "teater-musik.html": "Musiker/Scenekunst",
}

# Bucket display order — used only for the audit report below; the facet
# itself (FacetEngine's default multi-value handling, same as Nationalitet)
# sorts by count, not this fixed order.
BUCKET_ORDER = [
    "Gejstlig", "Militær", "Adel/Kongelig/Hof", "Embedsmand/Jura/Politik",
    "Handel/Erhverv", "Akademiker/Lærd", "Kunstner/Billedkunst",
    "Musiker/Scenekunst", "Forfatter/Digter",
]


# ---------------------------------------------------------------------
# nameKey() — ported 1:1 from mockup/js/entity-refs.js so this agrees
# with the site's own author→person resolution (worksByAuthor()).
# ---------------------------------------------------------------------
def _fold(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def name_key(s):
    if not s:
        return None
    s = re.split(r"[\(\（\[]", s, 1)[0].strip()
    if not s:
        return None
    if "," in s:
        parts = s.split(",")
        surname, given = parts[0], " ".join(parts[1:])
    else:
        toks = s.split()
        if not toks:
            return None
        surname, given = toks[-1], " ".join(toks[:-1])
    sk = re.sub(r"[^a-zæøå]", "", _fold(surname))
    if not sk:
        return None
    inits = sorted({t[0] for t in re.split(r"[\s.]+", _fold(given)) if t})
    return sk + "|" + "".join(inits)


# ---------------------------------------------------------------------
# Relation-clause stripping — same concern as parse_person_gender.py's
# POSSESSIVE_RE/_relation_hits, applied here to whole clauses rather than
# single marker words: an occupation word inside "Broder til Fru Therese
# Henriques, Typograf." belongs to the SUBJECT here (Typograf follows the
# clause), but "Søn af N.C.L.A., Skuespiller ved..." — the occupation
# belongs to the subject too once the "Søn af X," clause is dropped. Only
# a leading relation clause is stripped; mid-description relation clauses
# ("g. m. NN, Præst i Y") still have their own occupation attributed to
# the spouse, which is a known limitation matching gender's own "referent"
# class of issues — see docs/data-model/person-role-facet.md.
# Connector is (af|til|efter) for every relation word, not just Enke/
# Enkemand — checked against the actual corpus (10,228 descriptions):
# "Enke efter" is the dominant form for widowhood (142×, "widow OF [her
# late husband]" — his occupation, not hers), while every other relation
# word in this list only ever occurs with af/til, but there's no harm in
# accepting all three connectors uniformly.
RELATION_RE = re.compile(
    r"^(Søn|Datter|Broder|Søster|Søstersøn|Søsterdatter|Broderdatter|"
    r"Brodersøn|Svigersøn|Svigerdatter|Svoger|Hustru|Enke|Enkemand|"
    r"Fætter|Kusine|Nevø|Niece|Plejedatter|Plejesøn|Moder|Fader|"
    r"Adoptivdatter|Adoptivsøn|Steddatter|Stedsøn|Sønnesøn|Sønnedatter|"
    r"Dattersøn|Datterdatter)"
    r"\s+(af|til|efter)\s+[^,.;]+[,.;]\s*",
    re.I,
)
# The year after "g." (gift/married) is sometimes a range ("g. 1846–1870
# m. ...", a consort's reign/marriage span) rather than a single year — the
# range needs matching too, or the whole clause fails to strip and the
# spouse's own title/occupation leaks onto the subject (seen on Isabella II
# of Spain's entry: an unstripped "g. 1846–1870 m. Hertug ... Konge af S."
# attributed her husband's "Hertug"/"Konge" to her). Only the clause up to
# the next comma/period is dropped — a further appositive after that comma
# ("m. NN, titulær Konge af S.") can still describe the spouse and leak
# through; that's a known remaining gap, not attempted here (see
# docs/data-model/person-role-facet.md).
MARRIED_RE = re.compile(r"\bg\.\s*(\d{4}(–\d{4})?)?\s*m\.\s*[^,.;]+[,.;]?\s*", re.I)
WORD_RE = re.compile(r"\b[A-ZÆØÅ][a-zæøåA-ZÆØÅ'\-]{2,}\b")


def harvest_terms(description, term_bucket):
    """Returns [(term, bucket), ...] for every curated-CSV term found in
    the description, after stripping a leading relation clause. Order
    preserved, duplicates kept (caller dedupes buckets, keeps all terms
    for the audit column)."""
    d = (description or "").strip()
    if not d:
        return []
    d = RELATION_RE.sub("", d)
    d = MARRIED_RE.sub("", d)
    hits = []
    for w in WORD_RE.findall(d):
        wl = w.lower()
        bucket = term_bucket.get(wl)
        if bucket:
            hits.append((wl, bucket))
    return hits


def load_terms():
    if not os.path.exists(TERMS_CSV):
        sys.exit(f"Missing {TERMS_CSV}")
    term_bucket = {}
    with open(TERMS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            term = (r.get("term") or "").strip().lower()
            bucket = (r.get("bucket") or "").strip()
            if term and bucket:
                term_bucket[term] = bucket
    return term_bucket


def load_works_extra():
    if not os.path.exists(WORKS_EXTRA_JS):
        sys.exit(
            f"Missing {WORKS_EXTRA_JS} — run "
            "scripts/build_mockup/build_works_extra.py first."
        )
    text = open(WORKS_EXTRA_JS, encoding="utf-8").read()
    json_text = text.split("const WORKS_EXTRA = ", 1)[1].rstrip("\n").rstrip(";")
    return json.loads(json_text)


def main():
    if not os.path.exists(ENTITIES):
        sys.exit(f"Missing {ENTITIES}")

    print(f"Loading {os.path.relpath(ENTITIES, ROOT)}…")
    persons = []
    with open(ENTITIES, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["entity_type"] == "person":
                persons.append(r)
    print(f"  {len(persons):,} persons")

    term_bucket = load_terms()
    print(f"  {len(term_bucket):,} harvested terms loaded from "
          f"{os.path.relpath(TERMS_CSV, ROOT)} "
          f"({len(set(term_bucket.values()))} buckets)")

    works = load_works_extra()
    print(f"  {len(works):,} works loaded from "
          f"{os.path.relpath(WORKS_EXTRA_JS, ROOT)}")

    # Reverse index: nameKey(author) -> set of wings, exactly mirroring
    # entity-refs.js's worksByAuthor() build step.
    wings_by_namekey = defaultdict(set)
    for w in works.values():
        author = w.get("author")
        wing = w.get("wing")
        if not author or wing not in WING_BUCKET:
            continue
        k = name_key(author)
        if k:
            wings_by_namekey[k].add(wing)

    rows_out = []
    bucket_counts = Counter()
    source_a_only = source_b_only = both = neither = 0
    term_hit_counts = Counter()

    for r in persons:
        rid = r["entity_id"]
        label = (r.get("label") or "").strip()
        desc = r.get("description") or ""

        roles = set()
        wings_hit = set()
        k = name_key(label)
        if k and k in wings_by_namekey:
            for wing in wings_by_namekey[k]:
                roles.add(WING_BUCKET[wing])
                wings_hit.add(wing)

        term_hits = harvest_terms(desc, term_bucket)
        terms_hit = []
        for term, bucket in term_hits:
            roles.add(bucket)
            terms_hit.append(term)
            term_hit_counts[term] += 1

        if wings_hit and terms_hit:
            both += 1
        elif wings_hit:
            source_a_only += 1
        elif terms_hit:
            source_b_only += 1
        else:
            neither += 1

        for b in roles:
            bucket_counts[b] += 1

        rows_out.append({
            "entity_id": rid,
            "roller": ";".join(sorted(roles)),
            "kilde_vaerk": ";".join(sorted(wings_hit)),
            "kilde_beskrivelse_termer": ";".join(terms_hit),
        })

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["entity_id", "roller", "kilde_vaerk", "kilde_beskrivelse_termer"]
        )
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nWrote {os.path.relpath(OUT_CSV, ROOT)}")

    report(persons, rows_out, bucket_counts, source_a_only, source_b_only,
           both, neither, term_hit_counts, term_bucket)


def report(persons, rows_out, bucket_counts, source_a_only, source_b_only,
           both, neither, term_hit_counts, term_bucket):
    total = len(persons)
    with_role = total - neither
    print("\n=== Rolle/Erhverv — dækningsrapport ===")
    print(f"Total personer: {total:,}")
    print(f"Med mindst én rolle: {with_role:,} ({with_role/total:.0%})")
    print(f"  kun VÆRK-REGISTER: {source_a_only:,}")
    print(f"  kun beskrivelses-høst: {source_b_only:,}")
    print(f"  begge kilder: {both:,}")
    print(f"Uden rolle (Uklassificeret): {neither:,} ({neither/total:.0%})")

    print("\nFordeling pr. bucket (en person kan tælle i flere):")
    for b in BUCKET_ORDER:
        print(f"  {bucket_counts.get(b, 0):5,}  {b}")

    print(f"\nDistinkte høstede termer der ramte mindst én gang: "
          f"{len(term_hit_counts):,} af {len(term_bucket):,} i CSV'en")
    unused = sorted(set(term_bucket) - set(term_hit_counts))
    if unused:
        print(f"Termer i CSV'en der ALDRIG matchede noget i korpusset "
              f"({len(unused)} — kandidater til fjernelse eller stavefejl):")
        for t in unused:
            print(f"  {t}  ->  {term_bucket[t]}")


if __name__ == "__main__":
    main()
