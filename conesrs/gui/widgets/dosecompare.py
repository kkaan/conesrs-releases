"""Independent vs TPS point (primary) vs sphere (supplementary) dose block.

A 2×2 metric band (the dock is narrow), then the supplementary sphere row and the
tolerance band that produced the flag.
"""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QVBoxLayout, QWidget

from conesrs.engine.tolerance import action_limit_is_provisional, tolerance_bands
from conesrs.gui import theme


def _fmt(v, unit=""):
    return "-" if v is None else f"{v:.2f}{unit}"


def _signed(v):
    return "-" if v is None else f"{v:+.2f}"


class DoseCompare(QWidget):
    def __init__(self, result):
        super().__init__()
        r = result
        self._summary = (
            f"Independent {_fmt(r.d_calc_cgy_per_fx)} cGy/fx | "
            f"TPS point {_fmt(r.d_tps_cgy_per_fx)} cGy/fx "
            f"({_fmt(r.percent_diff, '%')}) [primary] | "
            f"TPS sphere {_fmt(r.d_tps_sphere_cgy_per_fx)} cGy/fx "
            f"@ {_fmt(r.sphere_diameter_mm)} mm ({_fmt(r.percent_diff_sphere, '%')}) "
            f"[supplementary]")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(8)
        mu = f"{r.mu_consistency:.3f}" if r.mu_consistency is not None else "-"
        cards = [
            ("Independent dose", _fmt(r.d_calc_cgy_per_fx), "cGy/fx"),
            ("TPS point dose", _fmt(r.d_tps_cgy_per_fx), "cGy/fx"),
            ("Difference", _signed(r.percent_diff), "%"),
            ("MU consistency", mu, ""),
        ]
        for i, (title, value, unit) in enumerate(cards):
            grid.addWidget(theme.metric(title, value, unit), i // 2, i % 2)
        lay.addLayout(grid)

        sphere = (f"Sphere mean, {_fmt(r.sphere_diameter_mm)} mm dia (supplementary): "
                  f"{_fmt(r.d_tps_sphere_cgy_per_fx)} cGy/fx, difference "
                  f"{_signed(r.percent_diff_sphere)} %.")
        lay.addWidget(theme.label(sphere, "gcMuted"))

        if r.cones_used:
            max_cone = max(r.cones_used)
            review, action = tolerance_bands(max_cone)
            prov = " (action limit provisional)" if action_limit_is_provisional(max_cone) else ""
            lay.addWidget(theme.label(
                f"Tolerance for the largest cone ({max_cone:g} mm): review beyond "
                f"±{review:.1f} %, action beyond ±{action:.1f} %{prov}. The point dose at "
                f"the isocentre drives the result.", "gcMuted"))

    def summary_text(self) -> str:
        return self._summary
