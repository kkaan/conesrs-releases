"""Measured beam-data model: output factors and depth-correction interpolation.

This module is on the dosimetry side of the geometry/dosimetry seam. It must
never import anything from conesrs.core.geometry.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_CONE_TOL_MM = 0.05  # tolerant cone-size match (Elekta has 7.5/12.5 mm cones)


class DepthOutOfRangeError(ValueError):
    """Raised when a requested depth is outside the measured DCF range."""


@dataclass(frozen=True, eq=False)
class ConeData:
    """Measured data for a single cone size (size in mm, may be non-integer)."""

    size_mm: float
    output_factor: float
    dcf_depths_cm: np.ndarray  # ascending, includes 10.0
    dcf_values: np.ndarray     # DCF(10) == 1.0 by construction


@dataclass(frozen=True, eq=False)
class BeamModel:
    """A versioned set of measured cone data for one beam model."""

    name: str
    version: str
    d_ref: float          # reference absorbed dose per MU (cGy/MU) at ref depth at iso
    ssd_cm: float         # SSD at which PDDs were measured — read from scan header
    cones: dict[float, ConeData]
    ref_depth_cm: float = 10.0   # PDD normalisation depth — read from scan header
    validated: bool = False
    validated_by: str = ""
    validated_date: str = ""

    def resolve_cone(self, size_mm: float) -> ConeData:
        """Return the ConeData whose size matches within _CONE_TOL_MM, else KeyError."""
        best = None
        best_err = _CONE_TOL_MM
        for cone in self.cones.values():
            err = abs(float(cone.size_mm) - float(size_mm))
            if err <= best_err:
                best, best_err = cone, err
        if best is None:
            raise KeyError(
                f"cone {size_mm} mm not in model {self.name!r} "
                f"(cones {sorted(self.cones)})"
            )
        return best

    def output_factor(self, size_mm: float) -> float:
        return self.resolve_cone(size_mm).output_factor

    def dcf(self, size_mm: float, depth_cm: float) -> float:
        cone = self.resolve_cone(size_mm)
        lo, hi = cone.dcf_depths_cm[0], cone.dcf_depths_cm[-1]
        if np.isnan(depth_cm) or depth_cm < lo or depth_cm > hi:
            raise DepthOutOfRangeError(
                f"depth {depth_cm:.2f} cm outside measured range "
                f"[{lo:.2f}, {hi:.2f}] for cone {cone.size_mm} mm"
            )
        return float(np.interp(depth_cm, cone.dcf_depths_cm, cone.dcf_values))
