#!/usr/bin/env python3
"""
make_gender_tagging_files.py
----------------------------
Genererer tre Excel-filer til manuel kønsvurdering af poster, som
parse_person_gender.py efterlader som "Endnu ubestemt". Se
docs/reports/gender-inference-experiment.md og aftalen om, hvordan de
menneskelige vurderinger bruges:

  1_maaling_100_tilfaeldige.xlsx   100 tilfældige ubestemte personer. Giver den
                                   første ground truth på målgruppen. MÅ IKKE
                                   bruges til at udlede regler — kun til at
                                   måle de regler, der udledes fra fil 2 og 3.
  2_erhvervsord.xlsx               De 200 hyppigste erhvervsord blandt de
                                   ubestemte, som anbefalingen ikke afgør.
                                   Vurderes pr. ord, ikke pr. person.
  3_maalrettede_poster.xlsx        Poster, hvor kvinder sandsynligvis findes
                                   (LR-kvindekø, kvindelige erhvervsformer,
                                   poster uden erhvervsord, trukket tilfældigt). Overlapper ikke
                                   fil 1. Bruges til at udlede kvinde-regler.

Modellens forudsigelser vises bevidst IKKE i filerne, så de ikke påvirker
vurderingen. De kan kobles på via entity_id ved indlæsning.

Kør:
    python scripts/enrichment/make_gender_tagging_files.py

Kræver openpyxl, pandas, numpy og scikit-learn (importerer
gender_inference_experiments). Forudsætter, at
gender_inference_experiments.py er kørt (unknown_predictions.csv).
"""

import csv
import os
import random
import re
import sys
from collections import Counter, defaultdict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gender_inference_experiments as G  # noqa: E402

ROOT = G.ROOT
PRED = os.path.join(G.OUT, "unknown_predictions.csv")
OUT = os.path.join(G.OUT, "tagging")
SEED = G.SEED

N_RANDOM = 100
N_WORDS = 200
N_NO_EVIDENCE = 30

FEM_ENDING_RE = re.compile(r"(?:rske|jomfru|dame|pige|kone|trice|esse|euse|rice|inde)$")
# Ord, der er nationalitets-/stedsangivelser eller fyldord og ikke erhverv, tælles
# stadig med — det er menneskets opgave at sortere dem fra ("Ikke et erhverv").

PERSON_CHOICES = "Mand,Kvinde,Uafgørligt,Ikke en enkeltperson"
CERTAINTY = "Sikker,Usikker"
BASIS = "Fornavn,Beskrivelse,Kender personen,Slået op,Gæt"
WORD_CHOICES = "Kun mænd,Kun kvinder,Begge køn forekommer,Ikke et erhverv"

HEAD_FILL = PatternFill("solid", fgColor="DDE6F0")
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC")


def load_refs():
    refs = defaultdict(list)
    with open(os.path.join(ROOT, "data", "normalized", "references.csv"),
              encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["vol"] and r["page"]:
                refs[r["entity_id"]].append(f"{r['vol']}:{r['page']}")
    return refs


def write_sheet(path, instructions, columns, rows, validations, widths):
    """columns: [(header, key, is_input)]. validations: {key: 'a,b,c'}."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Vurdering"
    for j, (head, _, is_input) in enumerate(columns, 1):
        c = ws.cell(row=1, column=j, value=head)
        c.font = Font(bold=True)
        c.fill = INPUT_FILL if is_input else HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, row in enumerate(rows, 2):
        for j, (_, key, is_input) in enumerate(columns, 1):
            c = ws.cell(row=i, column=j, value=row.get(key, ""))
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if is_input:
                c.fill = INPUT_FILL
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w
    ws.freeze_panes = "A2"
    keys = [k for _, k, _ in columns]
    for key, options in validations.items():
        col = ws.cell(row=1, column=keys.index(key) + 1).column_letter
        dv = DataValidation(type="list", formula1=f'"{options}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{len(rows) + 1}")
    ws.auto_filter.ref = ws.dimensions
    vs = wb.create_sheet("Vejledning", 0)
    vs.column_dimensions["A"].width = 110
    for i, line in enumerate(instructions, 1):
        c = vs.cell(row=i, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            c.font = Font(bold=True, size=13)
    wb.save(path)


def person_row(p, pred_by_id, refs):
    return {
        "entity_id": p["id"], "label": p["label"], "beskrivelse": p["desc"],
        "nationalitet": p["nat"],
        "henvisninger": ", ".join(refs.get(p["id"], [])[:6]),
    }


PERSON_COLS = [
    ("entity_id", "entity_id", False), ("Label", "label", False),
    ("Beskrivelse", "beskrivelse", False), ("Nationalitet (udledt)", "nationalitet", False),
    ("Dagbogsreferencer (bind:side)", "henvisninger", False),
    ("Køn", "koen", True), ("Sikkerhed", "sikkerhed", True),
    ("Hvad bygger du på?", "grundlag", True), ("Kommentar", "kommentar", True),
]
PERSON_WIDTHS = [12, 38, 60, 14, 22, 18, 12, 20, 40]
PERSON_VALID = {"koen": PERSON_CHOICES, "sikkerhed": CERTAINTY, "grundlag": BASIS}

PERSON_RULES = [
    "Vælg Mand/Kvinde, når kønnet fremgår eller du kender personen. Brug 'Uafgørligt', hvis det ikke kan afgøres — det er et gyldigt svar og lige så værdifuldt.",
    "Vælg 'Ikke en enkeltperson' for grupper, familier, firmaer, henvisninger og fejlsegmenterede rækker.",
    "Sikkerhed: 'Sikker' = du ville stå inde for det. 'Usikker' = bedste bud.",
    "'Hvad bygger du på?': Fornavn / Beskrivelse / Kender personen / Slået op (kilde uden for registret) / Gæt. Det bruges til at skelne, hvad datasættet selv kan sige, fra hvad der kræver ekstern viden.",
    "Der vises ingen maskinelle forudsigelser, med vilje.",
]


def main():
    os.makedirs(OUT, exist_ok=True)
    persons, _, markers, _ = G.load()
    by_id = {p["id"]: p for p in persons}
    refs = load_refs()
    mterms = G.marker_terms(markers)
    nat_words = G.nat_words_from(persons)

    with open(PRED, encoding="utf-8", newline="") as f:
        pred = {r["entity_id"]: r for r in csv.DictReader(f)}
    live = sorted(pred)                       # 2.671 egentlige ubestemte personer
    undecided = [e for e in live if not pred[e]["anbefalet"]]

    # ── Fil 1: tilfældig stikprøve af ALLE egentlige ubestemte ────────────
    rng = random.Random(SEED)
    sample1 = rng.sample(live, N_RANDOM)
    rows1 = [person_row(by_id[e], pred, refs) for e in sample1]
    write_sheet(
        os.path.join(OUT, "1_maaling_100_tilfaeldige.xlsx"),
        ["Fil 1 — Måling: 100 tilfældige ubestemte personer",
         "Formål: første rigtige ground truth på målgruppen. Stikprøven er trukket "
         "tilfældigt blandt alle 2.671 egentlige personer, som i dag er 'Endnu "
         "ubestemt' (både dem, anbefalingen afgør, og dem, den ikke afgør).",
         "VIGTIGT: Disse 100 poster må ikke bruges til at udlede regler, kun til at måle dem. "
         "Hvis du tager noget med herfra over i fil 2 eller 3, skal det ske uafhængigt af denne fil.",
         *PERSON_RULES],
        PERSON_COLS, rows1, PERSON_VALID, PERSON_WIDTHS)

    # ── Fil 2: erhvervsord blandt de uafgjorte ────────────────────────────
    occ = {e: G.occupation(by_id[e]["desc"], mterms, nat_words) for e in undecided}
    cnt = Counter(w for w in occ.values() if w)
    top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:N_WORDS]
    ex = defaultdict(list)
    for e in undecided:
        w = occ[e]
        if w and len(ex[w]) < 3:
            p = by_id[e]
            ex[w].append(f"{p['label']} — {p['desc'][:70]}")
    rows2 = [{"ord": w, "antal": n, "eksempler": "\n".join(ex[w])} for w, n in top]
    covered = sum(n for _, n in top)
    write_sheet(
        os.path.join(OUT, "2_erhvervsord.xlsx"),
        ["Fil 2 — Erhvervsord (vurderes pr. ord, ikke pr. person)",
         f"De {N_WORDS} hyppigste ord blandt de {len(undecided)} ubestemte personer, som "
         f"anbefalingen ikke afgør. Ordene dækker {covered} poster.",
         "Ordet er det første ikke-markør-ord i beskrivelsens hovedled (før 'af', 'til', 'med' …). "
         "Det er ikke altid et erhverv: 'fra', 'ung', 'Stockholm', 'passager' kan forekomme.",
         "Vælg: 'Kun mænd' (næsten alle bærere i denne periode og kontekst er mænd), "
         "'Kun kvinder', 'Begge køn forekommer', eller 'Ikke et erhverv' (så ignoreres ordet).",
         "Er du i tvivl, så vælg 'Begge køn forekommer' — reglen bliver så ikke brugt. "
         "Eksemplerne viser tre poster med ordet. Kommentaren kan bruges til undtagelser "
         "(fx 'kun mand, hvis ikke -inde')."],
        [("Erhvervsord", "ord", False), ("Antal blandt ubestemte", "antal", False),
         ("Eksempler", "eksempler", False),
         ("Vurdering", "vurdering", True), ("Kommentar", "kommentar", True)],
        rows2, {"vurdering": WORD_CHOICES}, [24, 14, 90, 24, 40])

    # ── Fil 3: målrettede poster (ekskl. fil 1) ───────────────────────────
    chosen, strata = [], {}
    taken = set(sample1)

    def take(eid, why):
        if eid not in taken:
            taken.add(eid)
            chosen.append(eid)
            strata[eid] = why

    for e in live:   # LR's kvindekø (S3 siger K ≥ 0,95, S2 afgør ikke)
        r = pred[e]
        if not r["S2_kaskade"] and r["S3_lr"] == "K" and float(r["S3_konf"]) >= 0.95:
            take(e, "LR-kvindekø")
    for e in live:   # kvindelige erhvervsformer
        w = occ.get(e) or G.occupation(by_id[e]["desc"], mterms, nat_words)
        if w and FEM_ENDING_RE.search(w):
            take(e, f"kvindelig erhvervsform ({w})")
    no_ev = [e for e in undecided if not occ[e] and e not in taken]
    for e in random.Random(SEED + 1).sample(no_ev, min(N_NO_EVIDENCE, len(no_ev))):
        take(e, "intet erhvervsord")
    rows3 = [{**person_row(by_id[e], pred, refs), "stratum": strata[e]} for e in chosen]
    write_sheet(
        os.path.join(OUT, "3_maalrettede_poster.xlsx"),
        ["Fil 3 — Målrettede poster til at finde kvindemønstre",
         f"{len(rows3)} ubestemte personer udvalgt, fordi kvinder sandsynligvis findes blandt dem. "
         "Overlapper ikke fil 1 (målesættet).",
         "Kolonnen 'Udvalgt fordi' viser, hvorfor posten er med. Den afslører kun udvælgelsen, ikke et facit — "
         "vurder posten selv.",
         "Formål: at lære regler for, hvordan kvinder viser sig i beskrivelserne (fx -pige, -kone, -dame, -ske). "
         "Brug kommentarfeltet til at notere ord eller vendinger, der afgjorde sagen.",
         *PERSON_RULES],
        [*PERSON_COLS[:5], ("Udvalgt fordi", "stratum", False), *PERSON_COLS[5:]],
        rows3, PERSON_VALID, [12, 38, 60, 14, 22, 28, 18, 12, 20, 40])

    print(f"fil 1: {len(rows1)} poster")
    print(f"fil 2: {len(rows2)} ord, dækker {covered} af {len(undecided)} uafgjorte")
    print(f"fil 3: {len(rows3)} poster:", dict(Counter(
        s.split(" (")[0] for s in strata.values())))


if __name__ == "__main__":
    main()
