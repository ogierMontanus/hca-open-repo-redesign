#!/usr/bin/env python3
"""
update_index.py — run the maintenance pass over one index.

    python scripts/index_maintenance/update_index.py person --from <new.tsv>
    python scripts/index_maintenance/update_index.py person --from <new.tsv> --apply
    python scripts/index_maintenance/update_index.py --list

The seven steps, in order, all in one command:

  1  read the updated source and the index as it stands
  2  match them, and classify what moved — new, changed, merged, split, gone
  3  carry every id that can be carried
  4  mint only for genuinely new rows and for the extra rows a split produced
  5  rewrite references that pointed at an id a merge retired
  6  validate, and report anything it refused to decide
  7  write the index, the ledger and the review file

**Dry run by default.** Nothing is written without `--apply`, and a run that
finds unresolved conflicts refuses to write at all unless `--force` is passed,
because a half-assigned index is worse than an unchanged one.

Not tied to the person register: `--list` shows every index the framework
knows, and adding one is a descriptor in `spec.py`. See
docs/index-maintenance.md.
"""

import argparse
import csv
import datetime as _dt
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from index_maintenance import core                      # noqa: E402
from index_maintenance.spec import REGISTRY, ROOT       # noqa: E402

REVIEW_FIELDS = ["kind", "id", "label", "detail"]


def _load_incoming(spec, path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter=spec.delimiter)
        return list(r), list(r.fieldnames or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("index", nargs="?", help="which index (see --list)")
    ap.add_argument("--from", dest="source", type=Path,
                    help="the updated source file; defaults to the index itself, "
                         "which makes the run a no-op integrity check")
    ap.add_argument("--apply", action="store_true", help="write the results")
    ap.add_argument("--force", action="store_true",
                    help="write even though conflicts were reported")
    ap.add_argument("--list", action="store_true", help="list known indexes")
    args = ap.parse_args()

    if args.list or not args.index:
        print("Indexes this framework knows:\n")
        for name, s in REGISTRY.items():
            wired = "wired" if s.signature_of({}) is not None else ""
            print(f"  {name:<10} {s.id_prefix}…  {s.path.relative_to(ROOT)}")
            if s.notes:
                print(f"             {s.notes}")
        return 0

    if args.index not in REGISTRY:
        sys.exit(f"unknown index {args.index!r}; known: {', '.join(REGISTRY)}")
    spec = REGISTRY[args.index]
    today = _dt.date.today().isoformat()

    # 1 ── read both sides
    previous, fields = spec.read()
    src = args.source or spec.path
    incoming, in_fields = _load_incoming(spec, src)
    if spec.id_column not in in_fields:
        in_fields = [spec.id_column] + in_fields
        for r in incoming:
            r.setdefault(spec.id_column, "")
    prev_entries = [r for r in previous if spec.is_entry(r)]
    new_entries = [r for r in incoming if spec.is_entry(r)]
    print(f"  index    {spec.path.relative_to(ROOT)}   {len(previous):,} rows "
          f"({len(prev_entries):,} entries)")
    print(f"  source   {src if not src.is_relative_to(ROOT) else src.relative_to(ROOT)}"
          f"   {len(incoming):,} rows ({len(new_entries):,} entries)")

    ledger = core.read_ledger(spec)
    minter = core.Minter(spec, ledger, previous)

    # 2 ── match and classify
    pairs, prev_un, new_un, ambiguous = core.match(spec, prev_entries, new_entries)

    # 3 + 4 ── carry, then mint only where nothing can be carried
    outcome = core.classify(spec, prev_entries, new_entries, pairs,
                            prev_un, new_un, minter, ledger, today, ambiguous)

    print("\n  " + "  ".join(f"{k}={v:,}" for k, v in outcome.counts().items()))
    for parent, family in outcome.splits[:5]:
        print(f"     split  {parent} -> {' '.join(family)}")
    for survivor, retired in outcome.merges[:5]:
        print(f"     merge  {' '.join(retired)} -> {survivor}")
    for nid, label, why in outcome.minted[:5]:
        print(f"     mint   {nid}  {label[:40]!r}  ({why})")

    # 5 ── follow the ids that moved
    touched = core.rewrite_references(spec, outcome, apply=args.apply)
    for path, n in touched:
        print(f"     refs   {n:,} row(s) repointed in {path.relative_to(ROOT)}")

    # 6 ── validate
    findings = core.validate(spec, new_entries, ledger)
    if findings:
        print(f"\n  integrity findings: {len(findings):,}")
        for kind, what, ctx in findings[:8]:
            print(f"     {kind:<20} {str(what)[:44]}  {ctx[:2]}")
    else:
        print("\n  integrity: clean")

    blocking = outcome.conflicts + [f for f in findings
                                    if f[0] in ("duplicate-id", "malformed-id", "missing-id")]
    if blocking:
        print(f"  UNRESOLVED: {len(blocking):,} — listed in "
              f"{spec.report_path.relative_to(ROOT)}")

    # 7 ── write
    spec.report_path.parent.mkdir(parents=True, exist_ok=True)
    with spec.report_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        for kind, what, ctx in outcome.conflicts:
            w.writerow({"kind": kind, "id": "", "label": what,
                        "detail": " | ".join(map(str, ctx))})
        for kind, what, ctx in findings:
            w.writerow({"kind": kind, "id": what, "label": "",
                        "detail": " | ".join(map(str, ctx))})
        for parent, family in outcome.splits:
            w.writerow({"kind": "split", "id": parent, "label": "",
                        "detail": " ".join(family)})
        for survivor, retired in outcome.merges:
            w.writerow({"kind": "merge", "id": survivor, "label": "",
                        "detail": " ".join(retired)})
    print(f"  wrote {spec.report_path.relative_to(ROOT)}")

    if not args.apply:
        print("\n  dry run — index and ledger unchanged. Re-run with --apply.")
        return 1 if blocking else 0
    if blocking and not args.force:
        print("\n  REFUSED to write: unresolved conflicts. Resolve them, or "
              "pass --force\n  to write everything that was decided and leave "
              "the rest without an id.")
        return 1

    shutil.copy2(spec.path, spec.path.with_suffix(spec.path.suffix + ".bak"))
    with spec.path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=in_fields, delimiter=spec.delimiter)
        w.writeheader()
        w.writerows(incoming)
    spec.path.with_suffix(spec.path.suffix + ".bak").unlink()
    core.write_ledger(spec, ledger)
    print(f"\n  wrote {spec.path.relative_to(ROOT)}  ({len(incoming):,} rows)")
    print(f"  wrote {spec.ledger_path.relative_to(ROOT)}  ({len(ledger):,} ids)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
