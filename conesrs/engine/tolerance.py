"""Tolerance bands on the percentage dose difference (design spec section 9).

Keyed to the largest cone aperture used in the plan. The <=10 mm action limit is
provisional (finalised from the validation cohort) and set wide here.
"""
from __future__ import annotations

# (review_pct, action_pct) by cone band
_LARGE = (3.0, 5.0)            # aperture > 10 mm
_SMALL = (5.0, 8.0)            # aperture <= 10 mm (action provisional)
_SMALL_CONE_MM = 10.0


def tolerance_flag(percent_diff: float, max_cone_mm: float) -> str:
    review, action = _SMALL if max_cone_mm <= _SMALL_CONE_MM else _LARGE
    mag = abs(percent_diff)
    if mag <= review:
        return "PASS"
    if mag <= action:
        return "REVIEW"
    return "ACTION"


def tolerance_bands(max_cone_mm: float) -> tuple[float, float]:
    """(review_pct, action_pct) applied to a plan whose largest cone is ``max_cone_mm``."""
    return _SMALL if max_cone_mm <= _SMALL_CONE_MM else _LARGE


def action_limit_is_provisional(max_cone_mm: float) -> bool:
    return max_cone_mm <= _SMALL_CONE_MM
