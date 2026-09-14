"""Versioned, checksummed beam-data file format (JSON + SHA-256).

The app loads beam data read-only. The checksum is computed over the canonical
(sorted-key) JSON of the data payload, so any edit to the numbers invalidates
the file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from conesrs.core.dose.beammodel import BeamModel, ConeData

FORMAT_VERSION = 1


def _checksum(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_beam_data(model: BeamModel, path: str | Path,
                   provenance: dict | None = None) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "name": model.name,
        "version": model.version,
        "d_ref": model.d_ref,
        "ssd_cm": model.ssd_cm,
        "ref_depth_cm": model.ref_depth_cm,
        "validated": model.validated,
        "validated_by": model.validated_by,
        "validated_date": model.validated_date,
        "cones": {
            str(size): {
                "output_factor": cone.output_factor,
                "dcf_depths_cm": np.asarray(cone.dcf_depths_cm).tolist(),
                "dcf_values": np.asarray(cone.dcf_values).tolist(),
            }
            for size, cone in model.cones.items()
        },
        "provenance": provenance if provenance is not None else {},
    }
    document = {"checksum": _checksum(payload), "data": payload}
    Path(path).write_text(json.dumps(document, indent=2), encoding="utf-8")


def load_beam_data(path: str | Path) -> BeamModel:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    payload = document["data"]
    if _checksum(payload) != document["checksum"]:
        raise ValueError(f"beam-data checksum mismatch (file tampered?): {path}")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ValueError(
            f"unsupported beam-data format_version "
            f"{payload.get('format_version')!r}, expected {FORMAT_VERSION}"
        )
    cones = {
        float(size): ConeData(
            size_mm=float(size),
            output_factor=c["output_factor"],
            dcf_depths_cm=np.array(c["dcf_depths_cm"], dtype=float),
            dcf_values=np.array(c["dcf_values"], dtype=float),
        )
        for size, c in payload["cones"].items()
    }
    return BeamModel(name=payload["name"], version=payload["version"],
                     d_ref=payload["d_ref"], ssd_cm=payload["ssd_cm"],
                     cones=cones, ref_depth_cm=payload["ref_depth_cm"],
                     validated=payload.get("validated", False),
                     validated_by=payload.get("validated_by", ""),
                     validated_date=payload.get("validated_date", ""))
