"""Resolve a cone size (mm) from raw applicator labels, model-agnostically.

Aktina puts the size in ApplicatorDescription ("STEREOTACTIC CONE 09.00 mm");
Elekta puts it in ApplicatorID ("7.50 mm"). We scan the description first, then
the id, for the first "<number> mm" token. No match -> None (not a cone beam).
"""
from __future__ import annotations

import re

_SIZE_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)


def parse_cone_size_mm(applicator_id: str, applicator_description: str) -> float | None:
    for text in (applicator_description or "", applicator_id or ""):
        m = _SIZE_MM.search(text)
        if m:
            return float(m.group(1))
    return None


def is_treatment_beam(treatment_delivery_type: str) -> bool:
    """A setup/imaging field is excluded; an empty type defaults to treatment."""
    t = (treatment_delivery_type or "").upper()
    return t in ("", "TREATMENT")
