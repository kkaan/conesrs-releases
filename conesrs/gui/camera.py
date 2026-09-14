"""Orthographic camera for the contour entry view. Pure numpy — no Qt import.

Frame: DICOM HFS patient coordinates (+x patient left, +y posterior, +z
superior). A basis is (n, r, u): view direction (eye -> scene), screen-right,
screen-up, all unit and mutually orthogonal with u = r x n.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PRESETS = ("arc", "axial", "coronal", "sagittal")
_ELEVATION_MAX = 1.5
_ZOOM_MIN, _ZOOM_MAX = 0.4, 5.0

# preset -> (view direction n, screen-up hint)
_FIXED = {
    "axial": ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),     # from superior, anterior up
    "coronal": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),     # from anterior, superior up
    "sagittal": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),   # from patient left, superior up
}


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 else v


def _rodrigues(v: np.ndarray, k: np.ndarray, angle: float) -> np.ndarray:
    """Rotate v about unit axis k by angle (radians)."""
    c, s = np.cos(angle), np.sin(angle)
    return v * c + np.cross(k, v) * s + k * float(np.dot(k, v)) * (1.0 - c)


def arc_axis(couch_deg: float) -> np.ndarray:
    """Gantry rotation axis for a couch angle: the normal of the plane swept by
    source_position(G, couch). Sign chosen so the z component is >= 0."""
    t = np.radians(couch_deg)
    a = np.array([np.sin(t), 0.0, np.cos(t)])
    return -a if a[2] < 0 else a


@dataclass
class Camera:
    preset: str = "arc"
    couch_deg: float = 0.0
    azimuth: float = 0.0       # radians, orbit about screen-up
    elevation: float = 0.0     # radians, orbit about screen-right
    zoom: float = 1.0

    def basis(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        if self.preset == "arc":
            n, up = -arc_axis(self.couch_deg), np.array([0.0, -1.0, 0.0])
        else:
            n, up = (np.array(v) for v in _FIXED[self.preset])
        n = _unit(n)
        r = np.cross(n, up)
        if np.linalg.norm(r) < 1e-9:
            r = np.cross(n, np.array([1.0, 0.0, 0.0]))
        r = _unit(r)
        u = _unit(np.cross(r, n))
        if self.azimuth:
            n, r = _rodrigues(n, u, self.azimuth), _rodrigues(r, u, self.azimuth)
        if self.elevation:
            n = _rodrigues(n, r, self.elevation)
            u = _unit(np.cross(r, n))
        return _unit(n), _unit(r), _unit(u)

    def orbit(self, d_azimuth: float, d_elevation: float) -> None:
        self.azimuth += d_azimuth
        self.elevation = float(np.clip(self.elevation + d_elevation,
                                       -_ELEVATION_MAX, _ELEVATION_MAX))

    def reset_orbit(self) -> None:
        self.azimuth = 0.0
        self.elevation = 0.0

    def zoom_by(self, factor: float) -> None:
        self.zoom = float(np.clip(self.zoom * factor, _ZOOM_MIN, _ZOOM_MAX))


def project(points: np.ndarray, iso: np.ndarray, basis, scale: float,
            width: float, height: float) -> np.ndarray:
    """(N,3) world mm -> (N,3) [screen x px, screen y px, depth mm along n].

    Iso maps to the canvas centre; screen y grows downward.
    """
    n, r, u = basis
    d = np.asarray(points, dtype=float).reshape(-1, 3) - np.asarray(iso, dtype=float)
    out = np.empty((len(d), 3), dtype=float)
    out[:, 0] = width / 2.0 + (d @ r) * scale
    out[:, 1] = height / 2.0 - (d @ u) * scale
    out[:, 2] = d @ n
    return out
