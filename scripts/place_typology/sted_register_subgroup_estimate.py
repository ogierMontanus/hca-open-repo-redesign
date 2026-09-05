#!/usr/bin/env python3
"""Zero-shot name-pattern estimate of the 33 §H subgroup distribution against
the 2508-place STED-REGISTER, following the same methodology as §E's
top-level 6-category test. Patterns are ordered by specificity/reliability;
first match wins. Default (no match) = bebygget / uspecificeret."""
import csv, re
from collections import Counter

CLOSED_LISTS = {
    'suveraen_stat': [
        'Danmark', 'Sverige', 'Norge', 'Tyskland', 'Italien', 'Frankrig', 'Spanien',
        'Portugal', 'Holland', 'Nederlandene', 'Belgien', 'Schweiz', 'Østrig',
        'Grækenland', 'Tyrkiet', 'Rusland', 'England', 'Irland', 'Skotland',
        'Ungarn', 'Rumænien', 'Bulgarien', 'Serbien', 'Polen', 'Finland',
        'Island', 'USA', 'Amerika', 'Malta', 'Egypten',
    ],
    'kontinent': ['Europa', 'Asien', 'Afrika', 'Amerika', 'Australien', 'Antarktis'],
    'landskabsregion': [
        'Tyrol', 'Slesvig', 'Holsten', 'Böhmen', 'Bøhmen', 'Sachsen', 'Bayern',
        'Preussen', 'Peloponnes', 'Toscana', 'Provence', 'Andalusien', 'Katalonien',
        'Wallakiet', 'Moldau', 'Bessarabien', 'Siebenbürgen', 'Istrien', 'Dalmatien',
    ],
}

# (subgroup, top_category, [regex patterns], is_word_boundary)
PATTERNS = [
    # --- Kategori 3: vand (highest reliability per §E) ---
    ('straede_sund', 'vand', [r'\bstrædet?\b', r'\bsund\b', r'-sund$', r'\bstrait\b', r'\bBosporus\b', r'\bDardaneller']),
    ('bugt_havn', 'vand', [r'\bbugt(en)?$', r'-bugt', r'\bhavn(en)?$', r'-havn$', r'\bbay\b', r'\bharbour\b', r'\bharbor\b', r'\bgolf(o)?$']),
    # NB: kræver et ordskel (mellemrum/bindestreg) foran "Sø" med stort S,
    # for at undgå falske positiver på ø-navne, der tilfældigvis ender på
    # bogstaverne "sø" uden mellemrum (fx "Agersø" er en ø, ikke en sø) --
    # fundet ved selvkritisk stikprøve, se kommentar i place-typology.md.
    ('soe', 'vand', [r'[\s-]Sø(en)?$', r'\blago\b', r'\blac\b', r'-see$', r'\bsee\b']),
    ('hav', 'vand', [r'-?havet$', r'\bhavet\b', r'\bsea\b', r'\bmare\b']),
    ('vandloeb', 'vand', [r'-?[Åå]en$', r'-?[Aa]a(en)?$', r'\belv(en)?$', r'-flod(en)?$', r'\bfluss\b', r'\bfiume\b', r'\bkanal(en)?$', r'\bcanal\b']),

    # --- Kategori 4: landskab ---
    ('vandfald', 'landskab', [r'\bfald(ene|et)?$', r'-fald$', r'\bcascata\b', r'\bwaterfall\b', r'fossen$']),
    ('vulkan', 'landskab', [r'\bvulkan\b', r'\bvolcano\b', r'\bVesuv', r'\bÆtna\b', r'\bEtna\b', r'\bStromboli\b']),
    ('grotte', 'landskab', [r'\bgrotte(n|r)?\b', r'\bgrotta\b', r'\bhøhle\b', r'\bhule(n)?$', r'\bcave\b']),
    ('kloeft_dal', 'landskab', [r'-?dal(en)?$', r'-tal$', r'\bkløft(en)?$', r'\bgorge\b']),
    ('klippe', 'landskab', [r'\bklint(en)?$', r'-klint$', r'\bklippe(n|r)?\b', r'\bfels(en)?\b']),
    ('forbjerg', 'landskab', [r'^[Kk]ap\s', r'\bcape\b', r'\bcapo\b', r'-næs$', r'\bnæs(et)?$', r'\bpunta\b']),
    ('pas', 'landskab', [r'-pas(set)?$', r'\bpass\b', r'\bpasso\b']),
    # Bare "-ø" uden bindestreg tælles også med (fx "Agersø", "Femø") --
    # dansk øe-navngivning fuser typisk direkte uden bindestreg, i modsætning
    # til "-Sø" (sø), som kræver ordskel foran (se soe-mønsteret ovenfor).
    ('oe', 'landskab', [r'ø(en)?$', r'\bisola\b', r'\bîle\b', r'\binsel\b', r'\bisland\b']),
    ('bjerg', 'landskab', [r'-bjerg(et|ene)?$', r'-fjeld(et)?$', r'^[Mm]onte\s', r'^[Mm]ont\s', r'\bmountain\b']),

    # --- Kategori 5: anlaeg ---
    ('religioes_bygning', 'anlaeg', [r'\bkirke(n)?$', r'-kirke$', r'\bkirche\b', r'\bchiesa\b', r'\bdom(en)?$', r'\bkloster(et)?$', r'\bmoské(en)?$', r'\bmosque\b', r'\bkatedral', r'\bbasilika\b']),
    ('slot_borg', 'anlaeg', [r'\bslot(tet)?$', r'-slot$', r'\bschloss\b', r'\bborg(en)?$', r'-borg$', r'\bburg\b', r'\bpalads(et)?$', r'\bpalazzo\b', r'\bpalace\b', r'\bcastello\b', r'\bcastle\b']),
    ('kulturinstitution', 'anlaeg', [r'\bteater(et)?$', r'\btheater\b', r'\bteatro\b', r'\bmuseum\b', r'\bmuseo\b', r'\bopera(en)?\b']),
    ('fortidsminde', 'anlaeg', [r'\bruin(en)?$', r'\bmonument(et)?$', r'\bgrav(en)?$', r'\btomb\b', r'\bmindesmærke']),
    ('infrastruktur', 'anlaeg', [r'\btorv(et)?$', r'-torv$', r'\bplads(en)?$', r'\bplatz\b', r'\bpiazza\b', r'^[Vv]ia\s', r'\bgade(n)?$', r'-gade$', r'\bstraße\b', r'\bbro(en)?$', r'-bro$', r'\bbrücke\b', r'\bponte\b', r'\brådhus(et)?$']),

    # --- Kategori 6: park ---
    ('bypark', 'park', [r'\bhave(n)?$', r'-have$', r'\bpark(en)?$', r'-park$', r'\bgarten\b', r'\bgiardino\b']),
    ('skov', 'park', [r'\bskov(en)?$', r'-skov$']),

    # --- Kategori 2: admreg (closed lists checked separately, but also allow suffix cues) ---
    ('provins', 'admreg', [r'\bprovins(en)?$', r'\bprovince\b']),
]


def classify_sted(label: str):
    name = label.strip()
    # 1) Closed lists (highest confidence, exact match on cleaned name)
    cleaned = re.sub(r'\s*\([^)]*\)\s*', '', name).strip()
    for sub, names in CLOSED_LISTS.items():
        if cleaned in names:
            top = 'admreg'
            return top, sub, 'closed-list'
    # 2) Regex patterns, in priority order. "soe" is matched case-sensitively
    # (no IGNORECASE) so the capital-S "Sø" boundary requirement actually
    # excludes lowercase "-sø" island-name endings like "Agersø".
    for sub, top, pats in PATTERNS:
        for pat in pats:
            flags = 0 if sub == 'soe' else re.IGNORECASE
            if re.search(pat, name, flags):
                return top, sub, f'pattern:{pat}'
    # 3) Default
    return 'bebygget', 'uspecificeret', 'default'


def main():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    entities_csv = os.path.join(here, '..', '..', 'data', 'normalized', 'entities.csv')
    rows = []
    with open(entities_csv, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r['entity_type'] == 'place' and r['category_h1'] == 'STED-REGISTER':
                rows.append(r)

    def is_xref(label):
        return bool(re.search(r',\s*se:?\s', label, re.IGNORECASE)) or 'se sagregistret' in label.lower()

    main_rows = [r for r in rows if not is_xref(r['label'])]

    top_counter = Counter()
    sub_counter = Counter()
    examples = {}
    results = []
    for r in main_rows:
        top, sub, method = classify_sted(r['label'])
        top_counter[top] += 1
        sub_counter[sub] += 1
        examples.setdefault(sub, []).append(r['label'])
        results.append((r['label'], top, sub, method))

    n = len(main_rows)
    print(f"Total classifiable (excl. cross-refs): {n}\n")
    print("=== Top-level (6 kategorier) ===")
    for top, c in top_counter.most_common():
        print(f"  {top:10s} n={c:4d}  ({c/n*100:.1f}%)")

    print("\n=== Finkategori (33 undergrupper) ===")
    for sub, c in sorted(sub_counter.items(), key=lambda x: -x[1]):
        ex = ', '.join(examples[sub][:4])
        print(f"  {sub:22s} n={c:4d}  ({c/n*100:.1f}%)  e.g. {ex}")

    return results


if __name__ == '__main__':
    results = main()
    import pickle
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'sted_register_results.pkl'), 'wb') as f:
        pickle.dump(results, f)
