"""Convert a measured percentage depth dose (PDD) into a depth correction
factor (DCF) referenced to depth d0 at isocentre.

    DCF(d) = [PDD(d) / PDD(d0)] * [(SSD + d) / (SSD + d0)]^2

The ratio term makes the result independent of the PDD's absolute
normalisation; the squared-distance term removes the fixed-SSD geometry baked
into the PDD (design spec section 4.2). SSD and d0 are explicit parameters. depths_cm must be ascending (np.interp
silently returns wrong values otherwise), so this is enforced.
"""
from __future__ import annotations

import numpy as np


def pdd_to_dcf(depths_cm: np.ndarray, pdd_values: np.ndarray,
               ssd_cm: float, d0_cm: float) -> np.ndarray:
    depths = np.asarray(depths_cm, dtype=float)
    pdd = np.asarray(pdd_values, dtype=float)
    if depths.size < 2 or not np.all(np.diff(depths) >= 0):
        raise ValueError("depths_cm must be ascending with at least 2 points")
    pdd_d0 = float(np.interp(d0_cm, depths, pdd))
    if pdd_d0 == 0.0:
        raise ValueError(f"PDD is zero at reference depth d0={d0_cm} cm")
    ratio = pdd / pdd_d0
    inv_sq = ((ssd_cm + depths) / (ssd_cm + d0_cm)) ** 2
    return ratio * inv_sq


def check_reference_consistency(dcf_depths_cm: np.ndarray, dcf_values: np.ndarray,
                                d0_cm: float, tol: float = 1e-4) -> None:
    """Hard gate: d0 must be within the depth range and DCF(d0) must equal 1.

    A DCF that is not exactly 1 at the reference depth, or a d0 outside the
    measured range, indicates a reference-point mismatch that would apply a
    constant percentage offset to every result (design spec section 7).

    tol (default 1e-4, i.e. 0.01%): tolerance for the DCF(d0)==1 check.
    Real scans with 0.1 cm step size produce grid points on either side of
    d0=10.0 cm; linear interpolation then gives DCF(d0) that deviates from 1.0
    by a numerical artifact of up to ~2e-5 in practice (observed across the 9
    Aktina cones) with no clinical significance. The default 1e-4 accommodates
    this while remaining ~100× tighter than any real reference-point mismatch
    (which would be %-level, order 1e-2 or larger).
    """
    depths = np.asarray(dcf_depths_cm, dtype=float)
    if depths.size < 2 or not np.all(np.diff(depths) >= 0):
        raise ValueError("dcf_depths_cm must be ascending with at least 2 points")
    if d0_cm < depths[0] or d0_cm > depths[-1]:
        raise ValueError(
            f"reference depth d0={d0_cm} cm outside measured range "
            f"[{depths[0]}, {depths[-1]}] cm"
        )
    dcf_d0 = float(np.interp(d0_cm, depths, np.asarray(dcf_values, dtype=float)))
    if abs(dcf_d0 - 1.0) > tol:
        raise ValueError(
            f"DCF at d0={d0_cm} cm is {dcf_d0:.6f}, expected 1.0 "
            "(reference-point mismatch)"
        )
