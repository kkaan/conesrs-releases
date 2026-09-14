"""Core integration: join geometry depths and dosimetry at the seam.

This is the ONE place where geometry and dosimetry meet (design spec §3.1):
    D_calc = sum_i [ MU_i * D_ref * OF(c_i) * DCF(c_i, d_i) ]
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from conesrs.core.dose.beammodel import BeamModel
from conesrs.core.dose.dosecalc import DoseSample, compute_dose
from conesrs.core.geometry.depth import ArcSpec, DepthTrace, trace_arc
from conesrs.core.geometry.surface import Surface


@dataclass(frozen=True)
class CoreDoseResult:
    """Result of the independent core dose calculation.

    NOTE: `frozen=True` does not make the `traces` list immutable; treat this as
    a read-only value object and do not mutate `traces` in place.
    """
    dose_cgy: float
    traces: list[DepthTrace]
    mean_depth_mm: float


def compute_independent_dose(model: BeamModel, arcs: list[ArcSpec],
                             iso: np.ndarray, surface: Surface,
                             step_deg: float = 2.0,
                             sad: float = 1000.0) -> CoreDoseResult:
    all_traces: list[DepthTrace] = []
    samples: list[DoseSample] = []
    for arc in arcs:
        if arc.cone_size_mm is None:
            raise ValueError(f"arc has no cone_size_mm: {arc}")
        traces = trace_arc(arc, iso, surface, step_deg, sad)
        all_traces.extend(traces)
        samples.extend(
            DoseSample(mu=t.mu, depth_mm=t.depth_mm, cone_size_mm=arc.cone_size_mm)
            for t in traces
        )
    dose = compute_dose(model, samples)

    total_mu = sum(t.mu for t in all_traces)
    mean_depth = (
        sum(t.mu * t.depth_mm for t in all_traces) / total_mu
        if total_mu else 0.0
    )
    return CoreDoseResult(dose_cgy=dose, traces=all_traces,
                          mean_depth_mm=mean_depth)
