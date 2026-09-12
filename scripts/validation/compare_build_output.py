#!/usr/bin/env python3
"""
Hash every artifact a publication-repo build produces, and compare two runs.

The equivalence check behind the migration: a build of hca-open-repo driven by
this repository's published package must produce the same bytes as a build
driven by the data already committed there.

    python scripts/validation/compare_build_output.py snapshot <checkout> <out.json>
    python scripts/validation/compare_build_output.py compare  <a.json> <b.json>

What is hashed:

    mockup/diary-pages/*.html    the generated diary pages (4,544)
    mockup/data/*.js             the generated JS data cards (9)
    web/data/*.json              the denormalised view shapes (7)

Two rules matter when producing a snapshot, both learned the hard way:

**Set PYTHONHASHSEED=0.** Several builders iterate over sets and dicts whose
order feeds the output. Without a fixed seed two runs of the same code differ.

**Do not run stages 1a-1e.** They regenerate data/normalized/ from the raw
sources, and work_languages.csv is not reproducible across lingua versions —
not merely in its confidence figures but in which rows it contains at all (16
ids move each way between the versions measured). Running them silently
rewrites the prepared data the baseline is supposed to hold fixed. Build only
the stages that consume prepared data:

    for s in 2 3a 3b 4a 4b 4c 4d 4e 4f; do
        PYTHONHASHSEED=0 PYTHONIOENCODING=utf-8 \
            python scripts/build_all.py --only $s
    done

**PYTHONIOENCODING=utf-8 is not optional on Windows.** build_cooccurrence.py
and build_nation_index.py both print a U+2192 arrow in their progress output,
which raises UnicodeEncodeError under the cp1252 console default. Stage 4e
then fails loudly; stage 4f is marked optional in build_all.py, so it fails
*silently* and nation-index.js is simply absent from the build. That is a real
defect in the publication repo, not in this check — reported, not worked
around, beyond forcing the encoding here.
"""

import hashlib
import json
import sys
from pathlib import Path

TARGETS = [
    "mockup/diary-pages/*.html",
    "mockup/data/*.js",
    "web/data/*.json",
]

# Differences that are expected and carry no information about the data.
# web/data/manifest.json embeds the wall-clock time of the build.
VOLATILE = {"web/data/manifest.json": "built_at timestamp"}


def snapshot(root: Path) -> dict:
    out = {}
    for pat in TARGETS:
        base, glob = pat.split("/", 1)
        for p in sorted((root / base).glob(glob)):
            out[p.relative_to(root).as_posix()] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
    return out


def report_snapshot(root: Path, dest: Path) -> int:
    h = snapshot(root)
    if not h:
        print(f"no artifacts found under {root} — was the build run?")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(h, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(h):,} artifacts hashed -> {dest}")
    for pat in TARGETS:
        prefix = pat.split("*")[0]
        print(f"   {pat:28s} {sum(1 for k in h if k.startswith(prefix)):,}")
    return 0


def compare(a_path: Path, b_path: Path) -> int:
    a = json.loads(a_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))

    missing = sorted(set(a) - set(b))
    extra = sorted(set(b) - set(a))
    differing = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    unexplained = [k for k in differing if k not in VOLATILE]

    print(f"  {a_path.name:24s} {len(a):,} artifacts")
    print(f"  {b_path.name:24s} {len(b):,} artifacts")
    print(f"  missing from the second  {len(missing):,}")
    print(f"  extra in the second      {len(extra):,}")
    print(f"  differing                {len(differing):,}")

    for k in missing[:20]:
        print(f"     missing: {k}")
    for k in extra[:20]:
        print(f"     extra:   {k}")
    for k in differing:
        why = VOLATILE.get(k)
        print(f"     differs: {k}" + (f"   [expected — {why}]" if why else ""))

    if missing or extra or unexplained:
        print("\n  FAIL — unexplained differences. Classify each before proceeding:")
        print("  identical / intentional improvement / formatting-only / unexplained.")
        return 1
    if differing:
        print(f"\n  PASS — {len(a) - len(differing):,} of {len(a):,} byte-identical; "
              f"{len(differing)} differ only in documented volatile fields.")
    else:
        print(f"\n  PASS — all {len(a):,} artifacts byte-identical.")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    if mode == "snapshot" and len(sys.argv) == 4:
        return report_snapshot(Path(sys.argv[2]).resolve(), Path(sys.argv[3]))
    if mode == "compare" and len(sys.argv) == 4:
        return compare(Path(sys.argv[2]), Path(sys.argv[3]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
