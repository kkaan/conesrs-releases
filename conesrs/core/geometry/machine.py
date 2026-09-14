"""Linac geometry: source position and central ray (IEC 61217 -> DICOM, HFS).

Geometry side of the seam. Must never import conesrs.core.dose.

Coordinate conventions (HFS patient, DICOM patient coordinates, millimetres):
    x = patient left, y = patient posterior, z = patient superior.
The room vertical (up) is -y. The gantry rotates in the x-y plane; the couch
(PatientSupportAngle) rotates the patient about the vertical (y) axis.

Source position relative to isocentre:
    x = SAD * sin(G) * cos(T)
    y = -SAD * cos(G)
    z = -SAD * sin(G) * sin(T)
where G = gantry angle, T = couch angle (both degrees). At T = 0 this reduces
to (SAD*sin G, -SAD*cos G, 0): gantry 0 is anterior, gantry 90 is patient-left.

NOTE: the sign of T follows the convention above; it is verified against a real
non-coplanar plan in Plan 2 (engine layer) before clinical use.
"""
from __future__ import annotations

import numpy as np


def source_position(gantry_deg: float, couch_deg: float,
                    isocenter: np.ndarray, sad: float = 1000.0) -> np.ndarray:
    """Source position (mm, DICOM/HFS) for a gantry/couch angle.

    See the module docstring for the full coordinate convention and formula:
        x = SAD*sin(G)*cos(T),  y = -SAD*cos(G),  z = -SAD*sin(G)*sin(T)
    with G = gantry angle, T = couch angle (degrees). Requires sad > 0.
    """
    gantry_rad = np.radians(gantry_deg)
    couch_rad = np.radians(couch_deg)
    rel = np.array([
        sad * np.sin(gantry_rad) * np.cos(couch_rad),
        -sad * np.cos(gantry_rad),
        -sad * np.sin(gantry_rad) * np.sin(couch_rad),
    ])
    return np.asarray(isocenter, dtype=float) + rel


def central_ray(gantry_deg: float, couch_deg: float, isocenter: np.ndarray,
                sad: float = 1000.0) -> tuple[np.ndarray, np.ndarray]:
    """Return (source, unit_direction) for the ray from source through iso."""
    iso = np.asarray(isocenter, dtype=float)
    source = source_position(gantry_deg, couch_deg, iso, sad)
    d = iso - source
    return source, d / np.linalg.norm(d)
