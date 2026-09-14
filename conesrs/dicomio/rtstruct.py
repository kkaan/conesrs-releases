"""Faithful RTSTRUCT parser -> StructureSet of core RawStructure objects.

Every ROI is parsed as stacked axial polygons. The parser does NOT decide which
ROI is the body or the target — that is the universal geometry algorithm in
conesrs.core.geometry.structures.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pydicom

from conesrs.core.geometry.structures import RawStructure


@dataclass(frozen=True)
class StructureSet:
    sop_uid: str
    frame_of_reference_uid: str
    structures: list[RawStructure]


def _contours_by_z(roi_contour) -> dict:
    contours: dict = {}
    for citem in getattr(roi_contour, "ContourSequence", []):
        data = [float(x) for x in citem.ContourData]
        if not data:
            continue
        z = round(float(data[2]), 3)
        poly = np.array([[data[i], data[i + 1]] for i in range(0, len(data), 3)],
                        dtype=float)
        contours.setdefault(z, []).append(poly)
    return contours


def structure_set_from_dataset(ds) -> StructureSet:
    names = {int(r.ROINumber): str(r.ROIName) for r in ds.StructureSetROISequence}
    types = {}
    for o in getattr(ds, "RTROIObservationsSequence", []):
        types[int(o.ReferencedROINumber)] = str(
            getattr(o, "RTROIInterpretedType", "") or "")
    structures = []
    for rc in getattr(ds, "ROIContourSequence", []):
        num = int(rc.ReferencedROINumber)
        contours = _contours_by_z(rc)
        if not contours:
            continue
        structures.append(RawStructure(
            name=names.get(num, f"ROI{num}"),
            roi_type=types.get(num, ""),
            contours=contours,
        ))
    return StructureSet(
        sop_uid=str(getattr(ds, "SOPInstanceUID", "")),
        frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
        structures=structures,
    )


def parse_rtstruct(path: str | Path) -> StructureSet:
    ds = pydicom.dcmread(str(path), force=True)
    return structure_set_from_dataset(ds)
