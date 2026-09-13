"""
sources.py — which release is authoritative for which entity, and why.

The migration plan originally assumed one flag would flip the whole pipeline
from V0.82 to V0.92 once a works register shipped. V0.94 made that impossible:
**no single release covers every entity.** It brought the works register that
was being waited for and dropped the person register entirely; V0.92's persons
cover two diary volumes out of ten.

So the source is chosen per entity type, and this is where that choice is
written down rather than left implicit in whichever ingester happens to run.
`report()` prints it; `scripts/normalization/*` and the enrichment passes are
expected to agree with it.

Each entry records what is authoritative *today* and what would have to change
for the newest release to take over. "Newest" is never the reason on its own —
the authoritative source is the one a human maintains deliberately.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    entity: str
    release: str
    reason: str
    blocker: str = ""


SOURCES = (
    Source("persons", "segmentation output",
           "Not a workbook at all. V0.94 has no person register; V0.92's "
           "covers volumes VI-VII only, 8,917 entries against the live "
           "10,228. data/parsed/personregister_xi_parsed.tsv carries 45,293 "
           "page references against references.csv's 39,361.",
           "V0.82 remains the spine until the HCAP-to-Reg crosswalk is "
           "accepted; 97.8 % resolved, 209 entries in review."),

    Source("person references", "V0.82 + segmentation output (MERGED)",
           "Done, step 10c. 11,220 references added across 2,358 people, "
           "+16.2 %. Strictly additive and append-only: the first 69,583 "
           "lines of references.csv are byte-identical, so no person lost a "
           "reference and dropping the tail restores the previous state. "
           "Excluded: 2,190 references from 27 entries that absorbed a "
           "neighbour's citation list during OCR segmentation, 12 citing "
           "pages that do not exist, and 614 behind unresolved crosswalk "
           "rows.",
           ""),

    Source("person identifiers", "Reg… (unchanged, public)",
           "Step 10d. The segmentation's HCAP ids are internal; the site "
           "keeps citing Reg… . The register is a citable scholarly resource "
           "with a published version URL, and persons.html?reg=Reg… is what "
           "external links point at — breaking them to tidy an internal id "
           "space is a bad trade. The crosswalk carries the indirection "
           "instead, which costs one join and no citations.",
           "Entries with no Reg counterpart need ids in a documented, "
           "non-colliding range before the spine can swap (step 10e)."),

    Source("works", "V0.82",
           "V0.94's 5-WORK-Registry is ready to take over — 3,590 rows, and "
           "OLDWorkID resolves 3,590 of 3,590 into entities.csv, a complete "
           "crosswalk.",
           "Adoption changes site output, so it needs a before/after against "
           "the build baseline. Not yet run."),

    Source("work artist / museum / city", "V0.82 regex",
           "V0.94 supplies these as real columns (2,113 / 576 / 574 filled), "
           "retiring the title-parenthesis regex in the publication repo.",
           "Lands with the works register."),

    Source("places", "V0.82",
           "V0.94's place attributes are strictly better: of 2,327 places "
           "shared by label, country disagrees on 1 and category on 5, and "
           "every disagreement is the live side being empty. It also has 106 "
           "places the live file lacks.",
           "Identity, not attributes, is the blocker: OLDLocationID resolves "
           "0 of 2,433, so places cannot be cut over on id. A label-join "
           "crosswalk has to be built first, as was done for persons."),

    Source("place coordinates", "Rejser + SV14",
           "V0.94 provisions Latitude/Longitude and fills neither, so the two "
           "geographic sources remain the only ones.",
           "Would change if the columns are ever populated."),

    Source("place country", "verified-places workbook",
           "Four sources exist for this field; the precedence order is in "
           "docs/architecture.md 2. V0.94 ranks first once places are "
           "adopted.",
           "Same as places."),

    Source("diary pages", "V0.82",
           "V0.94 covers all ten volumes, 4,413 pages, against diary.csv's "
           "2,177 for VI-VII only.",
           "V0.94 carries no diary text, so it can extend the page list but "
           "cannot replace the diary."),

    Source("diary text", "V0.82",
           "The only source that has it.", ""),

    Source("KB page permalinks", "the KB link workbook (unchanged)",
           "V0.94 fills KBLinkString on all 4,413 pages and every URL is "
           "byte-identical to what build_kb_links.py derives from the "
           "OffSetTab rule. The plan listed this as an unambiguous win; "
           "measuring it showed the opposite. V0.94 *states* the links, while "
           "the workbook lets them be *derived* and checked — and that check "
           "earns its keep: it caught vol I page 13, where the stored link "
           "points at page 32's file. Switching would trade a live validation "
           "for no change in output. V0.94 is used to confirm the rule "
           "instead, which is what a second independent source is good for.",
           "Revisit only if the workbook stops being maintained."),

    Source("calendar / date precision", "V0.82",
           "V0.94 has an explicit calendar with PrecisionYear / "
           "PrecisionMonth columns and a DateStatus vocabulary, replacing the "
           "ad-hoc YYYY-MM-XX handling.",
           "Lands with the diary page list."),

    Source("work/place references", "V0.82",
           "V0.94 withdrew V0.92's fact tables and re-encoded references as "
           "space-separated key lists inside the dimension rows.",
           "Those lists cannot express per-reference order, so references.csv's "
           "seq column cannot be reconstructed from them — only re-invented."),
)


def report() -> str:
    out = ["Authoritative source per entity", "=" * 70]
    for s in SOURCES:
        out.append(f"\n{s.entity}")
        out.append(f"  source : {s.release}")
        out.append(f"  why    : {s.reason}")
        if s.blocker:
            out.append(f"  blocked: {s.blocker}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(report())
