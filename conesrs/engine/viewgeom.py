"""Qt-free view geometry for the contour entry view. No gui / PySide6 imports."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from conesrs.core.geometry.depth import sample_arc_angles
from conesrs.core.geometry.machine import central_ray
from conesrs.core.geometry.structures import (RawStructure, select_body_structure,
                                              select_body_surface)
from conesrs.core.geometry.surface import ContourSurface, Ray, depth_to
from conesrs.engine.target import select_target_centroid
from conesrs.engine.validate import resolve_in_scope_beams


@dataclass(frozen=True)
class ViewSample:
    gantry: float
    couch: float
    source: np.ndarray
    entry: np.ndarray | None
    depth_mm: float | None


@dataclass(frozen=True)
class ViewBeam:
    beam_number: int
    label: str
    cone_size_mm: float
    couch_deg: float
    samples: tuple[ViewSample, ...]
    mu: float = 0.0


@dataclass(frozen=True)
class RingSet:
    """Decimated closed contour rings packed for drawing.

    points: (N, 3) float32, every ring concatenated; offsets: (R+1,) int64 so
    ring r is points[offsets[r]:offsets[r+1]]. Rings are closed implicitly
    (the last vertex joins back to the first).
    """
    points: np.ndarray
    offsets: np.ndarray

    @property
    def n_rings(self) -> int:
        return int(len(self.offsets) - 1)

    def ring(self, r: int) -> np.ndarray:
        return self.points[int(self.offsets[r]):int(self.offsets[r + 1])]


@dataclass(frozen=True)
class ViewStructure:
    name: str
    roi_type: str
    is_body: bool
    default_on: bool
    rings: RingSet


@dataclass(frozen=True)
class ViewGeometry:
    iso: np.ndarray
    target: np.ndarray | None
    body: ContourSurface
    structures: tuple[RawStructure, ...]
    beams: tuple[ViewBeam, ...]
    display: tuple[ViewStructure, ...] = ()


_TARGET_NAME = re.compile(r"^\s*(PTV|GTV)", re.IGNORECASE)


def _default_on(name: str, roi_type: str) -> bool:
    return roi_type.upper() == "PTV" or bool(_TARGET_NAME.match(name or ""))


def decimate_contours(contours: dict, *, slice_step_mm: float = 3.0,
                      max_vertices: int = 100) -> RingSet:
    """Thin a {z: [(N,2) polygon, ...]} contour stack for display.

    Keeps a slice whenever it is >= slice_step_mm past the last kept slice
    (first and last slices always kept); subsamples each polygon by a uniform
    index stride so no ring exceeds max_vertices; drops polygons with < 3
    vertices. Pure numpy; safe on 500k-point structure sets.
    """
    keys = sorted(contours, key=float)
    kept: list = []
    last_z = None
    for key in keys:
        z = float(key)
        if last_z is None or z - last_z >= slice_step_mm - 1e-9:
            kept.append(key)
            last_z = z
    if keys and kept[-1] != keys[-1]:
        kept.append(keys[-1])
    chunks: list[np.ndarray] = []
    offsets = [0]
    for key in kept:
        z = float(key)
        for poly in contours[key]:
            poly = np.asarray(poly, dtype=float).reshape(-1, 2)
            if len(poly) > max_vertices:
                poly = poly[::int(math.ceil(len(poly) / max_vertices))]
            if len(poly) < 3:
                continue
            ring = np.column_stack([poly, np.full(len(poly), z)]).astype(np.float32)
            chunks.append(ring)
            offsets.append(offsets[-1] + len(ring))
    points = (np.concatenate(chunks) if chunks
              else np.zeros((0, 3), dtype=np.float32))
    return RingSet(points=points, offsets=np.asarray(offsets, dtype=np.int64))


def _build_display(body: ContourSurface, structures, body_name: str,
                   body_roi_type: str) -> tuple[ViewStructure, ...]:
    out = [ViewStructure(name=body_name, roi_type=body_roi_type, is_body=True,
                         default_on=True, rings=decimate_contours(body.contours))]
    for s in structures:
        if s.roi_type.upper() == "MARKER" or s.name == body_name:
            continue
        out.append(ViewStructure(name=s.name, roi_type=s.roi_type, is_body=False,
                                 default_on=_default_on(s.name, s.roi_type),
                                 rings=decimate_contours(s.contours)))
    return tuple(out)


def _sample_arc(arc, cone_size_mm, iso, surface, step_deg, sad) -> ViewBeam:
    samples = []
    for gantry, _mu in sample_arc_angles(
            arc.gantry_start, arc.gantry_stop, arc.rotation, step_deg, arc.mu):
        source, direction = central_ray(gantry, arc.couch, iso, sad)
        entry = surface.entry_point(Ray(source, direction))
        if entry is None:
            samples.append(ViewSample(float(gantry), float(arc.couch), source,
                                      None, None))
        else:
            samples.append(ViewSample(
                float(gantry), float(arc.couch), source, entry,
                float(depth_to(iso, entry))))
    label = f"Beam {arc.beam_number} · {cone_size_mm:g} mm · couch {arc.couch:g}°"
    return ViewBeam(beam_number=int(arc.beam_number), label=label,
                    cone_size_mm=float(cone_size_mm),
                    couch_deg=float(arc.couch), samples=tuple(samples),
                    mu=float(arc.mu))


def build_view_geometry(plan, structures, model, *, step_deg=2.0, sad=1000.0,
                        plan_path="<plan>") -> ViewGeometry | None:
    iso = np.asarray(plan.isocentre, dtype=float)
    try:
        body = select_body_surface(list(structures), iso)
    except ValueError:
        return None
    body_roi = select_body_structure(list(structures))
    try:
        target = select_target_centroid(list(structures), iso)
    except ValueError:
        target = None
    beams: tuple[ViewBeam, ...] = ()
    if model is not None:
        in_scope, _rejects = resolve_in_scope_beams(plan.arcs, model, plan_path)
        beams = tuple(
            _sample_arc(arc, cone, iso, body, step_deg, sad)
            for arc, cone in in_scope
        )
    return ViewGeometry(iso=iso, target=target, body=body,
                        structures=tuple(structures), beams=beams,
                        display=_build_display(body, structures, body_roi.name,
                                               body_roi.roi_type))
