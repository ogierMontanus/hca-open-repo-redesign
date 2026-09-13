# Applied segmentation passes — archive

**Already applied. Do not run.** See [`../README.md`](../README.md) for why
they cannot be replayed and what the file they produced is worth.

Each pass mutated `data/parsed/personregister_xi_parsed.tsv` in place, once,
in a human-reviewed session. Running one now would apply it a second time to a
file it has already changed.

| Kind | Count | What it did |
|---|---:|---|
| `suggest_*` | 7 | wrote a review file to `data/review/` for a person to read |
| `apply_*` | 6 | applied the decisions they approved. (`apply_person_emendations.py` is **not** here — it validates and emits, and lives one level up) |
| `split_*` | 4 | separated named entries the OCR had fused |
| `merge_*` | 3 | folded duplicates and manual corrections back in |
| `fix_*` | 2 | one-off corrections (diacritics from the workbook, three fusion remnants) |
| `dedupe_*`, `link_*`, `import_*`, `harvest_*`, `calibrate_*`, `clean_*`, `refine_*`, `remove_*` | 8 | the rest: the 958-person import, the two duplicate sweeps, the dash-subentry relinking, description re-segmentation |

The order they ran in, the reasoning, and the known weaknesses are in
[`../../../docs/person-register-segmentation.md`](../../../docs/person-register-segmentation.md).

Two of those weaknesses now have a check where they had none:
`scripts/validation/compare_to_reference.py` measures coverage against the
independent transcription and scans for the duplicate class the session found
only by hand.
