"""Scope/precondition checks (design spec section 6).

Each function returns either None / data (ok) or a human-readable reason string
carrying file + DICOM-tag provenance where relevant. The orchestrator (check.py)
turns the first failure into a REJECTED PlanCheckResult.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from conesrs.config.machines import MachineConfig, UnknownMachineError
from conesrs.core.dose.beammodel import BeamModel
from conesrs.data.formats import load_beam_data
from conesrs.engine.coneresolve import is_treatment_beam, parse_cone_size_mm
from conesrs.engine.mlc import is_mlc_parked
from conesrs.engine.target import select_target_centroid

# DICOM tag references for provenance messages
_APP_DESC_TAG = "ApplicatorDescription (300A,00C3)"
_APP_ID_TAG = "ApplicatorID (300A,00C7)"
GRID_TOL_MM = 0.05


def resolve_in_scope_beams(arcs, model: BeamModel, plan_path: str):
    """Return (in_scope, rejects).

    in_scope: list of (arc, cone_size_mm) for treatment beams with a resolvable
    cone that exists in the model and a parked MLC.
    rejects: provenance strings for beams excluded as out of scope.
    """
    in_scope = []
    rejects = []
    for arc in arcs:
        if not is_treatment_beam(arc.treatment_delivery_type):
            continue  # setup/imaging beam — silently excluded, not a reject
        size = parse_cone_size_mm(arc.applicator_id, arc.applicator_description)
        if size is None:
            rejects.append(
                f"{plan_path}: beam {arc.beam_number} has no resolvable cone "
                f"({_APP_DESC_TAG}={arc.applicator_description!r}, "
                f"{_APP_ID_TAG}={arc.applicator_id!r})"
            )
            continue
        if arc.mlc is None:
            rejects.append(
                f"{plan_path}: beam {arc.beam_number} has no MLC data — cannot "
                f"confirm the cone aperture is unmodulated (parse the plan "
                f"with_mlc=True)"
            )
            continue
        if not is_mlc_parked(arc.mlc):
            rejects.append(
                f"{plan_path}: beam {arc.beam_number} is MLC-modulated "
                f"(cone {size} mm) — out of scope"
            )
            continue
        try:
            model.resolve_cone(size)
        except KeyError:
            rejects.append(
                f"{plan_path}: cone {size} mm "
                f"({_APP_DESC_TAG}={arc.applicator_description!r}, "
                f"{_APP_ID_TAG}={arc.applicator_id!r}) not in "
                f"model {model.name!r} cones {sorted(model.cones)}"
            )
            continue
        in_scope.append((arc, float(size)))
    return in_scope, rejects


def check_single_target(centroid: np.ndarray, iso: np.ndarray,
                        tol_mm: float = 5.0) -> str | None:
    d = float(np.linalg.norm(np.asarray(centroid, float) - np.asarray(iso, float)))
    if d > tol_mm:
        return (f"target centroid {d:.1f} mm from isocentre "
                f"(> {tol_mm} mm) — off-isocentre/multi-target, out of scope")
    return None


def check_grid_resolution(row_mm: float, col_mm: float, z_mm: float) -> str | None:
    # 1 mm isotropic is the SRS minimum requirement. A coarser grid degrades the
    # iso point-sample accuracy and is flagged; a finer grid exceeds the minimum
    # and is fine, so it must NOT warn.
    if max(row_mm, col_mm, z_mm) > 1.0 + GRID_TOL_MM:
        return (f"dose grid is {row_mm}x{col_mm}x{z_mm} mm, coarser than the 1 mm "
                f"SRS minimum — iso point-sample accuracy degraded")
    return None


@dataclass(frozen=True)
class ValidationIssue:
    severity: str    # "blocker" | "warning"
    message: str     # human-readable, with provenance where relevant
    code: str        # stable machine key, e.g. "cone_not_in_model"


def resolve_model_for_plan(plan, config: MachineConfig):
    """(BeamModel, None) on success; (None, ValidationIssue) if unmappable/unloadable."""
    try:
        model_id = config.model_id_for(plan.machine)
    except UnknownMachineError as exc:
        return None, ValidationIssue("blocker", str(exc), "machine_unmapped")
    try:
        return load_beam_data(config.model_path(model_id)), None
    except Exception as exc:  # noqa: BLE001 - missing/corrupt model file
        return None, ValidationIssue(
            "blocker", f"failed to load model {model_id!r}: {exc!r}", "model_load_failed")


def prevalidate(plan, structures, dose, model) -> list[ValidationIssue]:
    """All statically-detectable precondition failures, aggregated (not first-fail).

    `model` is the resolved BeamModel, or None (machine unmapped / load failed —
    the caller supplies that blocker separately via resolve_model_for_plan). Deep
    checks that need the dose calc (ray-misses-surface, depth-out-of-range) are NOT
    here — they surface when the check is actually run.
    """
    issues: list[ValidationIssue] = []
    iso = np.asarray(plan.isocentre, dtype=float)

    if model is not None:
        in_scope, rejects = resolve_in_scope_beams(plan.arcs, model, "<plan>")
        for r in rejects:
            issues.append(ValidationIssue("blocker", r, "beam_out_of_scope"))
        if not in_scope and not rejects:
            issues.append(ValidationIssue("blocker", "no in-scope cone beam", "no_cone_beam"))
        if not model.validated:
            issues.append(ValidationIssue(
                "warning", "UNVALIDATED MODEL — results are provisional until a "
                "physicist validates this beam-data model", "model_unvalidated"))

    try:
        centroid = select_target_centroid(structures, iso)
        bad = check_single_target(centroid, iso)
        if bad:
            issues.append(ValidationIssue("blocker", bad, "target_off_iso"))
    except ValueError as exc:
        issues.append(ValidationIssue("blocker", str(exc), "no_target"))

    if np.isnan(dose.sample_point(iso)):
        issues.append(ValidationIssue(
            "blocker", "isocentre is outside the RTDOSE grid", "iso_outside_grid"))
    if (dose.summation_type or "").upper() not in {"PLAN", "FRACTION"}:
        issues.append(ValidationIssue(
            "blocker", f"unsupported RTDOSE DoseSummationType {dose.summation_type!r}",
            "bad_summation"))

    zsp = float(abs(np.median(np.diff(dose.z_offsets)))) if len(dose.z_offsets) > 1 else 1.0
    grid_warn = check_grid_resolution(dose.row_spacing, dose.col_spacing, zsp)
    if grid_warn:
        issues.append(ValidationIssue("warning", grid_warn, "grid_coarse"))

    return issues
