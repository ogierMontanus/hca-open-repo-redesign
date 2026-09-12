# Curation passes

Human-driven passes that are **not pipeline stages** and are deliberately not
in `run_pipeline.py`. What they share is the thing that makes them awkward:

> **They read the publication repository's *built* output**, not this
> repository's prepared data.

`parse_person_role.py` and `wikidata_lookup.py` both read
`mockup/data/*-extra.js` — the JS cards `hca-open-repo` generates. So they can
only run against a built checkout, they invert the normal direction of the
dependency, and they cannot run in CI here.

They resolve it through `HCA_MOCKUP_DATA_DIR`, defaulting to a sibling
`../hca-open-repo/mockup/data`:

```
HCA_MOCKUP_DATA_DIR=../hca-open-repo/mockup/data \
    python scripts/curation/parse_person_role.py
```

Their outputs are committed, so nothing in the automated flow waits on them.
Run them deliberately, when the thing they enrich has changed.

They are grouped here rather than left among the register parsers so that the
cross-repo dependency is visible in the directory layout instead of only in a
docstring. See [`../../docs/interface.md`](../../docs/interface.md).
