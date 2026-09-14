"""Config-driven beam-data build.

A physicist-authored BuildConfig carries every domain decision: which scan is
the canonical PDD per cone, where the water surface sits in scanner Z
(surface_z_mm), the normalisation depth (d0_cm), the SSD, and D_ref. The build
never assumes these. It converts the selected depth scan to a PDD, computes the
DCF, runs the reference-point consistency check, and assembles a BeamModel.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from conesrs.core.dose.beammodel import BeamModel, ConeData
from conesrs.data.asc import Measurement
from conesrs.data.dcf import check_reference_consistency, pdd_to_dcf


@dataclass(frozen=True)
class BuildConfig:
    """Physicist-authored inputs that drive a beam-data build."""

    model_name: str
    version: str
    d0_cm: float                 # PDD normalisation / reference depth
    d_ref: float                 # reference dose per MU (cGy/MU) at d0 at iso
    d_ref_setup: str             # provenance: stated setup of D_ref
    surface_z_mm: float          # scanner Z of the water surface
    ssd_cm: float | None         # None -> read from each scan header
    cones: dict[float, int]      # {cone_size_mm: measurement_index}
    provenance: dict             # detector, protocol, date, builder, ...
    depth_sign: float = 1.0      # depth = depth_sign * (Z - surface_z_mm)

    @classmethod
    def from_dict(cls, d: dict) -> "BuildConfig":
        return cls(
            model_name=d["model_name"], version=d["version"],
            d0_cm=float(d["d0_cm"]), d_ref=float(d["d_ref"]),
            d_ref_setup=d["d_ref_setup"], surface_z_mm=float(d["surface_z_mm"]),
            ssd_cm=(None if d.get("ssd_cm") is None else float(d["ssd_cm"])),
            cones={float(k): int(v) for k, v in d["cones"].items()},
            provenance=d.get("provenance", {}),
            depth_sign=float(d.get("depth_sign", 1.0)),
        )


def measurement_to_pdd(m: Measurement, surface_z_mm: float,
                       depth_sign: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Convert a depth scan to (depths_cm ascending unique, pdd_values)."""
    z = m.points[:, 2]
    dose = m.points[:, 3]
    depth_mm = depth_sign * (z - surface_z_mm)
    # unique + sorted ascending (np.interp needs strictly increasing depths).
    # np.unique keeps the first occurrence's dose for any duplicate rounded
    # depth; averaging would be marginally more principled but is immaterial for
    # a smooth scan. Negative depths (points above surface) are NOT clipped here;
    # clinical depths are positive and BeamModel.dcf range-guards the rest.
    u_depth, idx = np.unique(np.round(depth_mm, 4), return_index=True)
    return u_depth / 10.0, dose[idx]


def build_beam_model(measurements: list[Measurement], opf: dict,
                     config: BuildConfig) -> BeamModel:
    if not config.cones:
        raise ValueError("BuildConfig has no cones to build")
    by_index = {m.index: m for m in measurements}
    cones: dict[float, ConeData] = {}
    ssd_values: list[float] = []
    for size, meas_index in config.cones.items():
        of = opf[size]  # raises KeyError if missing — caller must supply OF
        if meas_index not in by_index:
            raise ValueError(
                f"cone {size} mm references measurement index {meas_index}, "
                "which is not present in the parsed scans"
            )
        m = by_index[meas_index]
        depths_cm, pdd = measurement_to_pdd(m, config.surface_z_mm,
                                            config.depth_sign)
        ssd_cm = config.ssd_cm if config.ssd_cm is not None else m.ssd_mm / 10.0
        ssd_values.append(ssd_cm)
        dcf = pdd_to_dcf(depths_cm, pdd, ssd_cm, config.d0_cm)
        check_reference_consistency(depths_cm, dcf, config.d0_cm)
        cones[size] = ConeData(size_mm=size, output_factor=of,
                               dcf_depths_cm=depths_cm, dcf_values=dcf)
    # All cones come from the same machine, so the SSD must agree across them;
    # a divergence in the header-SSD path would silently corrupt the model.
    if len(set(round(s, 6) for s in ssd_values)) != 1:
        raise ValueError(f"inconsistent SSD across cones: {sorted(set(ssd_values))}")
    return BeamModel(name=config.model_name, version=config.version,
                     d_ref=config.d_ref, ssd_cm=ssd_values[0], cones=cones,
                     ref_depth_cm=config.d0_cm)
