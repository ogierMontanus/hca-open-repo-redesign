#!/usr/bin/env python3
"""Compute subgroup (layer-2) classification counts against the SV14 register,
to validate the proposed subgroup taxonomy before writing it into place-typology.md."""
import os
import xml.etree.ElementTree as ET
from collections import Counter
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_place_excel import classify, PPL_NAME_OVERRIDE, CATEGORY_NAMES

NS = {'tei': 'http://www.tei-c.org/ns/1.0'}

# svNames er et separat repo, normalt checket ud som søsterkatalog til
# hca-open-repo (jf. sessionens repo-scope). Overstyr med miljøvariablen
# SVNAMES_PLACES_XML, hvis din lokale opsætning afviger.
SVNAMES_PLACES_XML = os.environ.get(
    'SVNAMES_PLACES_XML',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'svNames', 'data', 'registers', 'places.xml'),
)

# Layer-2 subgroup lookup keyed by exact GeoNames code
SUBGROUP_BY_CODE = {
    # Kategori 1 -- bebygget
    'P.PPLC': 'hovedstad',
    'P.PPLA': 'regionssaede', 'P.PPLA2': 'regionssaede', 'P.PPLA3': 'regionssaede',
    'P.PPLA4': 'regionssaede', 'P.PPLA5': 'regionssaede',
    'P.PPL': 'by_landsby', 'A.ADM3': 'by_landsby', 'A.ADM4': 'by_landsby', 'A.ADM5': 'by_landsby',
    'P.PPLX': 'bydel',
    'P.PPLH': 'historisk_bebyggelse', 'P.PPLQ': 'historisk_bebyggelse', 'P.PPLW': 'historisk_bebyggelse',

    # Kategori 2 -- admreg
    'A.PCLI': 'suveraen_stat',
    'A.ADM1': 'provins', 'A.ADM2': 'provins',
    'L.RGN': 'landskabsregion', 'L.RGNH': 'landskabsregion', 'L.RGNE': 'landskabsregion', 'L.RGNL': 'landskabsregion',

    # Kategori 3 -- vand
    'H.STM': 'vandloeb', 'H.CNL': 'vandloeb', 'H.STMC': 'vandloeb',
    'H.LK': 'soe', 'H.LKS': 'soe',
    'H.SEA': 'hav', 'H.OCN': 'hav',
    'H.STRT': 'straede_sund', 'H.SD': 'straede_sund', 'H.NRWS': 'straede_sund',
    'H.BAY': 'bugt_havn', 'H.HBR': 'bugt_havn', 'H.GULF': 'bugt_havn', 'H.COVE': 'bugt_havn',

    # Kategori 4 -- landskab
    'T.ISL': 'oe', 'T.ISLS': 'oe',
    'L.CONT': 'kontinent',
    'T.MT': 'bjerg', 'T.MTS': 'bjerg', 'T.HLL': 'bjerg', 'T.PK': 'bjerg',
    'T.VLC': 'vulkan',
    'T.CLF': 'klippe', 'T.RK': 'klippe',
    'T.GRGE': 'kloeft_dal', 'T.VAL': 'kloeft_dal',
    'T.PASS': 'pas',
    'T.CAPE': 'forbjerg', 'T.PROM': 'forbjerg',
    'S.CAVE': 'grotte',
    'H.FLLS': 'vandfald', 'H.FLLSX': 'vandfald',

    # Kategori 5 -- anlaeg
    'S.CH': 'religioes_bygning', 'S.MSTY': 'religioes_bygning', 'S.MSQE': 'religioes_bygning',
    'S.TMPL': 'religioes_bygning', 'S.CVNT': 'religioes_bygning', 'S.HERM': 'religioes_bygning',
    'S.CSTL': 'slot_borg', 'S.PAL': 'slot_borg', 'S.EST': 'slot_borg', 'S.FT': 'slot_borg',
    'S.MUS': 'kulturinstitution', 'S.THTR': 'kulturinstitution', 'S.OPRA': 'kulturinstitution',
    'S.ANS': 'fortidsminde', 'S.MNMT': 'fortidsminde', 'S.RUIN': 'fortidsminde',
    'S.CMTY': 'fortidsminde', 'S.GRVE': 'fortidsminde', 'S.AMTH': 'fortidsminde',
    'S.SQR': 'infrastruktur', 'S.BDG': 'infrastruktur', 'S.GATE': 'infrastruktur',
    'S.ARCH': 'infrastruktur', 'S.WALLA': 'infrastruktur',
    'R.RD': 'infrastruktur', 'R.ST': 'infrastruktur', 'R.TNL': 'infrastruktur',
    'S.HSE': 'bolig_erhverv', 'S.FRM': 'bolig_erhverv', 'S.HTL': 'bolig_erhverv',
    'S.RSRT': 'bolig_erhverv', 'S.BLDG': 'bolig_erhverv',

    # Kategori 6 -- park
    'L.PRK': 'bypark',
    'S.GDN': 'have',
    'L.RESN': 'naturreservat', 'L.RES': 'naturreservat', 'L.RESA': 'naturreservat',
    'L.RESF': 'naturreservat', 'L.RESH': 'naturreservat', 'L.RESP': 'naturreservat',
    'L.RESV': 'naturreservat', 'L.RESW': 'naturreservat',
}

# Manual subgroup assignment for the individually-reviewed PPL entries
# (skov is genuinely new here -- no GeoNames code observed for it)
PPL_SUBGROUP = {
    "Odense Adelige Jomfrukloster": "religioes_bygning",
    "Klokkedybet": "vandloeb",
    "Nonnebakken": "fortidsminde",
    "Munke-Mose": "bypark",
    "Hunderup Skov": "skov",
    "Skt. Knuds Kirke": "religioes_bygning",
    "Dalum": "by_landsby",
    "Sankt Knuds Kirke": "religioes_bygning",
    "Vor Frue Kirke": "religioes_bygning",
    "Næsbyhoved Skov": "skov",
    "Lübeck Rådhus": "infrastruktur",
    "den botaniske Have": "have",
    "Falleberthor": None,
    "Der Braunschweiger Dom": "religioes_bygning",
    "Burg Dankwarderode": "slot_borg",
    "Zwinger Tower": "slot_borg",
    "Hovedkirken ": "religioes_bygning",
    "Kloster Ilsenburg": "religioes_bygning",
    "Ilse dalen": "kloeft_dal",
    "Bloksbjerg": "bjerg",
    "Teufelsmauer": "klippe",
    "Baumannshöhle": "grotte",
    "Schloss Blankenburg": "slot_borg",
    "Gellerts Grav": "fortidsminde",
    "Hôtel de Bavière": "bolig_erhverv",
    "Leipziger Altes Theater": "kulturinstitution",
    "Dom zu Meißen": "religioes_bygning",
    "Albrechtsburg Meissen": "slot_borg",
    "Augustusbrücke": "infrastruktur",
    "det kongelige Theater": "kulturinstitution",
    "Linchkeschen Bade": "bolig_erhverv",
    "Das grüne Gewölb": "kulturinstitution",
    "Schloß Lohmen": "slot_borg",
    "Dorfkirche Lohmen": "religioes_bygning",
    "Teufelsküche": "klippe",
    "Felsenburg Neurathen": "slot_borg",
    "Teufelsbrücke": "infrastruktur",
    "St-Johannis-Kirche": "religioes_bygning",
    "Sneiderloch": "grotte",
    "Böhmen": "landskabsregion",
    "Stadtkirche St. Marien": "religioes_bygning",
    "Plauenscher Grund": "kloeft_dal",
    "Der Kaiser von Rusland": "bolig_erhverv",
    "Operahuset Webers": "kulturinstitution",
    "Königstätisches Theater": "kulturinstitution",
    "Konzerthaus Berlin": "kulturinstitution",
    "Museet ": "kulturinstitution",
    "Schloss Ludwigslust": "slot_borg",
    "Italien ": "suveraen_stat",
    "Accademia di San Luca": "kulturinstitution",
    "Tomba di Virgilio": "fortidsminde",
    "Klosteret St. Antonio": "religioes_bygning",
    "Carlo Felice": "kulturinstitution",
    "Teatro Pallacorda": "kulturinstitution",
    "Teatro Alibert": "kulturinstitution",
    "Teatro di Apollo": "kulturinstitution",
    "Teatro dei Fiorentini": "kulturinstitution",
    "Teatro Fenise": "kulturinstitution",
    "Kongens Nytorv": "infrastruktur",
    "Schloss Breitenburg": "slot_borg",
    "Schöner Brunnen": "infrastruktur",
    "Sebalduskirche": "religioes_bygning",
    "Hofkirche Innsbruck": "religioes_bygning",
    "Palazzo degli Uffizi": "slot_borg",
    "Valico di Somma": "pas",
    "monte mario": "bjerg",
    "Palazzo Borghese": "slot_borg",
    "Via di Ripetta": "infrastruktur",
    "Chiesa di Sant'Antonio Abate all'Esquilino": "religioes_bygning",
    "Grotterne": "grotte",
    "Grande Cascata di Tivoli": "vandfald",
    "Via della Purificazione": "infrastruktur",
    "Santa Maria in Traspontina": "religioes_bygning",
    "Mola di Gaeta": "by_landsby",
    "Teatro di San Carlo": "kulturinstitution",
    "Piazza Municipio": "infrastruktur",
    "Chiesa di Santa Maria della Mercede a Montecalvario": "religioes_bygning",
    "Katidral ta’ San Pawl": "religioes_bygning",
    "Ermou": "infrastruktur",
    "Themistocles Tomb": "fortidsminde",
    "Galata Mevlevihanesi Müzesi": "religioes_bygning",
    "Mısır Çarşısı": "infrastruktur",
    "Emirgan Mosque": "religioes_bygning",
    "Kız Kulesi": "fortidsminde",
    "Ovidius Kulesi": "fortidsminde",
    "Canalul Dunăre-Marea Neagră": "vandloeb",
    "Trajan's Plaque": "fortidsminde",
    "Golubac Fortress": "slot_borg",
    "Petrovaradin fortress": "slot_borg",
}

# Enkelttilfælde hvor topkategorien allerede afviger fra den rå GeoNames-kode
# (jf. NAMED_CASES/NAMED_CASES_BY_NAME i classify()) -- undergruppen SKAL følge
# samme afvigelse, ellers modsiger de to lag hinanden (fx "anlaeg" + "have").
NAMED_SUBGROUP_OVERRIDE_BY_NAME = {
    'Hippodrome of Constantinople': 'fortidsminde',  # top-niveau: anlaeg, ikke park/have
}
NAMED_SUBGROUP_OVERRIDE_BY_ID = {
    # geo-982821 (Lilienstein, fejlkoblet) er 'usikker' på topniveau og
    # springes automatisk over nedenfor -- ingen undergruppe nødvendig.
}

# Poster uden brugbar GeoNames-kode, klassificeret på navn/notetekst i regel 4
FALLBACK_SUBGROUP_BY_NAME = {
    'Deya': 'by_landsby',       # notetekst: "a small coastal village"
    'Via Sistina': 'infrastruktur',  # gadenavn, jf. regel 4 navnemønster
}

tree = ET.parse(SVNAMES_PLACES_XML)
root = tree.getroot()
places = root.findall('.//tei:place', NS)

subgroup_counter = Counter()
top_by_subgroup = {}
missing_subgroup = []
examples = {}

for p in places:
    xml_id = p.get('{http://www.w3.org/XML/1998/namespace}id', '')
    geotype = p.get('type')
    main_name_el = p.find('tei:placeName[@type="main"]', NS)
    name = main_name_el.text if main_name_el is not None and main_name_el.text else '(uden navn)'
    note_el = p.find('tei:note', NS)
    note_text = note_el.text if note_el is not None and note_el.text else ''

    top_slug, method, reason = classify(xml_id, name, geotype, note_text)
    if top_slug == 'usikker':
        continue  # identity unresolved -- no subgroup either

    if xml_id in NAMED_SUBGROUP_OVERRIDE_BY_ID:
        sub = NAMED_SUBGROUP_OVERRIDE_BY_ID[xml_id]
    elif name in NAMED_SUBGROUP_OVERRIDE_BY_NAME:
        sub = NAMED_SUBGROUP_OVERRIDE_BY_NAME[name]
    elif geotype == 'PPL' and name in PPL_SUBGROUP:
        sub = PPL_SUBGROUP[name]
    elif geotype in SUBGROUP_BY_CODE:
        sub = SUBGROUP_BY_CODE[geotype]
    elif name in FALLBACK_SUBGROUP_BY_NAME:
        sub = FALLBACK_SUBGROUP_BY_NAME[name]
    else:
        sub = None

    if sub is None:
        missing_subgroup.append((name, geotype, top_slug))
        continue

    subgroup_counter[sub] += 1
    top_by_subgroup.setdefault(sub, top_slug)
    examples.setdefault(sub, []).append(name)

print(f"Total places: {len(places)}")
print(f"Classified into a subgroup: {sum(subgroup_counter.values())}")
print(f"Missing subgroup (need review): {len(missing_subgroup)}")
for n, t, top in missing_subgroup:
    print(f"  MISSING SUBGROUP: {n!r} (type={t!r}, top={top!r})")

print("\n--- Subgroup counts ---")
for sub, n in sorted(subgroup_counter.items(), key=lambda x: (top_by_subgroup[x[0]], -x[1])):
    ex = ', '.join(examples[sub][:3])
    print(f"[{top_by_subgroup[sub]:9s}] {sub:22s} n={n:3d}  e.g. {ex}")
