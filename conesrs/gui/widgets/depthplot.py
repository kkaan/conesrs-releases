"""Depth-vs-gantry scatter embedded via matplotlib's Qt backend (dark card styling)."""
from __future__ import annotations

from matplotlib import cycler
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from conesrs.gui import theme
from conesrs.report.depthaxes import draw_depth_axes


class DepthPlot(FigureCanvasQTAgg):
    def __init__(self, depth_profile, by_beam=()):
        fig = Figure(figsize=(5.0, 2.4), facecolor=theme.CARD)
        super().__init__(fig)
        ax = fig.add_subplot(111)
        ax.set_prop_cycle(cycler(color=theme.PLOT_CYCLE))
        draw_depth_axes(ax, depth_profile, by_beam)
        _style_dark(ax)
        fig.tight_layout(pad=0.8)
        self.setStyleSheet(f"background: {theme.CARD};")


def _style_dark(ax) -> None:
    ax.set_facecolor(theme.CARD)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.LINE)
    ax.tick_params(colors=theme.MUTED, labelsize=8, length=2, width=0.5)
    ax.xaxis.label.set_color(theme.INK)
    ax.yaxis.label.set_color(theme.INK)
    ax.xaxis.label.set_fontsize(8)
    ax.yaxis.label.set_fontsize(8)
    ax.grid(True, color=theme.LINE, alpha=1.0, linewidth=0.5)
    leg = ax.get_legend()
    if leg is not None:
        for t in leg.get_texts():
            t.set_color(theme.INK)
            t.set_fontsize(7)
