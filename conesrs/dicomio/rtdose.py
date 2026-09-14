"""Faithful RTDOSE parser -> DoseGrid with point and sphere sampling.

Only axial dose grids (IOP = [1,0,0,0,1,0]) are supported in v1. Dose is stored
in Gy (pixel_array * DoseGridScaling). The grid carries DoseSummationType so the
per-fraction-vs-total basis can be reconciled by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pydicom


@dataclass(frozen=True)
class DoseGrid:
    origin: np.ndarray        # (3,) ImagePositionPatient, mm
    row_spacing: float        # mm along +y (PixelSpacing[0])
    col_spacing: float        # mm along +x (PixelSpacing[1])
    z_offsets: np.ndarray     # (frames,) GridFrameOffsetVector, mm from origin z
    dose_gy: np.ndarray       # (frames, rows, cols) in Gy
    summation_type: str       # "PLAN" | "FRACTION" | "BEAM"
    units: str                # "GY"
    plan_ref_uid: str
    frame_of_reference_uid: str

    def _indices(self, p: np.ndarray) -> tuple[float, float, float]:
        col = (p[0] - self.origin[0]) / self.col_spacing
        row = (p[1] - self.origin[1]) / self.row_spacing
        z_spacing = (self.z_offsets[1] - self.z_offsets[0]
                     if len(self.z_offsets) > 1 else 1.0)
        frame = (p[2] - self.origin[2] - self.z_offsets[0]) / z_spacing
        return frame, row, col

    def sample_point(self, p: np.ndarray) -> float:
        """Trilinear dose (Gy) at a patient point; NaN if outside the grid."""
        f, r, c = self._indices(np.asarray(p, dtype=float))
        nf, nr, nc = self.dose_gy.shape
        if not (0 <= f <= nf - 1 and 0 <= r <= nr - 1 and 0 <= c <= nc - 1):
            return float("nan")
        f0, r0, c0 = int(np.floor(f)), int(np.floor(r)), int(np.floor(c))
        f1, r1, c1 = min(f0 + 1, nf - 1), min(r0 + 1, nr - 1), min(c0 + 1, nc - 1)
        df, dr, dc = f - f0, r - r0, c - c0
        total = 0.0
        for (fi, wf) in ((f0, 1 - df), (f1, df)):
            for (ri, wr) in ((r0, 1 - dr), (r1, dr)):
                for (ci, wc) in ((c0, 1 - dc), (c1, dc)):
                    total += wf * wr * wc * float(self.dose_gy[fi, ri, ci])
        return total

    def sample_sphere(self, p: np.ndarray, radius_mm: float,
                      step_mm: float = 1.0) -> float:
        """Mean trilinear dose over a lattice of points within radius of p."""
        p = np.asarray(p, dtype=float)
        offs = np.arange(-radius_mm, radius_mm + step_mm * 0.5, step_mm)
        vals = []
        for dx, dy, dz in product(offs, offs, offs):
            if dx * dx + dy * dy + dz * dz <= radius_mm * radius_mm:
                v = self.sample_point(p + np.array([dx, dy, dz]))
                if not np.isnan(v):
                    vals.append(v)
        if not vals:
            return self.sample_point(p)
        return float(np.mean(vals))


def parse_rtdose(path: str | Path) -> DoseGrid:
    ds = pydicom.dcmread(str(path), force=True)
    iop = [float(x) for x in ds.ImageOrientationPatient]
    if iop != [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]:
        raise ValueError(f"only axial dose grids are supported in v1; IOP={iop}")
    scaling = float(ds.DoseGridScaling)
    dose_gy = ds.pixel_array.astype(float) * scaling
    row_spacing, col_spacing = (float(ds.PixelSpacing[0]),
                                float(ds.PixelSpacing[1]))
    plan_ref = ""
    if "ReferencedRTPlanSequence" in ds:
        plan_ref = str(ds.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID)
    return DoseGrid(
        origin=np.array([float(x) for x in ds.ImagePositionPatient]),
        row_spacing=row_spacing, col_spacing=col_spacing,
        z_offsets=np.array([float(x) for x in ds.GridFrameOffsetVector]),
        dose_gy=dose_gy,
        summation_type=str(getattr(ds, "DoseSummationType", "")),
        units=str(getattr(ds, "DoseUnits", "")),
        plan_ref_uid=plan_ref,
        frame_of_reference_uid=str(getattr(ds, "FrameOfReferenceUID", "")),
    )
