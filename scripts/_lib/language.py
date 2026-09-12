"""
language.py
-----------
The project's language set for `lingua`, and the one remap that goes with it.

Two scripts detect language over register titles, and they are deliberately
*not* merged — their policies differ for good reason:

  enrichment/detect_work_language.py   the production stage. Takes the
      register's own statement first where the editors made one, and only
      then guesses; guards the guess with a confidence floor, a minimum
      title length, and a cue rescue. Timid on purpose: register titles are
      short, and short strings are where detection fails — bare top-1 puts
      "Der Improvisator" in Italian and "Improvisatoren" in Dutch.

  parsers/add_language_column.py       a hand-run CLI that appends columns
      to any parsed TSV. Bare top-1, no guards, no precedence layer.

What they genuinely share is this: the eleven languages that occur in these
registers, and the decision to fold Bokmål into Danish. That is what lives
here. Merging the policies would either blunt the careful one or bloat the
simple one.

The language list is not a default — it is a restriction. Leaving lingua's
full set enabled lets a two-word Danish title land in Tagalog.
"""

# Bokmål is detected separately by lingua but folded to Danish on the way
# out: written Bokmål and 19th-century Danish are near-identical for
# cataloguing, and both route to REX/KB for OPAC lookup.
REMAP = {"nb": "da"}

LANGUAGE_NAMES = [
    "DANISH", "BOKMAL", "GERMAN", "SWEDISH", "FRENCH", "DUTCH",
    "ENGLISH", "ITALIAN", "LATIN", "SPANISH", "PORTUGUESE",
]


def languages():
    """The lingua Language members this project detects over.

    Raises ImportError if lingua is absent — callers that must degrade
    gracefully should use build_detector(), which returns None instead.
    """
    from lingua import Language
    return [getattr(Language, n) for n in LANGUAGE_NAMES]


def build_detector(preload: bool = False):
    """A lingua detector over `languages()`, or None when lingua is absent.

    `preload` loads the models eagerly — worth it for the production stage,
    which detects over thousands of titles in one run, and not worth it for
    a one-shot CLI. It changes start-up cost only, never the result.
    """
    try:
        from lingua import LanguageDetectorBuilder
    except ImportError:
        return None
    builder = LanguageDetectorBuilder.from_languages(*languages())
    if preload:
        builder = builder.with_preloaded_language_models()
    return builder.build()


def to_iso(code: str) -> str:
    """Apply the project's remap to a detected ISO 639-1 code."""
    return REMAP.get(code, code)
