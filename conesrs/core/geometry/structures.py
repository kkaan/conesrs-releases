"""Universal, model-agnostic body-surface selection and target identification.

The SAME logic runs for every patient regardless of cone or beam model
(design spec §4.6). Geometry side of the seam — must not import conesrs.core.dose.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from conesrs.core.geometry.polygon import point_in_polygon, polygon_centroid
from conesrs.core.geometry.surface import ContourSurface

_BODY_NAME = re.compile(r"external|patient|body", re.IGNORECASE)
_MAX_PLAUSIBLE_WIDTH_MM = 250.0  # a cranial cross-section is well under this


@dataclass(frozen=True)
class RawStructure:
    """A named structure as stacked axial polygons (produced by dicomio later)."""

    name: str
    roi_type: str
    contours: dict  # {z_mm: [ (N,2) ndarray, ... ]}


def _median_width(contours: dict) -> float:
    widths = []
    for polys in contours.values():
        for poly in polys:
            widths.append(float(poly[:, 0].max() - poly[:, 0].min()))
    return float(np.median(widths)) if widths else 0.0


def _is_body_candidate(s: RawStructure) -> bool:
    return s.roi_type.upper() == "EXTERNAL" or bool(_BODY_NAME.search(s.name))


def _strip_to_iso_blob(contours: dict, iso: np.ndarray) -> dict:
    """Keep, per slice, only the polygon enclosing iso (x,y) or nearest to it.

    When several polygons enclose iso (e.g. a nested/ring contour), the one with
    the most vertices is kept, on the assumption the outer patient contour is the
    most finely sampled. If none encloses iso, the polygon whose centroid is
    nearest iso is kept.
    """
    iso_xy = iso[:2]
    stripped: dict = {}
    for z, polys in contours.items():
        if len(polys) == 1:
            stripped[z] = [polys[0]]
            continue
        enclosing = [p for p in polys if point_in_polygon(iso_xy, p)]
        if enclosing:
            stripped[z] = [max(enclosing, key=lambda p: len(p))]
        else:
            stripped[z] = [min(
                polys,
                key=lambda p: float(np.linalg.norm(polygon_centroid(p) - iso_xy)),
            )]
    return stripped


def select_body_structure(structures: list[RawStructure]) -> RawStructure:
    """The ROI whose contours become the body surface (see select_body_surface).

    Scoring: among body candidates, prefer those of plausible width (couch-merged
    contours are implausibly wide). Ties broken by narrower median width.
    """
    candidates = [s for s in structures if _is_body_candidate(s)]
    if not candidates:
        raise ValueError("no body-surface candidate structure found")

    def score(s: RawStructure) -> tuple[int, float]:
        w = _median_width(s.contours)
        plausible = 0 if w <= _MAX_PLAUSIBLE_WIDTH_MM else 1
        return (plausible, w)  # plausible first, then narrowest

    return min(candidates, key=score)


def select_body_surface(structures: list[RawStructure],
                        iso: np.ndarray) -> ContourSurface:
    """Choose the true skin surface and strip couch/fragments.

    KNOWN LIMITATION: the couch-merged test uses the MEDIAN slice width, so a
    couch merged into the body contour on only a minority of slices (e.g. a few
    inferior slices) may not lift the median past the threshold and is not
    detected here. Disconnected couch polygons are still stripped per-slice by
    _strip_to_iso_blob, but a couch MERGED into the patient polygon on a minority
    of slices is not separable here. The design's backstops for this are the
    validation candidate-surface-disagreement warning and the GUI per-plan
    override (later plans). Width is measured in X (lateral) extent, which is the
    axis a standard flat couch widens.
    """
    best = select_body_structure(structures)
    return ContourSurface(_strip_to_iso_blob(best.contours, iso))


def select_target_centroid(structures: list[RawStructure], iso: np.ndarray,
                           roi_types: tuple[str, ...] | None = None) -> np.ndarray:
    """Centroid (3,) of the structure whose centroid is nearest the isocentre.

    If ``roi_types`` is given (e.g. ("PTV", "GTV")), only structures whose
    ``roi_type`` matches one of them (case-insensitive) are considered. When it
    is None, ALL structures are searched, so callers that pass a full structure
    set (including OARs) should supply ``roi_types`` to avoid selecting an organ
    that happens to sit nearer the isocentre than the target.

    Centroids are vertex-mean (not area-weighted) averaged over all slices.
    """
    if roi_types is not None:
        wanted = {t.upper() for t in roi_types}
        structures = [s for s in structures if s.roi_type.upper() in wanted]
    best = None
    best_d = np.inf
    for s in structures:
        pts = []
        for z, polys in s.contours.items():
            for poly in polys:
                c2 = polygon_centroid(poly)
                pts.append([c2[0], c2[1], z])
        if not pts:
            continue
        centroid = np.asarray(pts, dtype=float).mean(axis=0)
        d = float(np.linalg.norm(centroid - iso))
        if d < best_d:
            best_d, best = d, centroid
    if best is None:
        raise ValueError("no structure with contours to compute a centroid")
    return best
