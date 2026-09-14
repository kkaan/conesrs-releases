"""Body-surface representations and ray-surface intersection.

Geometry side of the seam. Must never import conesrs.core.dose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

from conesrs.core.geometry.polygon import points_in_polygon


@dataclass(frozen=True)
class Ray:
    source: np.ndarray     # (3,)
    direction: np.ndarray  # (3,) unit vector


class Surface(Protocol):
    def entry_point(self, ray: Ray) -> Optional[np.ndarray]:
        """First intersection of the ray with the surface, or None."""
        ...


def depth_to(target: np.ndarray, entry: Optional[np.ndarray]) -> float:
    """Path length from entry point to target (e.g. isocentre), in mm."""
    if entry is None:
        raise ValueError("no entry point: ray did not intersect the surface")
    return float(np.linalg.norm(np.asarray(target, dtype=float) - entry))


@dataclass(frozen=True)
class SphereSurface:
    """Analytic spherical surface — used for tests and sanity phantoms."""

    center: np.ndarray
    radius: float

    def entry_point(self, ray: Ray) -> Optional[np.ndarray]:
        oc = ray.source - self.center
        b = 2.0 * float(np.dot(oc, ray.direction))
        c = float(np.dot(oc, oc)) - self.radius * self.radius
        disc = b * b - 4.0 * c
        if disc < 0.0:
            return None
        sqrt_disc = np.sqrt(disc)
        t1 = (-b - sqrt_disc) / 2.0
        t2 = (-b + sqrt_disc) / 2.0
        t = t1 if t1 > 0.0 else t2
        if t <= 0.0:
            return None
        return ray.source + t * ray.direction


@dataclass(frozen=True)
class ContourSurface:
    """Body surface reconstructed from stacked axial contour polygons.

    contours maps an axial z (mm) to a list of (N, 2) polygons on that slice.
    Multiple polygons per slice are supported (e.g. after couch stripping the
    list is reduced to the patient blob).
    """

    contours: dict  # {z_mm: [ (N,2) ndarray, ... ]}

    def __post_init__(self) -> None:
        zs = np.array(sorted(self.contours.keys()), dtype=float)
        object.__setattr__(self, "_zs", zs)
        if len(zs) > 1:
            # half the median spacing as the in-range tolerance
            tol = float(np.median(np.diff(zs))) / 2.0 + 1e-6
        elif len(zs) == 1:
            tol = float("inf")  # single slice: snap regardless of z
        else:
            tol = 0.0
        object.__setattr__(self, "_z_tol", tol)

    def _nearest_z(self, z: float) -> Optional[float]:
        zs = self._zs
        if len(zs) == 0:
            return None
        idx = int(np.argmin(np.abs(zs - z)))
        if abs(zs[idx] - z) > self._z_tol:
            return None
        return float(zs[idx])

    def inside_many(self, points: np.ndarray) -> np.ndarray:
        """Vectorised is_inside over an (M, 3) array -> (M,) bool.

        Same rule as the scalar test: snap each point to its nearest slice
        (first minimum on ties), reject if farther than the tolerance, then
        OR the polygon tests on that slice.
        """
        pts = np.asarray(points, dtype=float).reshape(-1, 3)
        out = np.zeros(len(pts), dtype=bool)
        zs = self._zs
        if len(zs) == 0 or len(pts) == 0:
            return out
        idx = np.abs(zs[None, :] - pts[:, 2][:, None]).argmin(axis=1)
        in_range = np.abs(zs[idx] - pts[:, 2]) <= self._z_tol
        for k in np.unique(idx[in_range]):
            sel = np.flatnonzero(in_range & (idx == k))
            xy = pts[sel, :2]
            hit = np.zeros(len(sel), dtype=bool)
            for poly in self.contours[float(zs[k])]:
                hit |= points_in_polygon(xy, poly)
            out[sel] = hit
        return out

    def is_inside(self, p: np.ndarray) -> bool:
        return bool(self.inside_many(np.asarray(p, dtype=float)[None, :])[0])

    def entry_point(self, ray: Ray, step: float = 1.0,
                    max_distance: float = 1500.0) -> Optional[np.ndarray]:
        """First outside->inside crossing marching from the source toward iso.

        Vectorised march with the same sample positions as the historical
        scalar loop (t = step, 2*step, ..., first t > max_distance) and the
        same 40-step bisection, so results are identical for step=1.0.
        """
        source = np.asarray(ray.source, dtype=float)
        direction = np.asarray(ray.direction, dtype=float)
        if self.inside_many(source[None, :])[0]:
            return ray.source  # source already inside (degenerate) -> entry here
        n_steps = int(np.floor(max_distance / step)) + 1
        ts = step * np.arange(1, n_steps + 1, dtype=float)
        pts = source[None, :] + ts[:, None] * direction[None, :]
        inside = self.inside_many(pts)
        hit = np.flatnonzero(inside)
        if len(hit) == 0:
            return None
        t = float(ts[hit[0]])
        # refine by bisection between (t-step) outside and t inside
        lo, hi = t - step, t
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if self.inside_many((ray.source + mid * ray.direction)[None, :])[0]:
                hi = mid
            else:
                lo = mid
        return ray.source + hi * ray.direction
