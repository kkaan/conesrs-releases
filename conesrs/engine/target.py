"""Engine-level SRS target identification by clinical NAME convention.

WHY this exists separately from ``conesrs.core.geometry.structures``:
real RTSTRUCTs (observed in the Aktina export) set every ROI's
``RTROIInterpretedType`` to ORGAN/EXTERNAL/MARKER, so the PTV/GTV identity is
carried ONLY in the structure NAME (e.g. ``PTV1-Right cerebellar``,
``GTV1-...``, ``TotalPTV``). A pure ``roi_type`` filter therefore selects
nothing and the plan rejects wrongly. This selector treats a structure as a
target candidate when EITHER its interpreted type is PTV/GTV OR its name
contains "PTV"/"GTV" (case-insensitive substring), then returns the candidate
whose vertex-mean centroid is nearest the isocentre.
"""
from __future__ import annotations

import numpy as np

from conesrs.core.geometry.polygon import polygon_centroid
from conesrs.core.geometry.structures import RawStructure


def _is_target_candidate(s: RawStructure) -> bool:
    if s.roi_type.upper() in {"PTV", "GTV"}:
        return True
    name = s.name.upper()
    return "PTV" in name or "GTV" in name


def select_target_centroid(structures: list[RawStructure],
                           iso: np.ndarray) -> np.ndarray:
    """Centroid (3,) of the PTV/GTV target nearest the isocentre.

    A structure is a target candidate if its ``roi_type`` is PTV/GTV OR its
    ``name`` contains "PTV"/"GTV" (case-insensitive). Among candidates, each
    structure's vertex-mean centroid (averaged over every contour vertex on
    every slice) is computed and the one nearest ``iso`` (a numpy (3,) array)
    is returned.

    Raises ``ValueError("no PTV/GTV target structure with contours found")``
    when there are no candidates, or none of them carry contours. The engine
    orchestrator converts this into a clean REJECT.
    """
    candidates = [s for s in structures if _is_target_candidate(s)]
    best = None
    best_d = np.inf
    for s in candidates:
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
        raise ValueError("no PTV/GTV target structure with contours found")
    return best
