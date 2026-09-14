"""Headless orchestration: matched PlanSet -> PlanCheckResult, and batch runs.

check_plan_set is the shared single-plan pipeline used by both CLI subcommands:
parse the DICOM set, resolve+load the beam model from config, run check_plan.
Expected scope failures return REJECTED (from check_plan or an unmapped machine);
unexpected processing failures (corrupt files) return an ERROR result so a batch
never aborts on one bad plan.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from conesrs.config.machines import MachineConfig, UnknownMachineError
from conesrs.core.dose.beammodel import BeamModel
from conesrs.data.formats import load_beam_data
from conesrs.dicomio.matching import PlanSet, match_folder
from conesrs.dicomio.rtdose import parse_rtdose
from conesrs.dicomio.rtplan import parse_rtplan
from conesrs.dicomio.rtstruct import parse_rtstruct
from conesrs.engine.check import check_plan
from conesrs.engine.result import PlanCheckResult
from conesrs.report.csv import result_to_row, write_summary
from conesrs.report.pdf import write_pdf


def _error(detail: str, model_id: str = "") -> PlanCheckResult:
    return PlanCheckResult(status="ERROR", model_id=model_id, error_detail=detail)


def check_plan_set(planset: PlanSet, config: MachineConfig, *,
                   sphere_diameter_mm: float = 2.0,
                   model_cache: dict[str, BeamModel] | None = None
                   ) -> PlanCheckResult:
    cache = model_cache if model_cache is not None else {}
    label = str(planset.plan_path) if planset.plan_path is not None else "<no plan path>"

    if planset.plan_path is None or planset.struct_path is None:
        return PlanCheckResult(status="REJECTED", model_id="",
                               reject_reason=f"{label}: incomplete set "
                               "(missing RTPLAN or RTSTRUCT)")
    if planset.dose_path is None:
        return PlanCheckResult(status="REJECTED", model_id="",
                               reject_reason=f"{label}: no RTDOSE — TPS "
                               "comparison source absent (BeamDose fallback not "
                               "implemented in v1)")

    # Parse (unexpected failures => ERROR, never a crash).
    try:
        plan = parse_rtplan(planset.plan_path, with_mlc=True)
        struct = parse_rtstruct(planset.struct_path)
        dose = parse_rtdose(planset.dose_path)
    except Exception as exc:  # noqa: BLE001 - corrupt/unreadable input
        return _error(f"{label}: failed to parse DICOM set: {exc!r}")

    # Resolve + load the beam model (unmapped machine => REJECTED).
    try:
        model_id = config.model_id_for(plan.machine)
    except UnknownMachineError as exc:
        return PlanCheckResult(status="REJECTED", model_id="",
                               reject_reason=f"{label}: {exc}",
                               patient_id=plan.patient_id,
                               plan_label=plan.plan_label, machine=plan.machine)
    try:
        if model_id not in cache:
            cache[model_id] = load_beam_data(config.model_path(model_id))
        model = cache[model_id]
    except Exception as exc:  # noqa: BLE001 - missing/corrupt model file
        return _error(f"{label}: failed to load model {model_id!r}: {exc!r}",
                      model_id)

    # Run the check, then enrich with identifiers from the plan.
    try:
        result = check_plan(plan, struct.structures, dose, model, model_id,
                            sphere_diameter_mm=sphere_diameter_mm,
                            plan_path=label)
    except Exception as exc:  # noqa: BLE001 - defensive; check_plan rejects, not raises
        return _error(f"{label}: check failed: {exc!r}", model_id)

    return dataclasses.replace(result, patient_id=plan.patient_id,
                               plan_label=plan.plan_label, machine=plan.machine)


_STATUSES = ("PASS", "REVIEW", "ACTION", "REJECTED", "ERROR")


@dataclass(frozen=True)
class BatchSummary:
    counts: dict[str, int]
    rows: tuple[dict, ...]
    csv_path: Path
    skip_log_path: Path
    out_dir: Path


def _status_label(result: PlanCheckResult) -> str:
    if result.status == "ACCEPTED":
        return result.tolerance_flag or "ACCEPTED"
    return result.status


def _pdf_name(result: PlanCheckResult, index: int) -> str:
    pid = (result.patient_id or "plan").replace(" ", "_")
    lab = (result.plan_label or str(index)).replace(" ", "_")
    return f"{pid}_{lab}_{index}.pdf"


def run_batch(folder, config: MachineConfig, out_dir, *,
              sphere_diameter_mm: float = 2.0, timestamp: str = "") -> BatchSummary:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {s: 0 for s in _STATUSES}
    rows: list[dict] = []
    skips: list[str] = []
    cache: dict[str, BeamModel] = {}

    for i, planset in enumerate(match_folder(folder)):
        result = check_plan_set(planset, config,
                                sphere_diameter_mm=sphere_diameter_mm,
                                model_cache=cache)
        label = _status_label(result)
        counts[label] = counts.get(label, 0) + 1

        pdf_path = ""
        if result.status == "ACCEPTED":
            pdf_file = out_dir / _pdf_name(result, i)
            try:
                write_pdf(result, pdf_file, timestamp=timestamp)
                pdf_path = str(pdf_file)
            except Exception as exc:  # noqa: BLE001 - a render failure must not abort the batch
                skips.append(f"[PDF-ERROR] {_pdf_name(result, i)}: {exc!r}")
        else:
            skips.append(f"[{label}] {result.reject_reason or result.error_detail}")
        rows.append(result_to_row(result, pdf_path=pdf_path))

    csv_path = out_dir / "summary.csv"
    write_summary(rows, csv_path)
    skip_log_path = out_dir / "skipped.txt"
    skip_log_path.write_text("\n".join(skips) + ("\n" if skips else ""),
                             encoding="utf-8")
    return BatchSummary(counts=counts, rows=tuple(rows), csv_path=csv_path,
                        skip_log_path=skip_log_path, out_dir=out_dir)
