#!/usr/bin/env python3
"""
build_preview.py — assemble this repository's own GitHub Pages site.

The preview exists so the data work here can be looked at on a link, without
anyone having to clone two repositories and run a build. It has two halves:

  the landing page   what this pipeline produced and what it found — counts
                     read live from data/review/, not typed in
  the built site     hca-open-repo, built from this repository's published
                     package by the workflow before this script runs

**No user interface is copied into this repository.** The site under
`site/mockup/` is produced by checking hca-open-repo out in CI and running its
build against `publish.py`'s output. That keeps the boundary the whole
migration was built on — nothing here renders, nothing there re-derives — and
it means the preview cannot drift from the real thing, because it *is* the
real thing built from this data.

Usage (the workflow does this; it also works locally):
    python scripts/preview/build_preview.py --site site
"""

import argparse
import csv
import html
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "data" / "review"

# (file, label, what the reader should understand it to be)
FINDINGS = [
    ("label_corruption.csv", "labels damaged by a find-and-replace",
     "“wor” replaced by “Pag” — Kenilworth as “KenilPagth”. Upstream in the "
     "V0.82 workbook, visible on the live site."),
    ("person_reference_merge_review.csv", "entries whose citation list is the next entry's",
     "Withheld from the reference merge: merging them would attribute "
     "hundreds of pages to the wrong person."),
    ("person_duplicate_candidates.csv", "duplicate candidates",
     "Same surname, same cited pages, compatible given names."),
    ("person_crosswalk_review.csv", "entries with no counterpart in the live register",
     "Escalated rather than matched by guesswork."),
    ("page_reference_problems.csv", "citations to pages that do not exist",
     "Checkable for the first time now that a ten-volume page list exists."),
]


def rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def data_rows(rel: str) -> int:
    return rows(ROOT / rel)


def git(*args, cwd=ROOT) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def page(ctx: dict) -> str:
    f = "".join(
        f"""      <tr><td class="n">{n:,}</td><td><a href="review/{fn}">{html.escape(label)}</a>
          <span>{html.escape(note)}</span></td></tr>\n"""
        for fn, label, note, n in ctx["findings"])
    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HCA data pipeline — preview</title>
<style>
:root {{ --ink:#1a211e; --mut:#66716b; --rule:#c8cdc2; --bg:#e6e8e2;
         --card:#f4f5f1; --accent:#8c4232; }}
@media (prefers-color-scheme:dark) {{ :root:not([data-theme=light]) {{
  --ink:#e7e9e4; --mut:#8d9891; --rule:#333b3c; --bg:#141819; --card:#1c2123;
  --accent:#d4846d; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 Georgia,serif;
        padding:0 20px 80px }}
main {{ max-width:64rem; margin:0 auto }}
header {{ padding:56px 0 0 }}
h1 {{ font-size:clamp(1.9rem,4vw,2.7rem); line-height:1.1; margin:0; letter-spacing:-.02em }}
.lede {{ max-width:44rem; color:var(--mut); font-size:1.05rem }}
.warn {{ border-left:3px solid var(--accent); background:var(--card); padding:14px 18px;
         margin:26px 0; font-size:.95rem }}
h2 {{ font-size:1.25rem; margin:44px 0 12px; border-top:1px solid var(--ink);
      padding-top:12px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1px;
         background:var(--rule); border:1px solid var(--rule) }}
.grid > div {{ background:var(--card); padding:16px 18px }}
.grid dt {{ font:600 1.45rem/1.1 ui-monospace,monospace; font-variant-numeric:tabular-nums }}
.grid dd {{ margin:6px 0 0; font-size:.78rem; letter-spacing:.06em; text-transform:uppercase;
            color:var(--mut); font-family:system-ui,sans-serif }}
table {{ border-collapse:collapse; width:100%; font-size:.92rem }}
td {{ border-bottom:1px solid var(--rule); padding:10px 12px; vertical-align:top }}
td.n {{ font:600 1rem ui-monospace,monospace; text-align:right; width:5rem;
        font-variant-numeric:tabular-nums; color:var(--accent) }}
td span {{ display:block; color:var(--mut); font-size:.84rem; margin-top:3px }}
a {{ color:var(--accent) }}
.big {{ display:inline-block; margin:8px 12px 0 0; padding:11px 18px; background:var(--accent);
        color:var(--bg); text-decoration:none; border-radius:3px; font:600 .95rem system-ui }}
footer {{ margin-top:52px; padding-top:14px; border-top:1px solid var(--rule);
          color:var(--mut); font:.8rem/1.7 system-ui; letter-spacing:.04em }}
code {{ font-size:.86em; background:var(--bg); padding:.1em .35em; border-radius:2px }}
</style>
<main>
<header>
  <h1>HCA diary data — pipeline preview</h1>
  <p class="lede">This is <code>hca-open-repo-redesign</code>: the cleaning and
  preparation of the source data behind <em>Andersen's Hvem Hvad Hvor</em>. It
  publishes prepared data; the website that consumes it lives in
  <code>hca-open-repo</code>.</p>
</header>

<div class="warn"><strong>This is a preview, not the published edition.</strong>
It is the site rebuilt from this repository's data, so it may show work that has
not been released. The published edition is at
<a href="https://ogiermontanus.github.io/hca-open-repo/mockup/index.html">ogiermontanus.github.io/hca-open-repo</a>.</div>

<h2>The site, built from this data</h2>
<p>Not a copy of the interface. The workflow checks out the publication
repository, hands it this package, and runs its build — so what you see below
is the real site, and it cannot drift from it.</p>
<p><a class="big" href="mockup/index.html">Open the site</a>
   <a class="big" href="web/index.html">The Places demo</a></p>

<h2>What the package contains</h2>
<div class="grid">
  <div><dt>{ctx['persons']:,}</dt><dd>person entries</dd></div>
  <div><dt>{ctx['works']:,}</dt><dd>work entries</dd></div>
  <div><dt>{ctx['places']:,}</dt><dd>place entries</dd></div>
  <div><dt>{ctx['refs']:,}</dt><dd>entity–page references</dd></div>
  <div><dt>{ctx['interface']}</dt><dd>files in the published interface</dd></div>
</div>

<h2>What checking it turned up</h2>
<p>Every one of these is reported and none is repaired: a citation or a name
here is evidence about a printed book, and a script that quietly rewrote it
would be inventing a claim. The CSVs are linked.</p>
<table>
{f}</table>

<h2>How it is kept</h2>
<p>Identifiers are <strong>carried, never derived</strong> — a content-derived
id changes when a typo is fixed and takes every citation with it. Updating a
register runs one command that carries every id it can, mints only for
genuinely new entries and for the extra rows a split produces, follows
references through a merge, and escalates rather than guesses. The same engine
serves any register.</p>

<footer>
  Built {ctx['built']} · data {ctx['b_sha']} · site {ctx['a_sha']}<br>
  CC BY 4.0 · H.C. Andersen Centret, Syddansk Universitet
</footer>
</main>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--site", type=Path, default=ROOT / "site")
    ap.add_argument("--a-sha", default="")
    args = ap.parse_args()

    site = args.site.resolve()
    site.mkdir(parents=True, exist_ok=True)

    # the review CSVs travel with the page so every number is checkable
    dest = site / "review"
    dest.mkdir(exist_ok=True)
    findings = []
    for fn, label, note in FINDINGS:
        src = REVIEW / fn
        n = rows(src)
        if src.exists():
            (dest / fn).write_bytes(src.read_bytes())
        findings.append((fn, label, note, n))

    ents = ROOT / "data" / "normalized" / "entities.csv"
    counts = {"person": 0, "work": 0, "place": 0}
    if ents.exists():
        with ents.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("entity_type") in counts:
                    counts[r["entity_type"]] += 1

    ctx = {
        "findings": findings,
        "persons": counts["person"], "works": counts["work"], "places": counts["place"],
        "refs": data_rows("data/normalized/references.csv"),
        "interface": sum(1 for l in (ROOT / "scripts" / "publish.py")
                         .read_text(encoding="utf-8").splitlines()
                         if l.strip().startswith('("data/')),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "b_sha": git("rev-parse", "--short", "HEAD"),
        "a_sha": args.a_sha or "not built",
    }
    (site / "index.html").write_text(page(ctx), encoding="utf-8")
    print(f"  wrote {site / 'index.html'}")
    for fn, label, note, n in findings:
        print(f"     {n:>5}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
