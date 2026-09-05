#!/usr/bin/env python3
"""Map the existing §H fine-grained (33-subgroup) classification to the new
§K taxonomy (5 categories x up to 3 sub-categories, GeoNames-letter-based),
and run it against all 481 SV14 places to get real counts + surface the
concrete edge cases (harbours, gardens, parks, waterfalls) for review."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET
from collections import Counter
from build_place_excel import classify as classify_top  # old 6-cat classify()
from subgroup_classify import (
    SUBGROUP_BY_CODE, PPL_SUBGROUP, NAMED_SUBGROUP_OVERRIDE_BY_NAME,
    NAMED_SUBGROUP_OVERRIDE_BY_ID, FALLBACK_SUBGROUP_BY_NAME,
)

NS = {'tei': 'http://www.tei-c.org/ns/1.0'}

# Old §H subgroup slug -> new §K category.subcategory
# Water is restored as its own category (1), split natural (1.x) vs the
# H-codes that are man-made facilities (-> 3.3). None of §H's water
# subgroups were man-made-water-specific, so the split below is inferred
# per subgroup, not per raw code -- flagged explicitly where genuinely
# uncertain (harbours specifically).
OLD_TO_NEW = {
    # Kategori 1: Vandområder
    'vandloeb':      '1.1',  # ferskvand
    'soe':           '1.1',  # ferskvand
    'hav':           '1.2',  # saltvand
    'straede_sund':  '1.2',  # saltvand
    'bugt_havn':     '1.2',  # saltvand -- se note: havn kan argumenteres til 3.3
    'vandfald':      '1.1',  # ferskvand -- vand er nu egen kategori igen, ingen T-undtagelse nødvendig

    # Kategori 2: Landområder
    'bjerg':          '2.1',
    'klippe':         '2.1',
    'kloeft_dal':     '2.1',
    'vulkan':         '2.1',
    'pas':            '2.1',
    'oe':             '2.2',
    'grotte':         '2.3',  # S-klasse i GeoNames, videreført undtagelse fra §F/G
    'forbjerg':       '2.3',
    'kontinent':      '5',    # eksplicit undtagelse i brugerens instruktion (A + L.CONT)
    'landskabsregion':'2.3',  # L.RGN/L.RGNH bliver IKKE løftet til kat. 5 (kun L.CONT er nævnt)
    'bypark':         '2.3',  # L.PRK -- ingen subkategori nævner parker eksplicit, se note
    'skov':           '2.3',
    'naturreservat':  '2.3',

    # Kategori 3: Bygninger, veje og anlæg
    'religioes_bygning': '3.2',
    'slot_borg':          '3.1',
    'kulturinstitution':  '3.1',
    'bolig_erhverv':      '3.1',
    'infrastruktur':      '3.3',
    'fortidsminde':       '3.3',
    'have':               '3.3',  # S.GDN -- ingen bygning, "under åben himmel"

    # Kategori 4: Byer og tæt bebyggede zoner
    'hovedstad':            '4',
    'regionssaede':         '4',
    'by_landsby':           '4',
    'bydel':                '4',
    'historisk_bebyggelse': '4',

    # Kategori 5: Administrative enheder
    'suveraen_stat': '5',
    'provins':       '5',
}

NEW_LABELS = {
    '1.1': '1.1 Ferskvand', '1.2': '1.2 Saltvand', '1': '1 Vandområder (uspec.)',
    '2.1': '2.1 Forhøjninger og dale', '2.2': '2.2 Øer', '2.3': '2.3 Øvrige terræner',
    '3.1': '3.1 Verdslige bygninger', '3.2': '3.2 Religiøse bygninger',
    '3.3': '3.3 Anlæg, veje og øvrigt under åben himmel',
    '4': '4 Byer og tæt bebyggede zoner',
    '5': '5 Administrative enheder',
    'usikker': 'USIKKER',
}

# svNames er et separat repo, normalt checket ud som søsterkatalog til
# hca-open-repo. Overstyr med miljøvariablen SVNAMES_PLACES_XML, hvis din
# lokale opsætning afviger.
_here = os.path.dirname(os.path.abspath(__file__))
_places_xml = os.environ.get(
    'SVNAMES_PLACES_XML',
    os.path.join(_here, '..', '..', '..', 'svNames', 'data', 'registers', 'places.xml'),
)
tree = ET.parse(_places_xml)
root = tree.getroot()
places = root.findall('.//tei:place', NS)

new_counter = Counter()
harbor_names = []
garden_park_names = []
waterfall_names = []
uncertain_names = []

for p in places:
    xml_id = p.get('{http://www.w3.org/XML/1998/namespace}id', '')
    geotype = p.get('type')
    main_name_el = p.find('tei:placeName[@type="main"]', NS)
    name = main_name_el.text if main_name_el is not None and main_name_el.text else '(uden navn)'
    note_el = p.find('tei:note', NS)
    note_text = note_el.text if note_el is not None and note_el.text else ''

    top_slug, method, reason = classify_top(xml_id, name, geotype, note_text)
    if top_slug == 'usikker':
        new_counter['usikker'] += 1
        continue

    # Re-derive old §H subgroup (mirrors subgroup_classify.py main loop)
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
        new_counter['usikker'] += 1
        uncertain_names.append(name)
        continue

    new_cat = OLD_TO_NEW.get(sub)
    if new_cat is None:
        new_counter['usikker'] += 1
        uncertain_names.append(f"{name} (subgroup={sub})")
        continue

    new_counter[new_cat] += 1
    if sub == 'bugt_havn':
        harbor_names.append(name)
    if sub in ('bypark', 'have'):
        garden_park_names.append((name, sub, new_cat))
    if sub == 'vandfald':
        waterfall_names.append(name)

total = len(places)
print(f"SV14-registret (n={total}) i den nye §K-taksonomi:\n")
order = ['1.1', '1.2', '2.1', '2.2', '2.3', '3.1', '3.2', '3.3', '4', '5', 'usikker']
for k in order:
    n = new_counter.get(k, 0)
    print(f"  {NEW_LABELS[k]:45s} n={n:3d}  ({n/total*100:.1f}%)")

print(f"\nSamlet kategori 1 (Vandområder): {new_counter.get('1.1',0)+new_counter.get('1.2',0)}")
print(f"Samlet kategori 2 (Landområder): {sum(new_counter.get(k,0) for k in ['2.1','2.2','2.3'])}")
print(f"Samlet kategori 3 (Bygninger/veje/anlæg): {sum(new_counter.get(k,0) for k in ['3.1','3.2','3.3'])}")

print(f"\n--- 'bugt_havn' (havn) -> {len(harbor_names)} poster, rutet til 1.2 ---")
for n in harbor_names:
    print(" ", n)

print(f"\n--- Parker/haver -> {len(garden_park_names)} poster ---")
for n, sub, cat in garden_park_names:
    print(f"  {n} (var {sub} -> nu {cat})")

print(f"\n--- Vandfald -> {len(waterfall_names)} poster (nu 1.1, ingen undtagelse nødvendig) ---")
for n in waterfall_names:
    print(" ", n)
