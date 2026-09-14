"""Factor-based dose sum (TG-71 / TG-219 formalism).

Dosimetry side of the seam. Imports the beam model only; no geometry imports.
"""
from __future__ import annotations

from dataclasses import dataclass

from conesrs.core.dose.beammodel import BeamModel


@dataclass(frozen=True)
class DoseSample:
    """One sampled beam direction: MU, depth to iso, and this beam's cone size."""

    mu: float
    depth_mm: float
    cone_size_mm: float


def compute_dose(model: BeamModel, samples: list[DoseSample]) -> float:
    """D_calc = sum_i [ MU_i * D_ref * OF(c_i) * DCF(c_i, d_i) ], OAR_i = 1.

    Each sample carries its own cone size, so a plan may mix cone sizes.
    """
    total = 0.0
    for s in samples:
        depth_cm = s.depth_mm / 10.0
        of = model.output_factor(s.cone_size_mm)
        total += s.mu * model.d_ref * of * model.dcf(s.cone_size_mm, depth_cm)
    return total


def mu_consistency(d_calc: float, prescribed_dose: float) -> float:
    """Ratio of planned MU to the MU that reproduces the prescribed dose.

    Since D_calc is produced by the planned MU, the MU that would deliver the
    prescribed dose is planned_MU * prescribed / D_calc, so the ratio reduces
    to D_calc / prescribed.
    """
    return d_calc / prescribed_dose
