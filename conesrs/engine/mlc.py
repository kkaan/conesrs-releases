"""Decide whether a beam's MLC is parked (cone plan) or modulated (out of scope).

A cone beam leaves the MLC static; a modulated beam moves leaves between control
points. We call it parked iff the maximum per-leaf travel between consecutive
control points is <= PARKED_TRAVEL_MM. The threshold separates the known sample
plans (Aktina cone plans are exactly static; the MLC plan moves leaves several
mm per step) and is locked by the tests above.
"""
from __future__ import annotations

import numpy as np

PARKED_TRAVEL_MM = 0.5


def is_mlc_parked(mlc, parked_travel_mm: float = PARKED_TRAVEL_MM) -> bool:
    """True if leaves do not move across control points. False if mlc is None.

    Any non-finite (NaN / Inf) leaf position causes an immediate False so
    the safety gate never silently treats corrupt data as parked.
    """
    if mlc is None or len(mlc) < 1:
        return False
    arrs = [np.asarray(cp, dtype=float) for cp in mlc]
    # Reject any control point containing non-finite values.
    for arr in arrs:
        if not np.all(np.isfinite(arr)):
            return False
    if len(arrs) == 1:
        return True  # single control point -> nothing moves
    for prev, cur in zip(arrs[:-1], arrs[1:]):
        if prev.shape != cur.shape:
            return False
        if float(np.max(np.abs(cur - prev))) > parked_travel_mm:
            return False
    return True
