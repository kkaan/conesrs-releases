"""The engine's output value object — pure data, no I/O or rendering."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanCheckResult:
    status: str                       # "ACCEPTED" | "REJECTED"
    model_id: str
    model_version: str = ""
    model_validated: bool = False
    tolerance_flag: str | None = None       # PASS/REVIEW/ACTION when ACCEPTED
    reject_reason: str | None = None
    d_calc_cgy_per_fx: float | None = None
    d_tps_cgy_per_fx: float | None = None          # trilinear POINT dose @ iso
    percent_diff: float | None = None              # vs point dose — drives the flag
    # Sphere-averaged TPS dose: informational context that mitigates Monte-Carlo
    # point-to-point noise. It does NOT drive the tolerance flag.
    d_tps_sphere_cgy_per_fx: float | None = None
    sphere_diameter_mm: float | None = None
    percent_diff_sphere: float | None = None       # vs sphere dose — informational
    mu_consistency: float | None = None
    cones_used: tuple[float, ...] = ()
    mean_depth_mm: float | None = None
    n_fractions: int | None = None
    warnings: tuple[str, ...] = ()
    # Identifiers (read from the Plan; absent on an ERROR before parse).
    patient_id: str | None = None
    plan_label: str | None = None
    machine: str | None = None
    # Unexpected processing failure detail (status == "ERROR").
    error_detail: str | None = None
    # (gantry_deg, depth_mm) per sampled direction, for the report depth plot.
    depth_profile: tuple[tuple[float, float], ...] = ()
    # Same samples grouped per beam: ((beam_number, ((gantry, depth), ...)), ...).
    depth_profile_by_beam: tuple[tuple[int, tuple[tuple[float, float], ...]], ...] = ()
