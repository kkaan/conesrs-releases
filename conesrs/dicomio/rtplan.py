"""Faithful RTPLAN parser -> Plan / Arc dataclasses.

Model-agnostic: surfaces the raw applicator ID and description (no cone-size
resolution — that is an engine concern) and reads NumberOfFractionsPlanned so
the per-fraction dose basis can be reconciled later. No validation here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pydicom


@dataclass(frozen=True)
class Arc:
    """One dynamic-conformal arc (or static field as a degenerate 1-point arc)."""

    beam_number: int
    beam_type: str            # e.g. "DYNAMIC"
    applicator_id: str        # raw, e.g. "Aktina SRS" or "7.50 mm"
    applicator_description: str  # raw, e.g. "STEREOTACTIC CONE 09.00 mm"
    mu: float                 # monitor units for this arc (per fraction)
    gantry_start: float       # degrees
    gantry_stop: float        # degrees
    rotation: str             # "CW" or "CCW"
    couch: float              # PatientSupportAngle, degrees
    collimator: float         # BeamLimitingDeviceAngle, degrees
    treatment_delivery_type: str = ""        # "TREATMENT" | "SETUP" | ""
    mlc: list | None = None                  # per-CP MLCX LeafJawPositions (None unless with_mlc)


@dataclass(frozen=True)
class Plan:
    """A parsed RTPLAN: identifiers, geometry, arcs, and dose-reference info."""

    sop_uid: str
    structure_set_ref_uid: str
    frame_of_reference_uid: str
    patient_id: str
    plan_label: str
    machine: str
    number_of_fractions: int
    isocentre: np.ndarray            # (3,) mm
    arcs: list[Arc]
    total_mu: float                  # sum of arc MU (per fraction)
    beam_dose_sum_gy: float | None   # sum of per-beam BeamDose (per fraction)
    dose_spec_point: np.ndarray | None  # (3,) mm, or None
    prescription_dose_gy: float | None


def _rotation(direction: str | None) -> str:
    d = (direction or "").upper()
    return "CCW" if d.startswith("CC") else "CW"


def _mlc_positions(beam) -> list | None:
    """Per-control-point MLCX leaf positions as 1-D float arrays, or None.

    Returns None if the beam carries no MLCX device. Otherwise returns one
    1-D float vector per control point, so ``len(result)`` always equals the
    control-point count and every row shares the same leaf count.

    Matches the X bank exactly ("MLCX") so an MLCY bank in the same beam cannot
    clobber the MLCX positions. Leaf positions are carried sparsely in DICOM: a
    control point that omits the MLCX positions inherits the previous control
    point's vector (forward-fill). If a control point would have no vector
    because no MLCX positions have appeared yet, a ValueError is raised rather
    than silently dropping the control point (which would shorten the sequence
    and could make a modulated plan look parked).
    """
    has_mlc = any(
        str(getattr(d, "RTBeamLimitingDeviceType", "")) == "MLCX"
        for d in getattr(beam, "BeamLimitingDeviceSequence", [])
    )
    if not has_mlc:
        return None
    out: list = []
    cur = None
    for i, cp in enumerate(beam.ControlPointSequence):
        for pos in getattr(cp, "BeamLimitingDevicePositionSequence", []):
            if str(getattr(pos, "RTBeamLimitingDeviceType", "")) == "MLCX":
                cur = np.array([float(x) for x in pos.LeafJawPositions], dtype=float)
        if cur is None:
            raise ValueError(
                f"beam {getattr(beam, 'BeamNumber', '?')}: MLCX positions absent "
                f"at control point {i} — cannot reconstruct leaf sequence"
            )
        out.append(cur)
    return out


def parse_rtplan(path: str | Path, with_mlc: bool = False) -> Plan:
    ds = pydicom.dcmread(str(path), force=True)
    fg = ds.FractionGroupSequence[0]

    # MU and BeamDose per referenced beam number (per fraction)
    mu_by_beam: dict[int, float] = {}
    dose_by_beam: dict[int, float] = {}
    spec_point = None
    for rb in fg.ReferencedBeamSequence:
        n = int(rb.ReferencedBeamNumber)
        if "BeamMeterset" in rb:
            mu_by_beam[n] = float(rb.BeamMeterset)
        if "BeamDose" in rb:
            dose_by_beam[n] = float(rb.BeamDose)
        if spec_point is None and "BeamDoseSpecificationPoint" in rb:
            spec_point = np.array([float(x) for x in rb.BeamDoseSpecificationPoint])

    arcs: list[Arc] = []
    isocentre = None
    machine = ""
    for b in ds.BeamSequence:
        n = int(b.BeamNumber)
        cps = b.ControlPointSequence
        c0 = cps[0]
        if isocentre is None and "IsocenterPosition" in c0:
            isocentre = np.array([float(x) for x in c0.IsocenterPosition])
        machine = str(getattr(b, "TreatmentMachineName", "") or machine)
        app = b.ApplicatorSequence[0] if "ApplicatorSequence" in b else None
        arcs.append(Arc(
            beam_number=n,
            beam_type=str(getattr(b, "BeamType", "")),
            applicator_id=str(getattr(app, "ApplicatorID", "") if app else ""),
            applicator_description=str(
                getattr(app, "ApplicatorDescription", "") if app else ""),
            mu=mu_by_beam.get(n, 0.0),
            gantry_start=float(getattr(c0, "GantryAngle", 0.0)),
            gantry_stop=float(getattr(cps[-1], "GantryAngle",
                                     getattr(c0, "GantryAngle", 0.0))),
            rotation=_rotation(getattr(c0, "GantryRotationDirection", None)),
            couch=float(getattr(c0, "PatientSupportAngle", 0.0)),
            collimator=float(getattr(c0, "BeamLimitingDeviceAngle", 0.0)),
            treatment_delivery_type=str(getattr(b, "TreatmentDeliveryType", "")),
            mlc=(_mlc_positions(b) if with_mlc else None),
        ))

    prescription = None
    if "DoseReferenceSequence" in ds:
        for dr in ds.DoseReferenceSequence:
            if "TargetPrescriptionDose" in dr:
                prescription = float(dr.TargetPrescriptionDose)
                break

    beam_dose_sum = sum(dose_by_beam.values()) if dose_by_beam else None
    struct_ref = ds.ReferencedStructureSetSequence[0].ReferencedSOPInstanceUID

    return Plan(
        sop_uid=str(ds.SOPInstanceUID),
        structure_set_ref_uid=str(struct_ref),
        frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
        patient_id=str(getattr(ds, "PatientID", "")),
        plan_label=str(getattr(ds, "RTPlanLabel", "")),
        machine=machine,
        number_of_fractions=int(fg.NumberOfFractionsPlanned),
        isocentre=(isocentre if isocentre is not None
                   else np.zeros(3, dtype=float)),
        arcs=arcs,
        total_mu=sum(a.mu for a in arcs),
        beam_dose_sum_gy=beam_dose_sum,
        dose_spec_point=spec_point,
        prescription_dose_gy=prescription,
    )
