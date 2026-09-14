"""Batch summary CSV — one flat row per plan, projected from PlanCheckResult.

Rejected and Error rows are included (with a reason) so the dataset records what
was NOT checked. Column order is fixed and locked by tests.
"""
from __future__ import annotations

import csv
from pathlib import Path

from conesrs.engine.result import PlanCheckResult

COLUMNS: tuple[str, ...] = (
    "patient_id", "plan_label", "machine", "status",
    "beam_model", "model_version", "model_validated",
    "cones_used", "n_fractions",
    "d_calc_cgy_per_fx", "d_tps_point_cgy_per_fx", "percent_diff",
    "d_tps_sphere_cgy_per_fx", "sphere_diameter_mm", "percent_diff_sphere",
    "mu_consistency", "mean_depth_mm", "reason", "pdf_path",
)


def status_label(result: PlanCheckResult) -> str:
    """ACCEPTED folds to its PASS/REVIEW/ACTION flag; else the raw status."""
    if result.status == "ACCEPTED":
        return result.tolerance_flag or "ACCEPTED"
    return result.status


def result_to_row(result: PlanCheckResult, pdf_path: str = "") -> dict:
    cones = ";".join(str(c) for c in result.cones_used)
    reason = result.reject_reason or result.error_detail or ""
    return {
        "patient_id": result.patient_id or "",
        "plan_label": result.plan_label or "",
        "machine": result.machine or "",
        "status": status_label(result),
        "beam_model": result.model_id,
        "model_version": result.model_version,
        "model_validated": result.model_validated,
        "cones_used": cones,
        "n_fractions": result.n_fractions if result.n_fractions is not None else "",
        "d_calc_cgy_per_fx": result.d_calc_cgy_per_fx,
        "d_tps_point_cgy_per_fx": result.d_tps_cgy_per_fx,
        "percent_diff": result.percent_diff,
        "d_tps_sphere_cgy_per_fx": result.d_tps_sphere_cgy_per_fx,
        "sphere_diameter_mm": result.sphere_diameter_mm,
        "percent_diff_sphere": result.percent_diff_sphere,
        "mu_consistency": result.mu_consistency,
        "mean_depth_mm": result.mean_depth_mm,
        "reason": reason,
        "pdf_path": pdf_path,
    }


def write_summary(rows: list[dict], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
