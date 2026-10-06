#!/usr/bin/env python3
"""
build_gender_review_excel.py
----------------------------
Bygger et Excel-gennemsyn af kønskategoriseringen for personregistret, med de
nye kategorier fra gender_inference_experiments.py:

    Mandlig / Kvindelig                          parserens afgørelse (≥ 0,70), uændret
    Endnu ubestemt, sandsynligvis kvinde         parseren (< 0,70) har ikke afgjort, men
    Endnu ubestemt, sandsynligvis mand           evidensen peger i en retning
    Endnu ubestemt, kræver manuelt gennemsyn     de få ægte tvivlstilfælde
    Irrelevant                                   firmaer, slægter, andre korporationer,
                                                 grupper og krydshenvisninger — køn er
                                                 ikke meningsfuldt, uanset hvor mange
                                                 personer posten dækker

Indlæser testworkbooken (default data/raw/hca-personregister-redesign_gender-
testing.xlsx) og bevarer dens kolonner A–P uændret: kolonne D er Navn, F Køn og G
Kønssikkerhed. Kolonne F og G omskrives kun for de poster, der var »Endnu
ubestemt«, eller som er irrelevante. Tilføjer Q (metode), R (grundlag) og S (Familiegruppe: posten samler flere personer og
skal deles i et senere berigelsestrin; kønnet på sådan en post er foreløbigt).

Arket sorteres efter G (stigende: de mest usikre først; tom = irrelevant sidst), derefter F, derefter D
(Navn, alfabetisk), og rækkerne farves efter F:

    indeholder »kvinde«   lyserød
    indeholder »mand«     blå
    Irrelevant            orange
    kræver manuelt gennemsyn   orange

Farven sættes som baggrund, skriftfarve og ramme, så den ses i alle fremvisere.

G for de nye kategorier er en sorteringsværdi, ikke parserens vægt: regelbaserede
forslag har 0,95, modelbaserede har den kalibrerede sandsynlighed, og »kræver
manuelt gennemsyn« har 0,5. G er tom for irrelevante poster.

Kør:
    python scripts/enrichment/build_gender_review_excel.py
    python scripts/enrichment/build_gender_review_excel.py --manual-below 0.70

Kræver openpyxl, numpy og scikit-learn (importerer gender_inference_experiments).
"""

import argparse
import csv
import os
import sys
from collections import Counter

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gender_inference_experiments as G  # noqa: E402
import gender_head_rules as H  # noqa: E402

P = G.P
ROOT = G.ROOT
DEFAULT_IN = os.path.join(ROOT, "data", "raw", "hca-personregister-redesign_gender-testing.xlsx")
DEFAULT_OUT = os.path.join(G.OUT, "hca-personregister-redesign_gender-review.xlsx")

MANUAL = os.path.join(ROOT, "data", "curated", "gender_manual_review.csv")
SHEET = "Personregister"
EXTRA = ["Kønsmetode", "Kønsgrundlag", "Familiegruppe"]

HEAD_FILL = PatternFill("solid", fgColor="444444")
# Farven sættes tre steder, så den også ses i fremvisere, der ignorerer fyld:
# baggrund (fuld ARGB med alfa FF, både fg og bg), skriftfarve og tynd ramme.
STYLES = {
    "pink": ("FFD6E8", "9C1F5E", "E58FB8"),
    "blue": ("CFE2FF", "1F4E96", "8FB4E8"),
    "orange": ("FFD9A0", "A64B00", "F0A030"),
}


def row_style(koen):
    """(fyld, skrift, ramme) for en Køn-værdi, eller None."""
    k = (koen or "").lower()
    if k == G.CAT_IRRELEVANT.lower() or "manuelt gennemsyn" in k:
        return STYLES["orange"]
    if "kvinde" in k:
        return STYLES["pink"]
    if "mand" in k:
        return STYLES["blue"]
    return None


def apply_style(cell, style):
    fill, font, line = style
    cell.fill = PatternFill("solid", start_color="FF" + fill, end_color="FF" + fill)
    cell.font = Font(color="FF" + font)
    side = Side(style="thin", color="FF" + line)
    cell.border = Border(left=side, right=side, top=side, bottom=side)


def sort_key(row, ci):
    """G (stigende: de mest usikre først; tom = irrelevant sidst), derefter F,
    derefter D (Navn, å som aa)."""
    g = row[ci["Kønssikkerhed (0–1)"]]
    return (2.0 if g in (None, "") else float(g), row[ci["Køn"]],
            G.strip_accents(row[ci["Navn"]] or ""), row[ci["Navn"]] or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=DEFAULT_IN)
    ap.add_argument("--output", default=DEFAULT_OUT)
    ap.add_argument("--manual-below", type=float, default=0.60,
                    help="modelsikkerhed under dette (mand) → manuelt gennemsyn (default 0,60)")
    ap.add_argument("--female-min", type=float, default=1.01,
                    help="laveste modelsikkerhed for et kvindeforslag fra modellen alene "
                         "(default 1,01 = slået fra: modellens kvindeforslag er for usikre)")
    ap.add_argument("--base-rate-male", action="store_true",
                    help="poster, hvor modellen kun er svag, får »sandsynligvis mand« ud fra "
                         "grundraten i stedet for »kræver manuelt gennemsyn«")
    args = ap.parse_args()

    wb_in = load_workbook(args.input)
    ws_in = wb_in[SHEET]
    header = [c.value for c in ws_in[1]]
    ci = {h: i for i, h in enumerate(header)}
    data = [list(r) for r in ws_in.iter_rows(min_row=2, values_only=True)]
    legend_lines = [r[0].value for r in wb_in["Læs mig"].iter_rows() if r[0].value]
    widths = {k: v.width for k, v in ws_in.column_dimensions.items()}
    print(f"Indlæst {len(data):,} poster fra {os.path.relpath(args.input, ROOT)}")

    # ── Parserens egen kategorisering over denne segmentering ─────────────
    markers = P.load_markers()
    titles = P.title_terms_from(markers)
    overrides = P.load_name_overrides()
    rows = [{"entity_id": r[ci["HCAP-ID"]], "label": r[ci["Navn"]] or "",
             "description": r[ci["Beskrivelse"]] or ""} for r in data]
    nats = {r[ci["HCAP-ID"]]: r[ci["Nationalitet"]].lower()
            for r in data if r[ci["Nationalitet"]]}
    roles = {r[ci["HCAP-ID"]]: [x.strip() for x in r[ci["Rolle / Erhverv"]].split(";") if x.strip()]
             for r in data if r[ci["Rolle / Erhverv"]]}
    persons, _, markers, _ = G.build_persons(rows, markers, titles, overrides, nats,
                                             existing=None, roles=roles)
    by_id = {p["id"]: p for p in persons}
    mism = sum(1 for r in data
               if (by_id[r[ci["HCAP-ID"]]]["existing"] is None) != (r[ci["Køn"]] == P.UNKNOWN))
    if mism:
        print(f"ADVARSEL: {mism} poster, hvor workbookens Køn afviger fra parserens genkørsel.")
    nat_words = G.nat_words_from(persons)
    mterms = G.marker_terms(markers)

    # ── Irrelevante poster (inkl. R0: par og blandede grupper) ────────────
    irr = {}
    fam = {}
    for r in data:
        p = by_id[r[ci["HCAP-ID"]]]
        kind, ground = G.family_group(p["label"], p["desc"], p["excluded"])
        if kind:
            fam[p["id"]] = (kind, ground)
        group_g = H.single_gender_group(p["label"], p["desc"])
        why = G.irrelevant_reason(p["label"], p["desc"], p["excluded"],
                                  parser_known=p["existing"] is not None,
                                  is_crossref=r[ci["Posttype"]] == "krydshenvisning",
                                  nat_words=nat_words, group_gender=group_g)             or H.r0_reason(kind, ground)
        if why:
            irr[p["id"]] = why
        # Træningsgrundlag: kun det, der ikke er afgjort irrelevant. Et kurateret
        # »crossReference« på en post med beskrivelse er et navnesammenfald.
        ex = why or (None if (p["excluded"] or "").startswith("kurateret: crossReference")
                     else p["excluded"])
        p["excluded"], p["stub"] = ex, ex is not None

    # ── Forslag til de ubestemte: S2 → R1–R4/P/B → R5 → S3 ────────────────
    pred_rows, _, _, name_lookup = G.infer_unknown(persons, markers, mterms, nat_words, titles)
    pred = {r["entity_id"]: r for r in pred_rows}
    ctx = H.Context(persons, titles, overrides, name_lookup)
    todo = [p["id"] for p in persons if p["existing"] is None and p["id"] not in irr]
    decided, r5_rows = H.decide_unknowns(
        persons, todo, pred, ctx, manual_below=args.manual_below,
        female_min=args.female_min, base_rate_male=args.base_rate_male)
    side = os.path.dirname(args.output)
    G.write_csv_to(os.path.join(side, "hcap_given_name_markers_male.csv"), r5_rows)
    G.write_csv_to(os.path.join(side, "hcap_rule_vs_parser_disagreements.csv"),
                   H.disagreements(persons, ctx, irr))
    G.write_csv_to(os.path.join(side, "hcap_head_terms_measured.csv"), H.measure_terms(persons, ctx))

    manual = {}
    if os.path.exists(MANUAL):
        with open(MANUAL, encoding="utf-8", newline="") as f:
            manual = {r["hcap_id"]: r["koen"] for r in csv.DictReader(f)}
        print(f"Manuel gennemgang: {len(manual)} afgørelser fra {os.path.relpath(MANUAL, ROOT)}")

    out_rows = []
    role_col = ci["Rolle / Erhverv"]
    for r in data:
        eid = r[ci["HCAP-ID"]]
        p = by_id[eid]
        new = list(r) + ["", "", ""]
        new[len(r) + 2] = " | ".join(x for x in fam.get(eid, ("", "")) if x)
        before = r[ci["Køn"]]
        if eid in irr:
            new[ci["Køn"]], new[ci["Kønssikkerhed (0–1)"]] = G.CAT_IRRELEVANT, None
            new[len(r)], new[len(r) + 1] = "irrelevant", irr[eid]
        elif before != P.UNKNOWN:
            new[len(r)] = "parser"
            new[len(r) + 1] = " | ".join(f"{k}: {t}" for _, _, k, t in p["inds"])
        else:
            d = decided[eid]
            if eid in manual:   # redaktørens gennemgang vinder over alle forslag
                k = manual[eid]
                d = {"kategori": k, "sikkerhed": None if k == G.CAT_IRRELEVANT else 1.0,
                     "metode": "manuel gennemgang",
                     "grundlag": f"redaktørens afgørelse (modelforslag: {d['kategori']}; {d['metode']})",
                     "rolle": ""}
            new[ci["Køn"]] = d["kategori"]
            new[ci["Kønssikkerhed (0–1)"]] = None if d["sikkerhed"] is None else round(d["sikkerhed"], 3)
            new[len(r)], new[len(r) + 1] = d["metode"], d["grundlag"]
            # P1–P5 sætter også rollen (kolonne H), hvis den ikke står der.
            have = [x.strip() for x in (new[role_col] or "").split(";") if x.strip()]
            for b in [x for x in d["rolle"].split("; ") if x]:
                if b not in have:
                    have.append(b)
            new[role_col] = "; ".join(have) or None
        out_rows.append((before, new))

    out_rows.sort(key=lambda t: sort_key(t[1], ci))
    final = [t[1] for t in out_rows]

    # ── Skriv arket ────────────────────────────────────────────────────────
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(header + EXTRA)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
    k_col = ci["Køn"]
    for row in final:
        ws.append(row)
        style = row_style(row[k_col])
        if style:
            for c in ws[ws.max_row]:
                apply_style(c, style)
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.column_dimensions[get_column_letter(k_col + 1)].width = 40
    ws.column_dimensions[get_column_letter(len(header) + 1)].width = 24
    ws.column_dimensions[get_column_letter(len(header) + 2)].width = 70
    ws.column_dimensions[get_column_letter(len(header) + 3)].width = 36
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions

    # ── Optælling ──────────────────────────────────────────────────────────
    after = Counter(r[k_col] for r in final)
    before = Counter(b for b, _ in out_rows)
    ts = wb.create_sheet("Optælling")
    ts.append(["Køn", "Før (parser)", "Efter"])
    for k in sorted(set(before) | set(after)):
        ts.append([k, before.get(k, 0), after.get(k, 0)])
    ts.append(["I alt", sum(before.values()), sum(after.values())])
    ts.append([])
    ts.append(["Kønskategori", "Metode", "Poster"])
    meth = Counter((r[k_col], r[len(header)]) for r in final if r[len(header)] != "parser")
    for (k, m), n in sorted(meth.items()):
        ts.append([k, m, n])
    ts.append([])
    ts.append(["Familiegruppe (skal deles senere)", "Type", "Poster"])
    for kind, n in Counter(k for k, _ in fam.values()).most_common():
        ts.append(["", kind, n])
    ts.append([])
    ts.append(["Irrelevant: grund", "", "Poster"])
    for why, n in Counter(irr.values()).most_common():
        ts.append([why, "", n])
    for c in ts[1]:
        c.font = Font(bold=True)
    ts.column_dimensions["A"].width = 46
    ts.column_dimensions["B"].width = 30
    ts.column_dimensions["C"].width = 14

    # ── Læs mig ────────────────────────────────────────────────────────────
    ls = wb.create_sheet("Læs mig", 0)
    ls.column_dimensions["A"].width = 150
    lines = legend_lines + [
        "",
        "KØNSGENNEMSYN (build_gender_review_excel.py)",
        "Køn har seks værdier. Mandlig/Kvindelig er enten parserens afgørelse (Kønsmetode = parser, sikkerhed ≥ 0,70) "
        "eller et afledt forslag med sikkerhed ≥ 0,71 (Kønsmetode = regel eller model; se Kønsgrundlag). "
        "»Endnu ubestemt, sandsynligvis …« gives KUN ved sikkerhed under 0,71:",
        "  Endnu ubestemt, sandsynligvis kvinde / mand — evidensen peger i en retning, men sikkerheden er under 0,71.",
        "  Endnu ubestemt, kræver manuelt gennemsyn — ingen evidens, uenige regler eller en model, der er for svag til at pege.",
        "  Irrelevant — firma, slægt eller anden korporation, gruppe, dyr eller krydshenvisning. Køn er ikke meningsfuldt "
        "for posten, uanset hvor mange personer den dækker.",
        f"Grænser (kan ændres på kommandolinjen): mand fra modelsikkerhed {args.manual_below:.2f}. "
        + ("Kvindeforslag fra modellen alene bruges ikke (de holdt ikke i stikprøven: romanske mandsnavne som "
           "Antoine og Andrea, og poster med kun efternavn); de ligger under »kræver manuelt gennemsyn« med modellens "
           "retning i Kønsgrundlag."
           if args.female_min > 1 else
           f"Kvinde fra modellen kun fra {args.female_min:.2f} og kun dansk/nordisk/tysk kontekst."),
        *(["Kørt med --base-rate-male: poster, hvor modellen kun er svag, er sat til »sandsynligvis mand« ud fra "
           "grundraten (≈ 76 % af de ubestemte er mænd; Kønssikkerhed 0,70). Det er ikke evidens om personen."]
          if args.base_rate_male else []),
        "Rækkefølge for de ubestemte: S2 (titel i beskrivelsen → fornavn → erhverv) → R1 titel i label → R2 slægts- og "
        "rolleord → R3 -inde/-esse → P1–P5 præst, militære grader, Abbé, Marquis/Pasha/Emir, Komtesse (sætter også Rolle) "
        "→ B1/B2 kønsord (-søn, -mester, -læge, -pige, -datter …) → R4 umarkeret erhverv (Forfatter, Maler …) → R5 fornavne "
        "i anden runde → S3-modellen. Ordlisterne står i data/curated/gender_head_terms_da.csv; reglerne er beskrevet i "
        "docs/gender-unclear-dictations.md. Giver to regler modsat køn, kræver posten manuelt gennemsyn. Regelniveau høj = 0,95, "
        "sandsynlig = 0,80; R5 = 0,71/0,77/0,85 efter hvor ofte navnet er set.",
        "Manuel gennemgang (Kønsmetode = manuel gennemgang): redaktørens afgørelser fra data/curated/gender_manual_review.csv "
        "overtager forslagene; Kønssikkerhed er sat til 1,0 (tom for Irrelevant).",
        "Kønssikkerhed for de nye kategorier er en SORTERINGSVÆRDI: regelbaseret 0,95, model = kalibreret sandsynlighed, "
        "manuelt gennemsyn 0,5, tom for irrelevante. Den er ikke parserens vægt og ikke en målt præcision.",
        "Sortering: Kønssikkerhed (stigende — de mest usikre først; irrelevante, uden sikkerhed, sidst), derefter Køn, derefter Navn. "
        "Farver: lyserød = Køn indeholder »kvinde«, blå = indeholder »mand«, orange = Irrelevant og »kræver manuelt gennemsyn« (farven er både baggrund, skrift og ramme).",
        "Familiegruppe (kolonne S) markerer poster, der samler flere personer: ægtepar (»X og Frue«), søskende (»Frøknerne«, »Brødrene X«), "
        "forældre/børn, familier og andre grupper. De skal DELES i et senere berigelsestrin; kønnet på sådan en post er foreløbigt. "
        "Se docs/gender-unclear-dictations.md, »Opdeling af familiegrupper«.",
        "Forslagene er automatiske og ikke kildeverificerede. Modelforslagene bygger på et register, hvis egen "
        "kategorisering er regelbaseret (se docs/reports/gender-inference-experiment.md).",
    ]
    for i, line in enumerate(lines, 1):
        c = ls.cell(row=i, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            c.font = Font(bold=True, size=13)

    try:
        wb.save(args.output)
    except PermissionError:   # filen er åben i Excel
        args.output = args.output.replace(".xlsx", "_ny.xlsx")
        wb.save(args.output)
        print("Den oprindelige fil er åben i Excel; gemte i stedet som:")
    print(f"Skrev {os.path.relpath(args.output, ROOT)}")
    print("\nKøn efter kørsel:")
    for k, n in sorted(after.items()):
        print(f"  {n:6,}  {k}")
    print("\nMetode for de nye kategorier:")
    for (k, m), n in sorted(meth.items()):
        print(f"  {n:6,}  {k}  [{m}]")


if __name__ == "__main__":
    main()
