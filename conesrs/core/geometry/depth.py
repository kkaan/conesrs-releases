"""Arc sampling and per-direction depth traces.

Geometry side of the seam. Must not import conesrs.core.dose.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from conesrs.core.geometry.machine import central_ray
from conesrs.core.geometry.surface import Ray, Surface, depth_to


@dataclass(frozen=True)
class ArcSpec:
    gantry_start: float
    gantry_stop: float
    rotation: str  # "CW" or "CCW"
    couch: float
    total_mu: float
    cone_size_mm: float | None = None  # set by the engine; required for dose


@dataclass(frozen=True)
class DepthTrace:
    """A single sampled beam direction and its ray-traced depth.

    NOTE: `frozen=True` blocks attribute reassignment but NOT in-place mutation
    of the `source`/`entry` numpy arrays. Treat this as an immutable value
    object; do not mutate the stored arrays in place.
    """
    gantry: float
    couch: float
    mu: float
    source: np.ndarray
    entry: np.ndarray
    depth_mm: float


def _swept_angle(start: float, stop: float, rotation: str) -> float:
    """Positive magnitude of the gantry sweep for the given direction."""
    if rotation.upper() == "CW":
        sweep = (stop - start) % 360.0
    else:
        sweep = (start - stop) % 360.0
    return 360.0 if sweep == 0.0 else sweep


def sample_arc_angles(gantry_start: float, gantry_stop: float, rotation: str,
                      step_deg: float, total_mu: float
                      ) -> list[tuple[float, float]]:
    """Return [(gantry_mid_deg, mu), ...] subdividing the arc into ~step_deg bins.

    MU is distributed proportionally to gantry rotation (linear in angle). Each
    returned gantry is the midpoint of its sub-arc.
    """
    sweep = _swept_angle(gantry_start, gantry_stop, rotation)
    n = max(1, int(round(sweep / step_deg)))
    sub = sweep / n
    sign = 1.0 if rotation.upper() == "CW" else -1.0
    mu_each = total_mu / n
    out = []
    for i in range(n):
        mid = gantry_start + sign * sub * (i + 0.5)
        out.append((mid % 360.0, mu_each))
    return out


def trace_arc(arc: ArcSpec, iso: np.ndarray, surface: Surface,
              step_deg: float = 2.0, sad: float = 1000.0) -> list[DepthTrace]:
    """Ray-trace a depth per sub-sampled gantry angle of the arc.

    Raises ValueError (via depth_to) if any sampled ray misses the surface; a
    beam missing the body is handled as a validation reject in the engine layer.
    """
    iso = np.asarray(iso, dtype=float)
    traces: list[DepthTrace] = []
    for gantry, mu in sample_arc_angles(arc.gantry_start, arc.gantry_stop,
                                        arc.rotation, step_deg, arc.total_mu):
        source, direction = central_ray(gantry, arc.couch, iso, sad)
        entry = surface.entry_point(Ray(source, direction))
        depth = depth_to(iso, entry)
        traces.append(DepthTrace(gantry=gantry, couch=arc.couch, mu=mu,
                                 source=source, entry=entry, depth_mm=depth))
    return traces
