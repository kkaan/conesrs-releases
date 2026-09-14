"""Faithful parser for RFA300 ASCII (.asc) water-tank measurement dumps.

Returns structured Measurement records and interprets nothing about depth or
cone identity — that interpretation is a physicist-confirmed build step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_MEAS = re.compile(r"#\s*Measurement number\s+(\d+)")
_TAG = re.compile(r"^%(\S+)[ \t]+(.*?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Measurement:
    """One water-tank scan: header tags plus its (X, Y, Z, Dose) points."""

    index: int
    scan_type: str        # %SCN, e.g. "DPT" (depth) or "PRO" (profile)
    field_size_mm: float  # first value of %FSZ
    ssd_mm: float         # %SSD
    energy_mv: float      # numeric part of %BMT (e.g. "PHO 6.0" -> 6.0)
    tags: dict            # all raw % tags (value comments stripped)
    points: np.ndarray    # (N, 4) columns X, Y, Z, Dose


def _parse_tags(block: str) -> dict:
    tags = {}
    for key, val in _TAG.findall(block):
        tags[key] = re.split(r"\s#", val)[0].strip()
    return tags


def _parse_points(block: str) -> np.ndarray:
    rows = []
    for line in block.splitlines():
        if not line.startswith("="):
            continue
        parts = line.split()
        nums = parts[1:]
        if len(nums) < 4:
            raise ValueError(
                f"malformed data line (expected >=4 values X Y Z Dose): {line!r}"
            )
        rows.append([float(x) for x in nums[:4]])
    if not rows:
        return np.empty((0, 4), dtype=float)
    return np.array(rows, dtype=float)


def parse_asc(path: str | Path) -> list[Measurement]:
    text = Path(path).read_text(encoding="latin-1")
    matches = list(_MEAS.finditer(text))
    out: list[Measurement] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        tags = _parse_tags(block)
        scan_type = tags.get("SCN", "").split()[0] if tags.get("SCN") else ""
        fsz = tags.get("FSZ", "")
        field_size_mm = float(fsz.split()[0]) if fsz else float("nan")
        ssd_mm = float(tags["SSD"]) if "SSD" in tags else float("nan")
        bmt = tags.get("BMT", "").split()
        energy_mv = float(bmt[-1]) if bmt else float("nan")
        out.append(Measurement(
            index=int(m.group(1)),
            scan_type=scan_type,
            field_size_mm=field_size_mm,
            ssd_mm=ssd_mm,
            energy_mv=energy_mv,
            tags=tags,
            points=_parse_points(block),
        ))
    return out
