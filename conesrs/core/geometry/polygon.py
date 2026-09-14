"""2D polygon helpers for axial contour slices (x, y in mm)."""
from __future__ import annotations

import numpy as np


def points_in_polygon(points: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    """Vectorised ray-casting point-in-polygon test.

    points: (M, 2); polygon: (N, 2). Returns (M,) bool. Uses exactly the same
    crossing rule as the historical scalar loop (edge i-1 -> i, strict x <
    intersection, half-open y test) so the two agree on every input.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    poly = np.asarray(polygon, dtype=float).reshape(-1, 2)
    if len(pts) == 0 or len(poly) == 0:
        return np.zeros(len(pts), dtype=bool)
    x = pts[:, 0:1]
    y = pts[:, 1:2]
    xi = poly[:, 0][None, :]
    yi = poly[:, 1][None, :]
    xj = np.roll(poly[:, 0], 1)[None, :]
    yj = np.roll(poly[:, 1], 1)[None, :]
    crosses = (yi > y) != (yj > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_int = (xj - xi) * (y - yi) / (yj - yi) + xi
    hits = crosses & (x < x_int)
    return (hits.sum(axis=1) % 2) == 1


def point_in_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    """Ray-casting point-in-polygon test. polygon: (N, 2) vertices."""
    return bool(points_in_polygon(np.asarray(point, dtype=float)[None, :2],
                                  polygon)[0])


def polygon_centroid(polygon: np.ndarray) -> np.ndarray:
    """Vertex mean (NOT the area-weighted polygon centroid), (2,)."""
    return np.asarray(polygon, dtype=float).mean(axis=0)
