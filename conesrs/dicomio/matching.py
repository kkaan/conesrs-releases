"""Group loose DICOM files into checkable (plan, struct, dose) sets.

Matching is by DICOM reference UIDs, not filenames: RTDOSE references its RTPLAN,
and RTPLAN references its RTSTRUCT. A folder with several plans sharing one
structure set resolves into one PlanSet per plan.

Real-data fallback: in multi-met SRS exports each plan is often saved with its
own RTSTRUCT *instance*, but only the last structure set is actually exported to
the folder, so plans 1..n-1 reference a struct UID that has no file on disk.
Those plans still share the structure's FrameOfReferenceUID, so when the exact
RTPLAN->RTSTRUCT UID match misses we fall back to the unique RTSTRUCT in the
plan's Frame of Reference. This stays reference-based (FoR is a DICOM reference),
never filename-based.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pydicom

_RTPLAN = "1.2.840.10008.5.1.4.1.1.481.5"
_RTSTRUCT = "1.2.840.10008.5.1.4.1.1.481.3"
_RTDOSE = "1.2.840.10008.5.1.4.1.1.481.2"


@dataclass(frozen=True)
class PlanSet:
    plan_path: Path | None
    struct_path: Path | None
    dose_path: Path | None


def _struct_for_uid(ds) -> str:
    """RTSTRUCT FrameOfReferenceUID (top-level, or via the referenced sequence)."""
    top = str(getattr(ds, "FrameOfReferenceUID", "") or "")
    if top:
        return top
    if "ReferencedFrameOfReferenceSequence" in ds:
        return str(getattr(ds.ReferencedFrameOfReferenceSequence[0],
                           "FrameOfReferenceUID", "") or "")
    return ""


def _scan(folder: Path) -> tuple[dict, dict, dict, list]:
    """Return (plans_by_sop, structs_by_sop, structs_by_for, doses).

    structs_by_for maps a FrameOfReferenceUID to the struct paths sharing it, so
    the FoR fallback can require a *unique* struct in that frame before using it.
    """
    plans: dict[str, dict] = {}
    structs: dict[str, Path] = {}
    structs_by_for: dict[str, list[Path]] = {}
    doses: list[dict] = []
    for path in Path(folder).rglob("*.dcm"):
        try:
            ds = pydicom.dcmread(str(path), stop_before_pixels=True, force=True)
        except Exception:
            continue
        sop_class = str(getattr(ds, "SOPClassUID", ""))
        sop = str(getattr(ds, "SOPInstanceUID", ""))
        if sop_class == _RTPLAN:
            ref = ""
            if "ReferencedStructureSetSequence" in ds:
                ref = str(ds.ReferencedStructureSetSequence[0]
                          .ReferencedSOPInstanceUID)
            plans[sop] = {"path": path, "struct_ref": ref,
                          "for": str(getattr(ds, "FrameOfReferenceUID", "") or "")}
        elif sop_class == _RTSTRUCT:
            structs[sop] = path
            for_uid = _struct_for_uid(ds)
            if for_uid:
                structs_by_for.setdefault(for_uid, []).append(path)
        elif sop_class == _RTDOSE:
            ref = ""
            if "ReferencedRTPlanSequence" in ds:
                ref = str(ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID)
            doses.append({"path": path, "plan_ref": ref})
    return plans, structs, structs_by_for, doses


def _resolve_set(sop, info, structs, structs_by_for, dose_for_plan) -> PlanSet:
    struct_path = structs.get(info["struct_ref"])
    if struct_path is None:
        # FoR fallback: use the struct in this plan's frame iff it is unique.
        candidates = structs_by_for.get(info["for"], [])
        if len(candidates) == 1:
            struct_path = candidates[0]
    return PlanSet(plan_path=info["path"], struct_path=struct_path,
                   dose_path=dose_for_plan.get(sop))


def match_folder(folder: str | Path) -> list[PlanSet]:
    plans, structs, structs_by_for, doses = _scan(Path(folder))
    dose_for_plan = {d["plan_ref"]: d["path"] for d in doses}
    return [_resolve_set(sop, info, structs, structs_by_for, dose_for_plan)
            for sop, info in plans.items()]


def match_plan_file(plan_path: str | Path) -> list[PlanSet]:
    """Resolve the single PlanSet for one user-selected RTPLAN file.

    The TPS exports RP/RS/RD into separate per-modality subfolders under a common
    parent, so the struct and dose are usually NOT beside the plan. We scan the
    plan's own folder first; if its struct or dose is missing there, we widen the
    search one directory level up (the parent that holds the sibling modality
    folders). Matching stays reference-UID based throughout.

    Returns a one-element list: the selected plan's set, with struct_path/dose_path
    possibly None so the engine can REJECT with a precise reason rather than crash.
    Returns [] if the file is not a readable RTPLAN.
    """
    plan_path = Path(plan_path)
    try:
        ds = pydicom.dcmread(str(plan_path), stop_before_pixels=True, force=True)
    except Exception:
        return []
    if str(getattr(ds, "SOPClassUID", "")) != _RTPLAN:
        return []
    sop = str(getattr(ds, "SOPInstanceUID", ""))

    roots = [plan_path.parent]
    if plan_path.parent.parent != plan_path.parent:
        roots.append(plan_path.parent.parent)

    best: PlanSet | None = None
    for root in roots:
        plans, structs, structs_by_for, doses = _scan(root)
        info = plans.get(sop)
        if info is None:
            continue
        dose_for_plan = {d["plan_ref"]: d["path"] for d in doses}
        best = _resolve_set(sop, info, structs, structs_by_for, dose_for_plan)
        if best.struct_path is not None and best.dose_path is not None:
            return [best]
    return [best] if best is not None else []
