"""Shared utilities for the register parsers.

Each parser in this folder reads a slice of the canonical workbook
`data/raw/HCA REPOSITORY V*/HCA-Repository V*.xlsx`, filters it by
RegistryCategory / WorkGenre / RegistryForm to isolate one printed-register
section, and emits a structured TSV. The functions here handle the parts that
are common to all parsers: resolving the highest-version workbook under
`data/raw/`, loading the Registry sheet, and extracting a 2-column slice in
the shape parsers expect.
"""

from __future__ import annotations

import pathlib
import re
from typing import Iterator

import openpyxl


WORKBOOK_PATTERN = re.compile(r"^HCA-Repository V(\d+(?:\.\d+)?)\.xlsx$")


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = ROOT / "data" / "raw"


def resolve_ground_truth_xlsx(
    raw_dir: pathlib.Path | str | None = None,
) -> pathlib.Path:
    """Return the highest-version `HCA-Repository V*.xlsx` file under `raw_dir`.

    The version embedded in the filename (e.g. `V0.82`) increments over time.
    Pick the highest by numeric comparison so the pipeline adapts automatically
    when a new version lands. Raises FileNotFoundError if no matching file is
    present.

    `raw_dir` defaults to `data/raw/`, and the search descends one level so a
    workbook shipped inside its release folder ("HCA REPOSITORY V0.82/") is
    found as readily as one lying loose in the directory itself.
    """
    raw_path = pathlib.Path(raw_dir) if raw_dir is not None else DEFAULT_RAW_DIR
    candidates: list[tuple[float, pathlib.Path]] = []
    for pattern in ("HCA-Repository V*.xlsx", "*/HCA-Repository V*.xlsx"):
        for p in raw_path.glob(pattern):
            m = WORKBOOK_PATTERN.match(p.name)
            if m:
                candidates.append((float(m.group(1)), p))
    if not candidates:
        raise FileNotFoundError(
            f"No HCA-Repository V*.xlsx workbook found in {raw_path.resolve()}"
        )
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def load_registry_slice(
    xlsx_path: pathlib.Path,
    *,
    category: str | None = None,
    genre: str | None = None,
    form: str | None = None,
    subform: str | None = None,
) -> list[tuple[str, str]]:
    """Load the Registry sheet, filter by category/genre/form/subform, return
    `(RegistryTitle, PKRegistryTitelID)` tuples in sheet order.

    Any filter left as None matches anything (including blank cells).
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Registry"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)

    idx_id = header.index("PKRegistryTitelID")
    idx_title = header.index("RegistryTitle")
    idx_cat = header.index("RegistryCategory (H1)")
    idx_gen = header.index("WorRegSubCat.WorkGenre (H2)")
    idx_form = header.index("WorRegSubCat.RegistryForm (H3)")
    idx_sub = header.index("WorRegSubCat.WorkSubForm (H4)")

    out: list[tuple[str, str]] = []
    for row in rows:
        if not row or row[idx_id] is None:
            continue
        if category is not None and row[idx_cat] != category:
            continue
        if genre is not None and row[idx_gen] != genre:
            continue
        if form is not None and row[idx_form] != form:
            continue
        if subform is not None and row[idx_sub] != subform:
            continue
        title = row[idx_title]
        if title is None or not str(title).strip():
            continue
        out.append((str(title), str(row[idx_id])))
    return out


def iter_slice_as_csvrows(slice_rows: list[tuple[str, str]]) -> Iterator[list[str]]:
    """Yield each row as a 2-column list, matching the shape that the
    original parsers expected from a TSV input (Row Labels, RegistryTitelID).
    Header is yielded first."""
    yield ["Row Labels", "RegistryTitelID"]
    for title, reg_id in slice_rows:
        yield [title, reg_id]
