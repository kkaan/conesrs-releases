"""Plan facts + model provenance rows, and the unvalidated-model notice."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from conesrs.gui import theme


class ProvenancePanel(QWidget):
    def __init__(self, result):
        super().__init__()
        r = result
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(theme.h2("Plan"))
        lay.addSpacing(4)
        rows = []
        if r.n_fractions is not None:
            rows.append(("Fractions", str(r.n_fractions)))
        if r.cones_used:
            rows.append(("Cones", ", ".join(f"{c:g}" for c in r.cones_used) + " mm"))
        if r.mean_depth_mm is not None:
            rows.append(("Mean depth to isocentre", f"{r.mean_depth_mm:.1f} mm"))
        rows.append(("Beam model", f"{r.model_id} {r.model_version}".strip() or "-"))
        rows.append(("Model validated", "Yes" if r.model_validated else "No"))
        for k, v in rows:
            lay.addWidget(theme.kv_row(k, v))
        if not r.model_validated:
            lay.addSpacing(8)
            lay.addWidget(theme.notice(
                "Unvalidated beam model. Results are provisional and not for clinical use.",
                theme.ERROR))
        for wmsg in r.warnings:
            if wmsg.startswith("UNVALIDATED MODEL"):
                continue   # already shown as the notice above
            lay.addSpacing(6)
            lay.addWidget(theme.notice(wmsg, theme.NEAR))
