"""
core.py — match an updated index against the previous one, and decide ids.

Index-agnostic. Everything it knows about a register arrives through an
`IndexSpec`.

The one rule the whole thing rests on
-------------------------------------
**An identifier is carried, never derived.** A content-derived id changes when
a typo is fixed and takes every citation with it. This is not theory here:
V0.94's place ids are content-derived and resolve 0 of 2,433 against the live
register, while its work ids are carried and resolve 3,590 of 3,590.

So the engine only ever does three things with an id: keep it on the row it
already belongs to, mint a fresh one, or retire it into the ledger with a
pointer to what replaced it. It never recomputes one.

Matching
--------
Four passes, each looking only at what the earlier ones left:

  0. **carried id** — the incoming row already names the entry it is. This is
     what makes a re-run idempotent, and it is the normal case when the
     updated source was derived from the index rather than reparsed.
  1. **label** — fold both sides and match exactly, where the fold is unique
     on both sides.
  2. **signature** — the citation set, for rows a rename moved out of reach of
     pass 1. A re-spelled entry keeps citing the same pages.
  3. **singular side** — one previous to several incoming, or the reverse.
     These become splits and merges below.

A key that is ambiguous on *both* sides identifies nothing, so those rows are
reported rather than paired. An earlier version paired them all-to-all, which
turned two same-named people into a merge and then assigned one id to both.

Nothing is matched on a similarity score. The tiers that resolved 97.8 % of
the person crosswalk were all exact on one axis or the other, and a fuzzy
tier would have bought the remaining percent at the cost of being unable to
say why any given row matched.

Split and merge
---------------
These fall out of the match being many-to-one in either direction:

  one previous row  ->  several new rows    a SPLIT
  several previous  ->  one new row         a MERGE

For a split, the child that inherits the parent's id is the one whose
signature overlaps the parent's most — the continuation, where most existing
citations still land. Its siblings are minted fresh. When two children tie,
nothing is assigned and the case is reported: guessing which half of a split
person keeps the citations is exactly the decision a human should make.

For a merge, the survivor keeps the id of the previous row it overlaps most,
and the others are retired in the ledger with `superseded_by` pointing at it,
so an old citation still resolves.

The ledger
----------
`data/curated/<index>_id_ledger.csv` is what makes an id permanent rather than
merely current. Every id ever minted stays in it with a status:

  active      in use on a row today
  merged      retired; `superseded_by` names the survivor
  split       the row it named was split; `superseded_by` names the
              continuation and `note` lists the siblings
  withdrawn   the row is gone and nothing replaced it

A citation to a retired id is still answerable, which is the entire point.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .spec import IndexSpec, fold

LEDGER_FIELDS = ["id", "status", "superseded_by", "first_seen", "note"]


@dataclass
class Outcome:
    """What one run decided."""
    carried: list = field(default_factory=list)      # (id, label)
    minted: list = field(default_factory=list)       # (id, label, why)
    splits: list = field(default_factory=list)       # (parent_id, [child ids])
    merges: list = field(default_factory=list)       # (survivor, [retired])
    withdrawn: list = field(default_factory=list)    # (id, label)
    changed: list = field(default_factory=list)      # (id, label) same id, new content
    conflicts: list = field(default_factory=list)    # (kind, detail, ids)

    def counts(self) -> dict:
        return {
            "carried": len(self.carried), "changed": len(self.changed),
            "minted": len(self.minted), "splits": len(self.splits),
            "merges": len(self.merges), "withdrawn": len(self.withdrawn),
            "conflicts": len(self.conflicts),
        }


# ── ledger ──────────────────────────────────────────────────────────────────

def read_ledger(spec: IndexSpec) -> dict:
    if not spec.ledger_path.exists():
        return {}
    with spec.ledger_path.open(encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def write_ledger(spec: IndexSpec, ledger: dict) -> None:
    spec.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with spec.ledger_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for k in sorted(ledger):
            w.writerow({c: ledger[k].get(c, "") for c in LEDGER_FIELDS})


class Minter:
    """Hands out the next free id and never reuses a retired one."""

    def __init__(self, spec: IndexSpec, ledger: dict, rows: list):
        self.spec = spec
        used = set(ledger) | {r.get(spec.id_column, "") for r in rows}
        nums = [int(u[len(spec.id_prefix):]) for u in used
                if u.startswith(spec.id_prefix) and u[len(spec.id_prefix):].isdigit()]
        self._next = max(nums, default=0) + 1

    def mint(self) -> str:
        new = f"{self.spec.id_prefix}{self._next:0{self.spec.id_width}d}"
        self._next += 1
        return new


# ── matching ────────────────────────────────────────────────────────────────

def _index_by(rows, keyfn):
    out = defaultdict(list)
    for i, r in enumerate(rows):
        k = keyfn(r)
        if k:
            out[k].append(i)
    return out


def match(spec: IndexSpec, previous: list, incoming: list) -> tuple:
    """Return (pairs, prev_unmatched, new_unmatched, ambiguous).

    `pairs` may be many-to-one or one-to-many — classify() turns those into
    merges and splits. It is never many-to-many: a key that is ambiguous on
    *both* sides identifies nothing, so those rows are returned as `ambiguous`
    and left for a human rather than paired arbitrarily.

    Four passes, each only looking at what the previous ones left:

      0  carried id     the incoming row already says which entry it is.
                        This is what makes a re-run idempotent, and it is the
                        normal case when the updated source was derived from
                        the index rather than reparsed from scratch.
      1  unique label   one previous row and one incoming row fold alike.
      2  unique signature   for rows a rename moved out of reach of pass 1.
      3  singular side  one previous to several incoming (a split), or
                        several previous to one incoming (a merge).
    """
    ID = spec.id_column
    pairs = []
    prev_left = set(range(len(previous)))
    new_left = set(range(len(incoming)))
    ambiguous = []

    # pass 0 — the incoming row carries an id we already know
    prev_by_id = {}
    for i, r in enumerate(previous):
        k = (r.get(ID) or "").strip()
        if k:
            prev_by_id.setdefault(k, []).append(i)
    for j, r in enumerate(incoming):
        k = (r.get(ID) or "").strip()
        hits = prev_by_id.get(k, [])
        if k and len(hits) == 1 and hits[0] in prev_left:
            pairs.append((hits[0], j))
            prev_left.discard(hits[0])
            new_left.discard(j)

    def _buckets(keyfn):
        p, n = defaultdict(list), defaultdict(list)
        for i in prev_left:
            k = keyfn(previous[i])
            if k:
                p[k].append(i)
        for j in new_left:
            k = keyfn(incoming[j])
            if k:
                n[k].append(j)
        return p, n

    # passes 1 and 2 — unique on both sides
    for keyfn in (lambda r: fold(spec.label_of(r)), spec.signature_of):
        p, n = _buckets(keyfn)
        for k, pidx in p.items():
            nidx = n.get(k, [])
            if len(pidx) == 1 and len(nidx) == 1:
                pairs.append((pidx[0], nidx[0]))
                prev_left.discard(pidx[0])
                new_left.discard(nidx[0])

    # pass 3 — one side singular: a split or a merge, for classify() to settle
    for keyfn in (lambda r: fold(spec.label_of(r)), spec.signature_of):
        p, n = _buckets(keyfn)
        for k, pidx in p.items():
            nidx = n.get(k, [])
            if not pidx or not nidx:
                continue
            if len(pidx) > 1 and len(nidx) > 1:
                # Same label on both sides, several each. The label has run
                # out of discriminating power, but the signature may not
                # have: pair off whatever matches exactly on citations, and
                # only report what is left.
                taken_p, taken_n = set(), set()
                nsig = {j: spec.signature_of(incoming[j]) for j in nidx}
                for i in pidx:
                    psig = spec.signature_of(previous[i])
                    if not psig:
                        continue
                    hit = [j for j in nidx if j not in taken_n and nsig[j] == psig]
                    if len(hit) == 1:
                        pairs.append((i, hit[0]))
                        taken_p.add(i); taken_n.add(hit[0])
                left_p = [i for i in pidx if i not in taken_p]
                left_n = [j for j in nidx if j not in taken_n]
                if left_p and left_n:
                    ambiguous.append((str(k)[:60],
                                      [previous[i].get(ID, "") for i in left_p]))
                prev_left -= set(pidx)
                new_left -= set(nidx)
                continue
            for i in pidx:
                for j in nidx:
                    pairs.append((i, j))
            prev_left -= set(pidx)
            new_left -= set(nidx)

    return pairs, sorted(prev_left), sorted(new_left), ambiguous


def _overlap(a: frozenset, b: frozenset) -> int:
    return len(a & b)


def classify(spec: IndexSpec, previous: list, incoming: list,
             pairs: list, prev_unmatched: list, new_unmatched: list,
             minter: Minter, ledger: dict, today: str,
             ambiguous: list = ()) -> Outcome:
    """Decide an id for every incoming row. Mutates `incoming` in place."""
    out = Outcome()
    for key, ids in ambiguous:
        out.conflicts.append(("ambiguous-both-sides", key, ids))
    by_prev = defaultdict(list)
    by_new = defaultdict(list)
    for i, j in pairs:
        by_prev[i].append(j)
        by_new[j].append(i)

    ID = spec.id_column
    assigned = set()

    # ── merges: several previous rows collapse onto one incoming row
    for j, prevs in by_new.items():
        if len(prevs) < 2:
            continue
        sig = spec.signature_of(incoming[j])
        scored = sorted(prevs, key=lambda i: -_overlap(spec.signature_of(previous[i]), sig))
        best, rest = scored[0], scored[1:]
        top = _overlap(spec.signature_of(previous[best]), sig)
        tie = [i for i in rest if _overlap(spec.signature_of(previous[i]), sig) == top]
        if tie and top > 0:
            out.conflicts.append(("merge-tie", spec.label_of(incoming[j]),
                                  [previous[i][ID] for i in scored]))
            continue
        survivor = previous[best][ID]
        incoming[j][ID] = survivor
        assigned.add(j)
        retired = []
        for i in rest:
            rid = previous[i][ID]
            retired.append(rid)
            ledger[rid] = {"id": rid, "status": "merged", "superseded_by": survivor,
                           "first_seen": ledger.get(rid, {}).get("first_seen", today),
                           "note": f"merged into {survivor}"}
        out.merges.append((survivor, retired))

    # ── splits: one previous row becomes several incoming rows
    for i, news in by_prev.items():
        news = [j for j in news if j not in assigned]
        if len(news) < 2:
            continue
        psig = spec.signature_of(previous[i])
        scored = sorted(news, key=lambda j: -_overlap(spec.signature_of(incoming[j]), psig))
        top = _overlap(spec.signature_of(incoming[scored[0]]), psig)
        tie = [j for j in scored[1:] if _overlap(spec.signature_of(incoming[j]), psig) == top]
        if tie:
            out.conflicts.append(("split-tie", spec.label_of(previous[i]),
                                  [spec.label_of(incoming[j]) for j in scored]))
            continue
        parent = previous[i][ID]
        incoming[scored[0]][ID] = parent          # the continuation keeps it
        assigned.add(scored[0])
        children = []
        for j in scored[1:]:
            nid = minter.mint()
            incoming[j][ID] = nid
            assigned.add(j)
            children.append(nid)
            ledger[nid] = {"id": nid, "status": "active", "superseded_by": "",
                           "first_seen": today, "note": f"split from {parent}"}
            out.minted.append((nid, spec.label_of(incoming[j]), f"split from {parent}"))
        out.splits.append((parent, [parent] + children))
        ledger[parent] = {"id": parent, "status": "active", "superseded_by": "",
                          "first_seen": ledger.get(parent, {}).get("first_seen", today),
                          "note": f"split; siblings {' '.join(children)}"}

    # ── straightforward carries
    for i, j in pairs:
        if j in assigned:
            continue
        pid = previous[i][ID]
        if not pid:
            continue
        incoming[j][ID] = pid
        assigned.add(j)
        if _row_content(spec, previous[i]) != _row_content(spec, incoming[j]):
            out.changed.append((pid, spec.label_of(incoming[j])))
        else:
            out.carried.append((pid, spec.label_of(incoming[j])))

    # ── split children that a rename hid from the label match
    #
    # A real split usually renames at least one half — that is the point of
    # splitting. So the label cannot see it, and without this the new half is
    # minted as an unrelated "new entry" and the ledger loses the connection
    # back to its parent. The signature can see it: a split child cites a
    # subset of what the undivided entry cited.
    prev_sig = [(i, spec.signature_of(previous[i])) for i in range(len(previous))]
    for j in list(new_unmatched):
        if j in assigned:
            continue
        sig = spec.signature_of(incoming[j])
        if not sig:
            continue
        cands = [i for i, ps in prev_sig
                 if ps and sig < ps and previous[i].get(ID)]
        if not cands:
            continue
        # Several entries can happen to cite a superset of these pages — in
        # the person register a busy contemporary often does. A split child
        # shares its parent's heading, so the label breaks the tie: score on
        # how much of the label they share first, then on how tightly the
        # parent's citations enclose the child's.
        ctok = set(fold(spec.label_of(incoming[j])).split())

        def _score(i):
            ptok = set(fold(spec.label_of(previous[i])).split())
            return (len(ctok & ptok), -len(spec.signature_of(previous[i])))

        ranked = sorted(cands, key=_score, reverse=True)
        if len(ranked) > 1 and _score(ranked[0]) == _score(ranked[1]):
            out.conflicts.append(("split-parent-ambiguous", spec.label_of(incoming[j]),
                                  [previous[i][ID] for i in ranked[:4]]))
            continue
        if _score(ranked[0])[0] == 0:
            continue          # shares no label at all — treat as a new entry
        parent = previous[ranked[0]][ID]
        nid = minter.mint()
        incoming[j][ID] = nid
        assigned.add(j)
        ledger[nid] = {"id": nid, "status": "active", "superseded_by": "",
                       "first_seen": today, "note": f"split from {parent}"}
        out.minted.append((nid, spec.label_of(incoming[j]), f"split from {parent}"))
        existing = next((f for pnt, f in out.splits if pnt == parent), None)
        if existing is None:
            out.splits.append((parent, [parent, nid]))
        else:
            existing.append(nid)
        ledger[parent] = {"id": parent, "status": "active", "superseded_by": "",
                          "first_seen": ledger.get(parent, {}).get("first_seen", today),
                          "note": f"split; sibling {nid}"}

    # ── genuinely new rows
    for j in new_unmatched:
        if j in assigned:
            continue
        nid = minter.mint()
        incoming[j][ID] = nid
        ledger[nid] = {"id": nid, "status": "active", "superseded_by": "",
                       "first_seen": today, "note": "new entry"}
        out.minted.append((nid, spec.label_of(incoming[j]), "new entry"))

    # ── rows that vanished
    for i in prev_unmatched:
        pid = previous[i][ID]
        if not pid:
            continue
        ledger[pid] = {"id": pid, "status": "withdrawn", "superseded_by": "",
                       "first_seen": ledger.get(pid, {}).get("first_seen", today),
                       "note": "absent from the updated source"}
        out.withdrawn.append((pid, spec.label_of(previous[i])))

    # anything still without an id is a conflict the run refused to guess at
    for j, r in enumerate(incoming):
        if not r.get(ID):
            out.conflicts.append(("unassigned", spec.label_of(r), []))

    return out


def _row_content(spec: IndexSpec, row: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in row.items() if k != spec.id_column))


# ── reference rewriting ─────────────────────────────────────────────────────

def rewrite_references(spec: IndexSpec, outcome: Outcome, apply: bool) -> list:
    """Point references at survivors after a merge. Returns (path, n) pairs."""
    remap = {}
    for survivor, retired in outcome.merges:
        for r in retired:
            remap[r] = survivor
    if not remap:
        return []
    touched = []
    for path, delim, column in spec.reference_files:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f, delimiter=delim)
            rows, fields = list(rdr), list(rdr.fieldnames or [])
        n = 0
        for r in rows:
            if r.get(column) in remap:
                r[column] = remap[r[column]]
                n += 1
        if n and apply:
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, delimiter=delim)
                w.writeheader()
                w.writerows(rows)
        touched.append((path, n))
    return touched


# ── validation ──────────────────────────────────────────────────────────────

def validate(spec: IndexSpec, rows: list, ledger: dict) -> list:
    """Integrity findings. Empty means the index is internally consistent."""
    ID = spec.id_column
    findings = []
    seen = defaultdict(list)
    for r in rows:
        seen[r.get(ID, "")].append(spec.label_of(r))
    for k, labels in seen.items():
        if not k:
            findings.append(("missing-id", f"{len(labels)} row(s) carry no id", labels[:3]))
        elif len(labels) > 1:
            findings.append(("duplicate-id", k, labels[:3]))
    for r in rows:
        k = r.get(ID, "")
        if k and not (k.startswith(spec.id_prefix) and k[len(spec.id_prefix):].isdigit()):
            findings.append(("malformed-id", k, [spec.label_of(r)]))
    live = {r.get(ID) for r in rows}
    for k, e in ledger.items():
        if e.get("status") == "active" and k not in live:
            findings.append(("ledger-drift", k, [e.get("note", "")]))
        if e.get("status") in ("merged", "split") and e.get("superseded_by") \
                and e["superseded_by"] not in live and e["superseded_by"] not in ledger:
            findings.append(("dangling-supersede", k, [e["superseded_by"]]))
    return findings
