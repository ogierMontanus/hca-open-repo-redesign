"""Index-local knowledge for the register integrity checks.

Every rule in `check_indexes.py` needs to know three things about the index
it is checking, and all three differ per index:

  1. **What its rows are.** The person register calls a row an entry_type;
     the work sub-registers call it a Posttype. Both distinguish an ordinary
     entry from a cross-reference stub, and the sub-entry / container kinds
     exist in only one index each.
  2. **How a title or name is written.** The work register writes
     "Tempora mutantur, oder Die gestrengen Herren (Karl Blum)" — an
     alternative title plus a creator parenthetical — and a cross-reference
     to it says only "Tempora mutantur". The person register writes
     "Drewsen, Aage (1841-1876)" and a cross-reference says
     "Drewsen, Aage.". A resolver that does not know each convention
     reports hundreds of blind references that are not blind.
  3. **What a row of each kind must carry.** A cross-reference stub has no
     description and no page references *by construction* — the content
     lives at its target. Asserting "description is never empty" would fire
     on all 410 person cross-references while missing the 5 ordinary entries
     that genuinely lost theirs.

So the knowledge lives here, once, and the rules stay short.
"""

from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# A target within this ratio of an entry is treated as an OCR near miss
# rather than a blind reference. 0.90 was measured against this corpus: it
# admits every hand-checked OCR defect below and no unrelated pair.
NEAR_MISS_RATIO = 0.90
# Below this length a ratio is meaningless (see Index.resolve).
SHORT_KEY = 12
# Shortest cross-reference head allowed to claim a longer entry by prefix.
PREFIX_FLOOR = 6


# The OCR confusion classes this corpus actually exhibits, established in
# docs/person-register-segmentation.md (the systematic C->G misread behind
# Cornelis/Gornelis, Puggaard C./G., Collin/Gollin) and in
# data/raw/ocr-comparison-dagboeger-XI.md (the 0/9 and l/i classes).
# Collapsing each class to one character turns "Golloredo-Mansfeld" and
# "Colloredo-Mansfeld" into the same key -- which is a *reported* match,
# never a silent one: the reference and the entry still disagree in the
# data, and one of them needs correcting.
OCR_CONFUSIONS = str.maketrans({
    "g": "c", "l": "i", "1": "i", "0": "o", "9": "o", "u": "n", "v": "u",
    "z": "s", "b": "h", "t": "f", "m": "rn",
})


def ocr_key(k: str) -> str:
    return k.translate(OCR_CONFUSIONS)


def _edits_within(a: str, b: str, limit: int) -> bool:
    """True when `a` and `b` differ by at most `limit` single-character
    edits. Cheap bounded Levenshtein — the strings here are short."""
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return False
        prev = cur
    return prev[-1] <= limit


# ── shared normalisation ────────────────────────────────────────────────────

def fold(s: str) -> str:
    """Diacritic-, case- and punctuation-insensitive comparison key.

    æ→ae and ø→o as elsewhere in the project, NFKD strips the rest, and
    punctuation becomes whitespace rather than vanishing, so "O.T." and
    "O T" agree but "Ja!" and "Jan" do not.

    **å does not fold to "aa" here, despite the replace below.** NFKD runs
    first and decomposes å into "a" plus a combining ring, which the next
    line strips; by the time .replace("å", "aa") is reached there are no å
    characters left. So fold("Åbenrå") == "abenra", which matches the
    register's undoubled spellings and NOT "Aabenraa". æ and ø survive
    because they have no decomposition.

    That is a narrower rule than scripts/_lib/names.py, which declines to
    pick a branch and returns both keys — see its docstring for the
    measurement. Left as it stands deliberately: this function's output
    decides what the integrity checker reports, and widening it is a
    behaviour change needing its own before/after, not a tidy-up.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("ø", "o").replace("æ", "ae").replace("å", "aa")
    s = re.sub(r"[»«\"'’`.,!?;:\-–—/()\[\]*]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# A "se:" / "se ogsaa:" redirect, wherever it appears — in a label, a
# description, or a raw entry line. The register prints both spellings
# ("ogsaa" and "ogsa") and sometimes breaks the line before it.
SEE_MARKER = re.compile(r"[,;]?\s*\n?\s*\bse\s+og(?:s|)aa\s*:", re.I)
SEE_ANY = re.compile(r"[,;]?\s*\n?\s*\bse\s+og(?:s|)aa\s*:|[,;]?\s*\n?\s*\bse\s*:", re.I)

# A trailing "Sp. 60", "Sp. 60 og 201" — the register's own column pointer.
# It is a *locator*, never part of a title, and a target consisting only of
# one is a malformed reference rather than a blind one.
COLUMN_POINTER = re.compile(r"[\s,]*\bSp\.\s*\d[\d\s.,]*(?:og\s*\d+)?\s*\.?\s*$", re.I)
ONLY_COLUMN_POINTER = re.compile(r"^\s*(?:Sp\.|sp\.)\s*\d[\d\s.,]*(?:og\s*\d+)?\s*\.?\s*$")

# Alternative-title connective: "Tempora mutantur, oder Die gestrengen
# Herren", "Danina eller Jocko", "Le Retour ou La suite du …". Both sides
# are legitimate resolution targets — the register cross-references either.
ALT_TITLE = re.compile(r",?\s+(?:eller|oder|ou|or)\s+", re.I)

# A trailing parenthetical: the creator ("(Karl Blum)"), a publication year
# ("(1838)"), a museum ("(Louvre, Paris)"). Peeled off for matching; never
# part of what a cross-reference cites.
TAIL_PAREN = re.compile(r"\s*\([^()]*\)\s*[.,]?\s*$")

# Leading article, in every language the register's titles use. A
# cross-reference cites "Chant des Titans"; the entry is "Le Chant des
# Titans". Stripped from both sides so they meet.
LEADING_ARTICLE = re.compile(
    r"^(?:le|la|les|l|un|une|der|die|das|den|dem|des|ein|eine|the|a|an|"
    r"il|lo|gli|el|los|las|en|et|de|det)\s+", re.I
)

# Several targets in one field: "Bagtalelsens Skole og School for Scandal".
MULTI_TARGET = re.compile(r"\s+og\s+|\s*;\s*", re.I)


def strip_article(s: str) -> str:
    return LEADING_ARTICLE.sub("", s, count=1).strip()


def title_keys(label: str) -> set[str]:
    """Every form a work title might be cited under.

    Expands the register's own title conventions: the head before a "se:"
    tail, both sides of an alternative title, the title with each trailing
    parenthetical peeled off, and each of those without its leading article.
    """
    head = SEE_ANY.split(label or "", maxsplit=1)[0]
    head = COLUMN_POINTER.sub("", head)
    out: set[str] = set()
    stack = [head]
    for _ in range(4):
        nxt: list[str] = []
        for t in stack:
            t = t.strip()
            if not t:
                continue
            out.add(fold(t))
            out.add(fold(strip_article(t)))
            for part in ALT_TITLE.split(t):
                if part.strip():
                    nxt.append(part)
            peeled = TAIL_PAREN.sub("", t).strip()
            if peeled and peeled != t:
                nxt.append(peeled)
        if not nxt:
            break
        stack = nxt
    return {k for k in out if k}


def name_keys(label: str) -> set[str]:
    """Every form a person or place name might be cited under.

    The person register writes "Drewsen, Aage (1841-1876)" and cites it as
    "Drewsen, Aage."; a place is "Napoli" cited as "Napoli". Peeling the
    life-date parenthetical and the surname-only head covers both, and the
    surname-only key is what lets "se: Junot" reach "Junot, Andoche".
    """
    head = SEE_ANY.split(label or "", maxsplit=1)[0]
    head = COLUMN_POINTER.sub("", head).strip()
    forms = [head]
    peeled = TAIL_PAREN.sub("", head).strip()
    while peeled and peeled != forms[-1]:
        forms.append(peeled)
        peeled = TAIL_PAREN.sub("", peeled).strip()
    out = {fold(f) for f in forms}
    # An entry may print an alias in an internal parenthetical --
    # "Ûxküll (Uexküll), Berend", "Strandberg (Talis Qualis)". A
    # cross-reference cites either spelling, so index both, and index the
    # name with the parenthetical removed as well.
    for f in list(forms):
        for alias in re.findall(r"\(([^()]+)\)", f):
            if alias.strip() and not re.search(r"\d", alias):
                out.add(fold(alias))
        bare = re.sub(r"\s*\([^()]*\)", "", f).strip()
        if bare and bare != f:
            forms.append(bare)
            out.add(fold(bare))
            if "," in bare:
                out.add(fold(bare.split(",", 1)[0]))
    # Surname-only, taken before folding — folding turns the comma into a
    # space, so "Drewsen, Aage" has to be split while it still has one.
    # This is what lets "se: Junot" reach "Junot, Andoche (1771-1813)".
    for f in forms:
        if "," in f:
            before, after = (x.strip() for x in f.split(",", 1))
            out.add(fold(before))
            # The register inverts a leading article or name particle so the
            # entry files under its distinctive word: "Brenets, Les",
            # "Geer, de", "Ohsson, d'". A cross-reference cites the natural
            # order, so index that too.
            if after and len(after.split()) <= 2 and after[:1].islower() or \
               (after and LEADING_ARTICLE.match(after + " ")):
                out.add(fold(f"{after} {before}"))
    return {k for k in out if k}


def split_targets(target: str) -> list[str]:
    """Split a cross-reference field that names more than one target.

    Only ever a *fallback*: "og" is as often inside one title ("Fordum og
    nu", "Capital og Arbeide") as it is between two, so the caller resolves
    the whole field first and comes here only when that fails.
    """
    parts = [p.strip(" .,;") for p in MULTI_TARGET.split((target or "").strip())]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else []


# A target that has swallowed the start of the next entry: a life-date
# parenthetical, or a sentence break followed by a new capitalised name.
# "Behrendt, Sigismund." is a target; "A.N.de Saint-Aubain. Bernini,
# Lorenzo (1598-1680)" is two entries fused by the splitter.
# A word broken across the printed column and never rejoined: "Berner-Schil-
# den", "Dra- strup", "Frie- derici". The project already treats this as its
# own defect family (apply_hyphen_linewrap_fixes.py,
# data/review/ocr_hyphen_linewrap_candidates.tsv); naming it here means a
# reference that fails only because of one is reported as the known,
# already-tooled defect it is rather than as a blind reference.
LINEWRAP = re.compile(r"[a-zæøåäöü]-\s+[a-zæøåäöü]")

TARGET_OVERRUN = re.compile(
    r"\(\s*\d{3,4}\s*[-–]|"
    r"[a-zæøå]{2}\.\s+[A-ZÆØÅÜ][a-zæøåü]+,\s"
)


# ── the resolver ────────────────────────────────────────────────────────────

@dataclass
class Resolution:
    """What became of one cross-reference target.

    `status` is the finding class, and the four are deliberately distinct —
    they call for different work:

      resolved         the target exists; nothing to do
      ocr_variant      the target and an entry agree once the corpus's own
                       documented OCR confusion classes (C/G, l/i, 0/9) are
                       collapsed. The reference is not blind, but the two
                       spellings still disagree and one is wrong
      near_miss        nothing matches, but one entry is one or two
                       characters away. Almost always an OCR defect in the
                       *target entry's own* label ("Slouet i Poitou" for
                       "Slottet i Poitou"), so the fix is over there, not
                       in the reference
      linewrap         the target still carries an unrejoined printed-column
                       line break ("Berner-Schil- den"); healing it usually
                       resolves. A known, already-tooled defect family
      malformed        the target is not a name or title at all — an empty
                       field, or a bare column pointer the parser captured
                       where a title should be. A parser fix
      blind           nothing exists and nothing is close: the reference
                       points at an entry the register does not contain.
                       An editorial finding, and the one that matters
      self            the target resolves back to the citing row
    """
    status: str
    target: str
    target_id: str | None = None
    candidate: str | None = None
    score: float = 0.0


@dataclass
class Index:
    """One index (register), with the local conventions its rules need."""
    name: str
    keyfn: object                     # title_keys or name_keys
    # key -> [entity/entry id]; a key with several ids is an ambiguous target
    keys: dict = field(default_factory=dict)
    # id -> display label, for reporting
    labels: dict = field(default_factory=dict)

    def add(self, row_id: str, label: str) -> None:
        self.labels[row_id] = label
        for k in self.keyfn(label):
            self.keys.setdefault(k, []).append(row_id)

    _ocr_cache: dict | None = None

    def _ocr_index(self) -> dict:
        if self._ocr_cache is None:
            cache: dict[str, list[str]] = {}
            for k, ids in self.keys.items():
                cache.setdefault(ocr_key(k), []).extend(ids)
            self._ocr_cache = cache
        return self._ocr_cache

    def resolve(self, target: str, *, citing_id: str | None = None) -> Resolution:
        raw = (target or "").strip()
        if not raw:
            return Resolution("malformed", raw)
        if ONLY_COLUMN_POINTER.match(raw):
            return Resolution("malformed", raw)

        cleaned = COLUMN_POINTER.sub("", raw).strip(" .,;")
        cands = self.keyfn(cleaned)
        for k in cands:
            if k in self.keys:
                hit = self.keys[k]
                if citing_id and hit == [citing_id]:
                    return Resolution("self", raw, citing_id)
                other = [h for h in hit if h != citing_id]
                if other:
                    return Resolution("resolved", raw, other[0])
                return Resolution("self", raw, citing_id)

        # Prefix match: the register cross-references the head of a longer
        # entry -- "Didaskalia" -> "Didaskalia oder Blätter für Geist …",
        # "Skopas" -> "Skopas fra Paros (4.Aarh.f.Chr.)". Guarded by a
        # length floor so a short word cannot claim an entry; 6 is the
        # shortest real head in this corpus ("Ronco", "Borgo", "Skopas"),
        # and the guard below additionally requires a word boundary.
        for k in sorted(cands, key=len, reverse=True):
            if len(k) < PREFIX_FLOOR:
                continue
            for cand_key, ids in self.keys.items():
                if cand_key.startswith(k + " "):
                    other = [h for h in ids if h != citing_id]
                    if other:
                        return Resolution("resolved", raw, other[0])

        # Nothing matched exactly. Try the known OCR confusion classes
        # before falling back to a blind similarity search: a hit here has a
        # documented cause, which a ratio never does.
        ocr_index = self._ocr_index()
        for k in cands:
            ids = ocr_index.get(ocr_key(k), [])
            other = [h for h in ids if h != citing_id]
            if other:
                return Resolution("ocr_variant", raw, other[0],
                                  self.labels.get(other[0]), 1.0)

        # Still nothing. Is anything nearly right? A near miss is an OCR
        # defect to fix, not a blind reference to escalate, so it is worth
        # the one-off cost of a fuzzy pass over the key space.
        best, score = None, 0.0
        probe = max(cands, key=len) if cands else fold(cleaned)
        for cand_key in self.keys:
            if abs(len(cand_key) - len(probe)) > 6:
                continue
            r = difflib.SequenceMatcher(None, probe, cand_key).ratio()
            if r > score:
                best, score = cand_key, r
        # A short name cannot reach a ratio threshold tuned for titles: one
        # substituted character in "Melk" scores 0.75, the same as two words
        # of difference in a long title. Judge short keys by edit distance
        # instead, which is what an OCR defect actually is.
        if best and (score >= NEAR_MISS_RATIO or
                     (len(probe) <= SHORT_KEY
                      and _edits_within(probe, best, 1))):
            ids = [h for h in self.keys[best] if h != citing_id]
            if ids:
                return Resolution("near_miss", raw, ids[0],
                                  self.labels.get(ids[0]), round(score, 3))
        return Resolution("blind", raw, None,
                          self.labels.get(self.keys.get(best, [None])[0]) if best else None,
                          round(score, 3))


def _read_csv(path: Path, delimiter: str = ","):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def load_entities():
    return _read_csv(ROOT / "data" / "normalized" / "entities.csv")


def load_parsed(name: str):
    return _read_csv(ROOT / "data" / "parsed" / name, delimiter="\t")


def build_entity_index(rows, entity_type: str) -> Index:
    """An index over one register in entities.csv.

    Cross-reference stubs are excluded as *targets*: a redirect must land on
    a real entry, and letting one stub resolve to another would hide exactly
    the dangling chains these rules exist to find.
    """
    keyfn = title_keys if entity_type == "work" else name_keys
    idx = Index(entity_type, keyfn)
    for r in rows:
        if r["entity_type"] != entity_type:
            continue
        # Only a bare "se:" makes a redirect stub. "se ogsaa:" is a soft
        # link printed ON a substantive entry ("Brylluppet paa Ulfsbjerg
        # (Frans Hedberg)- Se ogsaa: Brölloppet på Ulfåsa"), and excluding
        # those would make every see-also pair report as blind — each half
        # would have removed the other from the index.
        if redirect_of(r):
            continue
        idx.add(r["entity_id"], r["label"])
    return idx


def primary_key(idx: "Index", label: str) -> str | None:
    """The most specific key for a label — the full folded head.

    Chain detection needs this rather than the whole key set: the surname
    fallback that lets "se: Junot" find "Junot, Andoche" also makes every
    "Andersen, X" stub look like every other one.
    """
    head = SEE_ANY.split(label or "", maxsplit=1)[0]
    return fold(COLUMN_POINTER.sub("", head)) or None


def redirect_of(row) -> str:
    """The redirect a row carries, whether or not the ingester extracted it.

    `see` is populated for works only; for persons and places the register's
    "se:" redirect survives only inside the label text. Reading both means a
    rule covers all three registers instead of a quarter of them.
    """
    if row.get("see", "").strip():
        return row["see"].strip()
    m = SEE_ANY.search(row["label"])
    if m and not SEE_MARKER.match(row["label"][m.start():]):
        return row["label"][m.end():].strip()
    return ""


def is_self_reference(citing_label: str, target: str) -> bool:
    """True when a row's cross-reference points back at the row itself.

    Checked against the label rather than through the index, because stubs
    are deliberately absent from the index as targets — so a self-redirect
    would otherwise fall through as "blind" and the rule that exists to
    catch it could never fire.
    """
    head = fold(COLUMN_POINTER.sub("", SEE_ANY.split(citing_label or "", maxsplit=1)[0]))
    tgt = fold(COLUMN_POINTER.sub("", (target or "").strip(" .,;")))
    return bool(head) and head == tgt


def resolve_field(idx: Index, field_value: str, *,
                  citing_id: str | None = None,
                  citing_label: str | None = None):
    """Resolve one cross-reference *field*, which may name several targets.

    Order matters: the whole field is tried first, because "og" sits inside
    a title as often as it sits between two. Only when the whole field fails
    do we split, and only when every part then resolves do we accept the
    split reading — a half-resolving split is weaker evidence than the
    unsplit failure it replaced.
    """
    if citing_label is not None and is_self_reference(citing_label, field_value):
        return [Resolution("self", (field_value or "").strip(), citing_id)]
    whole = idx.resolve(field_value, citing_id=citing_id)
    if whole.status in ("resolved", "self"):
        return [whole]
    if whole.status == "blind":
        if TARGET_OVERRUN.search(field_value or ""):
            return [Resolution("overrun", (field_value or "").strip())]
        if LINEWRAP.search(field_value or ""):
            # Retry with the break healed: if that resolves, the reference
            # was never blind, only unrejoined.
            healed = LINEWRAP.sub(lambda m: m.group(0)[0] + m.group(0)[-1],
                                  field_value)
            again = idx.resolve(healed, citing_id=citing_id)
            return [Resolution("linewrap", (field_value or "").strip(),
                               again.target_id, again.candidate or whole.candidate,
                               again.score)]

    parts = split_targets(field_value)
    if parts:
        each = [idx.resolve(p, citing_id=citing_id) for p in parts]
        if all(r.status in ("resolved", "self") for r in each):
            return each
    return [whole]
