#!/usr/bin/env python3
"""
One-off split of PerXI09032, a five-entry fusion chain confirmed against
xlsx DimPer:
  Wendell, Henning (1838-1913), fil.dr., ... VI 305 306.
  Wendt, preussisk Officer i tyrkisk Tjeneste 1841.                (xlsx: dateless, matches)
  Westergaard, Chr. Jorgensen (1824-1894), Justitsraad, ...        (xlsx: exact match)
  Westergaard, N. L. (1815-1878), Professor i indisk-orientalsk
    Filologi, Etatsraad 1869.                                      (xlsx: exact match)
  Westrup, J. S. (1833-1901), Premierlojtnant i Artilleriet, ...   (xlsx has no exact
                                                                     match at these years --
                                                                     "Wichfeld" prefix is
                                                                     OCR/dash bleed from the
                                                                     preceding sub-entry)

Run from the repo root:
  python scripts/parsers/split_wendell_chain.py
"""
import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARSED_TSV = os.path.join(ROOT, "data", "parsed", "personregister_xi_parsed.tsv")


def main():
    with open(PARSED_TSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    fieldnames = list(rows[0].keys())

    # Entry ids are positional and shift after every split earlier in
    # this pipeline, so PerXI09032 does NOT reliably name this row any
    # more -- it silently matched an unrelated "Wedell-Wedellsborg" row
    # once, overwriting it. Match by content only, never by id.
    target = [r for r in rows if r["03_surname"] == "Wendell" and "Westergaard" in r["09_description"]]
    if len(target) != 1:
        raise SystemExit(f"expected exactly 1 target row, found {len(target)}")
    old = target[0]

    def entry(surname, given, birth, death, desc, refs_raw, refs_parsed):
        e = {k: "" for k in fieldnames}
        e.update({
            "02_entry_type": "standardpost",
            "03_surname": surname,
            "04_given_names": given,
            "05_sort_key": f"{surname}, {given}".strip().rstrip(","),
            "06_birth_year": birth,
            "07_death_year": death,
            "09_description": desc,
            "10_references_raw": refs_raw,
            "11_references_parsed": refs_parsed,
            "13_raw_text": (
                f"{surname}, {given} ({birth}-{death}), {desc} {refs_raw}".strip()
                if given else f"{surname}, {desc} {refs_raw}".strip()
            ),
        })
        return e

    wendell = dict(old)
    wendell["09_description"] = "fil.dr., senere Sognepræst i Bjørnlunda, Strängnäs Stift."
    wendell["10_references_raw"] = "VI 305 306."
    wendell["11_references_parsed"] = "VI:305;VI:306"
    wendell["13_raw_text"] = (
        "Wendell, Henning (1838-1913), fil.dr., senere Sognepræst i Bjørnlunda, "
        "Strängnäs Stift. VI 305 306."
    )

    wendt = entry("Wendt", "", "", "", "preussisk Officer i tyrkisk Tjeneste 1841.", "", "")

    westergaard1 = entry(
        "Westergaard", "Chr. Jørgensen", "1824", "1894",
        "Justitsraad, 1866 Sekretær hos Krigsministeren, Overkrigskommissær.", "", "",
    )

    westergaard2 = entry(
        "Westergaard", "N. L.", "1815", "1878",
        "Professor i indisk-orientalsk Filologi, Etatsraad 1869.", "", "",
    )

    westrup = entry(
        "Westrup", "J. S.", "1833", "1901",
        "Premierløjtnant i Artilleriet, Afsked med Kaptajns Karakter 1875, militærpolitisk Forfatter.",
        "IV 370-72.", "IV:370;IV:371;IV:372",
    )

    out = []
    for r in rows:
        if r is old:
            out.extend([wendell, wendt, westergaard1, westergaard2, westrup])
        else:
            out.append(r)

    for i, r in enumerate(out, start=1):
        r["01_entry_id"] = f"PerXI{i:05d}"

    assert len(out) == len(rows) + 4

    with open(PARSED_TSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        w.writeheader()
        w.writerows(out)

    print(f"wrote {len(out)} rows (was {len(rows)})")


if __name__ == "__main__":
    main()
