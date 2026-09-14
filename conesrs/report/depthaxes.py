"""Depth-vs-gantry axes drawing shared by the PDF report and the GUI (matplotlib only)."""
from __future__ import annotations


def draw_depth_axes(ax, depth_profile, by_beam=()):
    """Scatter of depth vs gantry, one colour per beam (shared by GUI and PDF).

    Points are not joined: arcs are separate series and a joined line would
    draw a meaningless segment from the end of one arc to the start of the next.
    """
    series = by_beam or ((None, tuple(depth_profile)),)
    for beam_number, pts in series:
        if not pts:
            continue
        label = f"Beam {beam_number}" if beam_number is not None else None
        ax.scatter([g for g, _ in pts], [d for _, d in pts], s=9, label=label)
    if by_beam:
        ax.legend(fontsize=7, frameon=False, ncol=2)
    ax.set_xlabel("Gantry angle (deg)")
    ax.set_ylabel("Depth to iso (mm)")
    ax.set_xlim(0, 360)
    ax.set_xticks(range(0, 361, 60))
    ax.grid(True, alpha=0.3)
