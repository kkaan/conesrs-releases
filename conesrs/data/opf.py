"""Parser for the cone output-factor table.

Layout: a header row whose first cell is a label and remaining cells are cone
sizes (mm); one data row whose first cell is a label (e.g. "OPF poly") and whose
remaining cells are the output factors aligned with the header sizes.

Tab- and comma-delimited files are both accepted (the Aktina export is CSV, the
Elekta export is tab-separated). Cone sizes are kept as floats — Elekta has
non-integer cones (7.5, 12.5, 17.5 mm) that must not be truncated to int.
"""
from __future__ import annotations

import csv
from pathlib import Path


def parse_opf_csv(path: str | Path) -> dict[float, float]:
    lines = [ln for ln in Path(path).read_text(encoding="utf-8-sig").splitlines()
             if ln.strip()]
    if len(lines) < 2:
        raise ValueError("OPF table needs a header row and at least one data row")
    delimiter = "\t" if "\t" in lines[0] else ","
    rows = list(csv.reader(lines, delimiter=delimiter))
    sizes = [float(c) for c in rows[0][1:]]
    values = rows[1][1:]
    if len(values) != len(sizes):
        raise ValueError(
            f"OPF row has {len(values)} values for {len(sizes)} cone sizes"
        )
    return {size: float(v) for size, v in zip(sizes, values)}
