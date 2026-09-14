"""Engine orchestrator: matched DICOM set -> PlanCheckResult.

Computes everything per fraction. The independent dose is evaluated at iso via
the Plan 1 seam; the TPS dose is a trilinear point sample of RTDOSE at iso,
divided by the number of fractions (the grid is DoseSummationType=PLAN/total).
"""
from __future__ import annotations

import numpy as np

from conesrs.core.calc import compute_independent_dose
from conesrs.core.dose.beammodel import BeamModel, DepthOutOfRangeError
from conesrs.core.dose.dosecalc import mu_consistency
from conesrs.core.geometry.depth import ArcSpec, sample_arc_angles
from conesrs.core.geometry.structures import select_body_surface
from conesrs.core.geometry.surface import Surface
from conesrs.engine.result import PlanCheckResult
from conesrs.engine.target import select_target_centroid
from conesrs.engine.tolerance import tolerance_flag
from conesrs.engine.validate import (
    check_grid_resolution, check_single_target, resolve_in_scope_beams,
)

TARGET_ISO_TOL_MM = 5.0
SPHERE_DIAMETER_MM = 2.0  # default volume-averaging diameter (mitigates MC noise)


def _gy_total_to_cgy_per_fx(total_gy: float, summation_type: str | None,
                            nfx: int) -> float | None:
    """Reconcile an RTDOSE sample (Gy) onto a per-fraction cGy basis.

    Returns None for an unsupported DoseSummationType so the caller can reject.
    """
    st = (summation_type or "").upper()
    if st == "PLAN":
        return float(total_gy) * 100.0 / nfx   # Gy total course -> cGy per fx
    if st == "FRACTION":
        return float(total_gy) * 100.0          # already per fraction -> cGy per fx
    return None


def _reject(model_id, model, reason, warnings=()) -> PlanCheckResult:
    return PlanCheckResult(status="REJECTED", model_id=model_id,
                           model_version=model.version,
                           model_validated=model.validated, reject_reason=reason,
                           warnings=tuple(warnings))


def _split_by_beam(traces, in_scope, step_deg):
    """Group the flat trace list back into per-beam (gantry, depth) series.

    compute_independent_dose concatenates trace_arc output arc by arc, and
    trace_arc emits exactly len(sample_arc_angles(...)) samples per arc.
    """
    out = []
    pos = 0
    for arc, _cone in in_scope:
        n = len(sample_arc_angles(arc.gantry_start, arc.gantry_stop, arc.rotation,
                                  step_deg, arc.mu))
        chunk = traces[pos:pos + n]
        pos += n
        out.append((int(arc.beam_number),
                    tuple((float(t.gantry), float(t.depth_mm)) for t in chunk)))
    return tuple(out)


def check_plan(plan, structures, dose, model: BeamModel, model_id: str,
               surface: Surface | None = None, step_deg: float = 2.0,
               plan_path: str = "<plan>",
               sphere_diameter_mm: float = SPHERE_DIAMETER_MM) -> PlanCheckResult:
    warnings: list[str] = []
    if not model.validated:
        warnings.append("UNVALIDATED MODEL — results are provisional until a "
                        "physicist validates this beam-data model")

    iso = np.asarray(plan.isocentre, dtype=float)

    # scope: in-scope beams (cone + parked MLC)
    in_scope, rejects = resolve_in_scope_beams(plan.arcs, model, plan_path)
    if not in_scope:
        reason = rejects[0] if rejects else f"{plan_path}: no in-scope cone beams"
        return _reject(model_id, model, reason, warnings)

    # single target near iso
    try:
        centroid = select_target_centroid(structures, iso)
    except ValueError as exc:
        return _reject(model_id, model, f"{plan_path}: {exc}", warnings)
    bad = check_single_target(centroid, iso, TARGET_ISO_TOL_MM)
    if bad:
        return _reject(model_id, model, f"{plan_path}: {bad}", warnings)

    # dose-grid resolution (flag, not reject)
    zsp = float(abs(np.median(np.diff(dose.z_offsets)))) if len(dose.z_offsets) > 1 else 1.0
    grid_warn = check_grid_resolution(dose.row_spacing, dose.col_spacing, zsp)
    if grid_warn:
        warnings.append(grid_warn)

    # body surface (caller may inject one for tests)
    if surface is None:
        try:
            surface = select_body_surface(structures, iso)
        except ValueError as exc:
            return _reject(model_id, model, f"{plan_path}: {exc}", warnings)

    # per-beam ArcSpecs carrying each beam's cone
    arcspecs = [
        ArcSpec(gantry_start=a.gantry_start, gantry_stop=a.gantry_stop,
                rotation=a.rotation, couch=a.couch, total_mu=a.mu,
                cone_size_mm=cone)
        for a, cone in in_scope
    ]
    try:
        core = compute_independent_dose(model, arcspecs, iso, surface, step_deg)
    except (ValueError, DepthOutOfRangeError) as exc:
        return _reject(model_id, model, f"{plan_path}: {exc}", warnings)

    depth_profile = tuple((float(t.gantry), float(t.depth_mm)) for t in core.traces)
    depth_profile_by_beam = _split_by_beam(core.traces, in_scope, step_deg)
    d_calc = core.dose_cgy  # cGy per fraction (arc MU is per fraction)

    # TPS dose at iso, per fraction. The prominent comparison is the trilinear
    # POINT dose; the sphere-averaged dose is supplementary context that tames
    # Monte-Carlo point-to-point noise but does NOT drive the tolerance flag.
    nfx = int(plan.number_of_fractions) or 1
    tps_total_gy = dose.sample_point(iso)
    if np.isnan(tps_total_gy):
        return _reject(model_id, model,
                       f"{plan_path}: isocentre is outside the RTDOSE grid",
                       warnings)
    if tps_total_gy <= 0:
        return _reject(model_id, model,
                       f"{plan_path}: isocentre in a zero-dose region — "
                       "TPS comparison undefined", warnings)
    # Reconcile the RTDOSE dose basis against per-fraction before comparing.
    d_tps = _gy_total_to_cgy_per_fx(tps_total_gy, dose.summation_type, nfx)
    if d_tps is None:
        return _reject(model_id, model,
                       f"{plan_path}: unsupported RTDOSE DoseSummationType "
                       f"{dose.summation_type!r} — cannot reconcile dose basis",
                       warnings)

    # Sphere-averaged dose over the configured diameter (same per-fraction basis).
    sphere_total_gy = dose.sample_sphere(iso, sphere_diameter_mm / 2.0)
    d_tps_sphere = _gy_total_to_cgy_per_fx(sphere_total_gy, dose.summation_type, nfx)
    percent_diff_sphere = (100.0 * (d_calc - d_tps_sphere) / d_tps_sphere
                           if d_tps_sphere else float("nan"))

    percent_diff = 100.0 * (d_calc - d_tps) / d_tps if d_tps else float("nan")
    presc_per_fx_cgy = (plan.prescription_dose_gy or 0.0) * 100.0 / nfx
    muc = mu_consistency(d_calc, presc_per_fx_cgy) if presc_per_fx_cgy else None

    cones = tuple(c for _, c in in_scope)
    flag = tolerance_flag(percent_diff, max(cones))

    return PlanCheckResult(
        status="ACCEPTED", model_id=model_id, model_version=model.version,
        model_validated=model.validated, tolerance_flag=flag,
        d_calc_cgy_per_fx=d_calc, d_tps_cgy_per_fx=d_tps,
        percent_diff=percent_diff,
        d_tps_sphere_cgy_per_fx=d_tps_sphere,
        sphere_diameter_mm=sphere_diameter_mm,
        percent_diff_sphere=percent_diff_sphere,
        mu_consistency=muc, cones_used=cones,
        mean_depth_mm=core.mean_depth_mm, n_fractions=nfx,
        depth_profile=depth_profile,
        depth_profile_by_beam=depth_profile_by_beam,
        warnings=tuple(warnings),
    )
