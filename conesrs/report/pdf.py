"""Per-plan PDF report (reportlab) with an embedded depth-vs-gantry plot.

The only module importing reportlab/matplotlib. Renders the frozen
PlanCheckResult; timestamp is injected by the caller so this stays deterministic.

Visual language follows the GenesisCare Physics design system (the Annual QA
Dashboard tokens): white paper, a barely-there green grid, one brand green,
fine grey rules, 8 px corners, no shadows, capsule pills for status only,
uppercase reserved for eyebrows / metric labels / status chips.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless, no display

from conesrs.report.depthaxes import draw_depth_axes  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib.colors import HexColor  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.utils import ImageReader, simpleSplit  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from conesrs.engine.result import PlanCheckResult
from conesrs.engine.tolerance import action_limit_is_provisional, tolerance_bands

# ---------------------------------------------------------------------------
# Design tokens (colors_and_type.css)
# ---------------------------------------------------------------------------
GREEN = HexColor("#00a869")        # primary brand
GREEN_DEEP = HexColor("#008f5a")   # pass text on soft bg
GREEN_DARK = HexColor("#138f5b")   # eyebrow, dark surfaces
GREEN_SOFT = HexColor("#e8f7f0")   # pass pill background
GREEN_LINE = HexColor("#9edfc5")   # pass pill border
GREEN_EDGE = HexColor("#b9e8d3")   # notice border

INK_STRONG = HexColor("#333438")   # headings, primary text
INK = HexColor("#4f4f53")          # body text
MUTED = HexColor("#6a6b71")        # captions, secondary text
LINE = HexColor("#d9d9d9")         # borders, dividers
BAND = HexColor("#f3f3f3")         # table header
BAND_SOFT = HexColor("#fbfbfb")    # list-row bg
SURFACE = HexColor("#ffffff")

DANGER = HexColor("#b93a31")
DANGER_SOFT = HexColor("#ffe9e5")
DANGER_LINE = HexColor("#efb4aa")

WARN_TEXT = HexColor("#75520f")
WARN_BG = HexColor("#fff5df")
WARN_LINE = HexColor("#f0cf8a")

_GRID_ALPHA = 0.035
_GRID_STEP = 24.0        # 32 css px at 96 dpi = 24 pt
_RADIUS = 6.0            # 8 css px
_BORDER = 0.75

# Type scale (rem → pt at 16px root, ×0.75)
FS_EYEBROW = 9.0     # 0.75rem, uppercase, tracked
FS_MICRO = 9.0       # 0.76rem, table headers, chips
FS_SMALL = 9.5       # 0.78rem, metric labels
FS_BODY = 10.5       # 0.9rem
FS_H2 = 13.0         # 1.1rem
FS_METRIC = 19.0     # 1.6rem
FS_DISPLAY = 26.0    # clamp(1.8rem … 3.6rem) — the low end suits A4

# Pill kinds: (background, border, text)
_PILL = {
    "pass": (GREEN_SOFT, GREEN_LINE, GREEN_DEEP),
    "near": (WARN_BG, WARN_LINE, WARN_TEXT),
    "fail": (DANGER_SOFT, DANGER_LINE, DANGER),
    "review": (BAND, LINE, INK),
    "error": (BAND, DANGER_LINE, DANGER),
}
_STATUS_KIND = {"PASS": "pass", "REVIEW": "near", "ACTION": "fail",
                "REJECTED": "review", "ERROR": "error"}
_NOTICE = {  # (background, border, text)
    "info": (SURFACE, GREEN_EDGE, INK),
    "warn": (WARN_BG, WARN_LINE, WARN_TEXT),
    "error": (DANGER_SOFT, DANGER_LINE, DANGER),
}

# Plot series: brand green first, then neutrals; never a second hue for decoration.
_PLOT_CYCLE = ["#00a869", "#4f4f53", "#138f5b", "#6a6b71", "#9edfc5", "#b93a31",
               "#333438", "#f0cf8a"]


# ---------------------------------------------------------------------------
# Fonts: Aptos → Inter → Segoe UI → Tahoma (the system's own stack), else Helvetica.
# ---------------------------------------------------------------------------
_FONTS: tuple[str, str] | None = None
_FONT_STACK = (
    ("Aptos", "aptos.ttf", "aptos-bold.ttf"),
    ("Inter", "Inter-Regular.ttf", "Inter-Bold.ttf"),
    ("SegoeUI", "segoeui.ttf", "segoeuib.ttf"),
    ("Tahoma", "tahoma.ttf", "tahomabd.ttf"),
)


def _font_dirs() -> list[Path]:
    dirs = []
    for env, sub in (("WINDIR", "Fonts"), ("LOCALAPPDATA", "Microsoft/Windows/Fonts")):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / sub)
    dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
             Path.home() / ".fonts", Path("/Library/Fonts")]
    return dirs


def _fonts() -> tuple[str, str]:
    """Return (regular, bold) font names, registering a system TTF pair if found."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    _FONTS = ("Helvetica", "Helvetica-Bold")
    for family, reg, bold in _FONT_STACK:
        for d in _font_dirs():
            if (d / reg).exists() and (d / bold).exists():
                try:
                    pdfmetrics.registerFont(TTFont(family, str(d / reg)))
                    pdfmetrics.registerFont(TTFont(family + "-Bold", str(d / bold)))
                except Exception:  # unreadable font file → keep looking
                    continue
                _FONTS = (family, family + "-Bold")
                return _FONTS
    return _FONTS


def _plot_font_family() -> list[str]:
    fam = _fonts()[0]
    names = {"Aptos": "Aptos", "Inter": "Inter", "SegoeUI": "Segoe UI", "Tahoma": "Tahoma"}
    return [names[fam], "DejaVu Sans"] if fam in names else ["DejaVu Sans"]


# ---------------------------------------------------------------------------
# Formatting (numbers always with their unit; decimals are honest)
# ---------------------------------------------------------------------------
def _status_text(result: PlanCheckResult) -> str:
    if result.status == "ACCEPTED":
        return result.tolerance_flag or "ACCEPTED"
    return result.status


def _cones_text(cones) -> str:
    return ", ".join(f"{c:g}" for c in cones) + " mm" if cones else "-"


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x:+.2f} %"


def _dose(x: float | None) -> str:
    return "-" if x is None else f"{x:.2f} cGy/fx"


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------
class _Page:
    """Cursor-based single-column layout with automatic page breaks."""

    def __init__(self, c: canvas.Canvas, result: PlanCheckResult, timestamp: str):
        self.c = c
        self.result = result
        self.timestamp = timestamp
        self.w, self.h = A4
        self.margin = 16 * mm
        self.x0 = self.margin
        self.x1 = self.w - self.margin
        self.cw = self.x1 - self.x0
        self.bottom = 18 * mm
        self.page = 0
        self.y = 0.0
        self.regular, self.bold = _fonts()
        self._begin_page()

    # -- page chrome --------------------------------------------------------
    def _begin_page(self):
        self.page += 1
        self._background()
        self._footer()
        self.y = self.h - self.margin

    def _background(self):
        c = self.c
        c.saveState()
        c.setFillColor(SURFACE)
        c.rect(0, 0, self.w, self.h, fill=1, stroke=0)
        c.setStrokeColor(GREEN)
        c.setStrokeAlpha(_GRID_ALPHA)
        c.setLineWidth(0.75)
        x = 0.0
        while x <= self.w:
            c.line(x, 0, x, self.h)
            x += _GRID_STEP
        c.restoreState()

    def _footer(self):
        c = self.c
        y = self.bottom - 6 * mm
        c.setStrokeColor(LINE)
        c.setLineWidth(_BORDER)
        c.line(self.x0, y + 4 * mm, self.x1, y + 4 * mm)
        r = self.result
        model = f"Beam model {r.model_id or '-'} {r.model_version}".rstrip()
        left = f"conesrs  ·  Cone-SRS secondary MU check  ·  {model}"
        c.setFont(self.regular, 7.5)
        c.setFillColor(MUTED)
        c.drawString(self.x0, y, left)
        c.drawRightString(self.x1, y, f"Page {self.page}")

    def need(self, height: float):
        if self.y - height < self.bottom:
            self.c.showPage()
            self._begin_page()

    def gap(self, dy: float):
        self.y -= dy

    # -- text ---------------------------------------------------------------
    def text(self, x, y, s, *, size=FS_BODY, bold=False, color=INK, align="left",
             tracking=0.0):
        c = self.c
        c.setFont(self.bold if bold else self.regular, size)
        c.setFillColor(color)
        if tracking:
            t = c.beginText()
            t.setTextOrigin(x, y)
            t.setCharSpace(tracking)
            t.textLine(s)
            c.drawText(t)
        elif align == "right":
            c.drawRightString(x, y, s)
        elif align == "center":
            c.drawCentredString(x, y, s)
        else:
            c.drawString(x, y, s)

    def width(self, s, size, bold=False):
        return pdfmetrics.stringWidth(s, self.bold if bold else self.regular, size)

    def wrapped(self, x, y, w, s, *, size=FS_BODY, bold=False, color=INK, leading=None):
        """Draw wrapped text top-down from baseline y; return the baseline after it."""
        leading = leading or size * 1.35
        font = self.bold if bold else self.regular
        for line in simpleSplit(s, font, size, w):
            self.text(x, y, line, size=size, bold=bold, color=color)
            y -= leading
        return y

    def wrapped_height(self, w, s, *, size=FS_BODY, bold=False, leading=None):
        leading = leading or size * 1.35
        font = self.bold if bold else self.regular
        return len(simpleSplit(s, font, size, w)) * leading

    def eyebrow(self, x, y, s, color=GREEN_DARK):
        self.text(x, y, s.upper(), size=FS_EYEBROW, bold=True, color=color,
                  tracking=FS_EYEBROW * 0.08)

    def h2(self, s):
        self.need(FS_H2 * 2)
        self.text(self.x0, self.y - FS_H2, s, size=FS_H2, bold=True, color=INK_STRONG)
        self.y -= FS_H2 * 1.9

    # -- shapes -------------------------------------------------------------
    def card(self, x, y_top, w, h, *, fill=SURFACE, border=LINE):
        c = self.c
        c.setFillColor(fill)
        c.setStrokeColor(border)
        c.setLineWidth(_BORDER)
        c.roundRect(x, y_top - h, w, h, _RADIUS, fill=1, stroke=1)

    def pill(self, x, y_mid, label, kind, *, size=FS_MICRO, align="left"):
        """Capsule status chip. Returns its width."""
        bg, border, fg = _PILL[kind]
        label = label.upper()
        tracking = size * 0.02
        tw = self.width(label, size, bold=True) + tracking * len(label)
        padx, pady = size * 0.9, size * 0.55
        w, h = tw + 2 * padx, size + 2 * pady
        if align == "right":
            x -= w
        c = self.c
        c.setFillColor(bg)
        c.setStrokeColor(border)
        c.setLineWidth(_BORDER)
        c.roundRect(x, y_mid - h / 2, w, h, h / 2, fill=1, stroke=1)
        self.text(x + padx, y_mid - size * 0.36, label, size=size, bold=True,
                  color=fg, tracking=tracking)
        return w

    def notice(self, s, kind="info"):
        """Full-width notice box; full sentences ending with periods."""
        bg, border, fg = _NOTICE[kind]
        pad = 9
        inner = self.cw - 2 * pad
        th = self.wrapped_height(inner, s, size=FS_SMALL)
        h = th + 2 * pad - FS_SMALL * 0.35
        self.need(h + 6)
        self.card(self.x0, self.y, self.cw, h, fill=bg, border=border)
        self.wrapped(self.x0 + pad, self.y - pad - FS_SMALL * 0.8, inner, s,
                     size=FS_SMALL, color=fg)
        self.y -= h + 6

    def metric(self, x, y_top, w, h, label, value, unit=""):
        self.card(x, y_top, w, h)
        pad = 10
        self.text(x + pad, y_top - pad - FS_SMALL * 0.8, label.upper(), size=FS_SMALL,
                  bold=True, color=MUTED, tracking=FS_SMALL * 0.02)
        vy = y_top - h + pad + 2
        self.text(x + pad, vy, value, size=FS_METRIC, bold=True, color=INK_STRONG)
        if unit:
            vx = x + pad + self.width(value, FS_METRIC, bold=True) + 4
            self.text(vx, vy, unit, size=FS_SMALL, color=MUTED)

    def table(self, cols, rows, *, x=None, w=None, header=True):
        """cols: [(title, width_fraction, align)]; rows: list of cell lists.

        A cell is a str, or a tuple ("pill", label, kind). Sticky-band header,
        row separators only — no vertical rules.
        """
        x = self.x0 if x is None else x
        w = self.cw if w is None else w
        pad = 8
        hh = FS_MICRO + 2 * pad - 2
        rh = FS_BODY + 2 * pad
        self.need(hh + rh)
        widths = [w * f for _, f, _ in cols]
        c = self.c
        if header:
            c.setFillColor(BAND)
            c.setStrokeColor(LINE)
            c.setLineWidth(_BORDER)
            c.rect(x, self.y - hh, w, hh, fill=1, stroke=0)
            c.line(x, self.y - hh, x + w, self.y - hh)
            cx = x
            for (title, _, align), cw_ in zip(cols, widths):
                tx = cx + cw_ - pad if align == "right" else cx + pad
                self.text(tx, self.y - hh + pad - 1, title.upper(), size=FS_MICRO,
                          bold=True, color=MUTED, align=align)
                cx += cw_
            self.y -= hh
        for row in rows:
            self.need(rh)
            cx = x
            base = self.y - rh + pad
            for cell, (_, _, align), cw_ in zip(row, cols, widths):
                if isinstance(cell, tuple) and cell[0] == "pill":
                    px = cx + cw_ - pad if align == "right" else cx + pad
                    self.pill(px, self.y - rh / 2, cell[1], cell[2], align=align)
                else:
                    tx = cx + cw_ - pad if align == "right" else cx + pad
                    self.text(tx, base, str(cell), size=FS_BODY, color=INK, align=align)
                cx += cw_
            c.setStrokeColor(LINE)
            c.setLineWidth(_BORDER)
            c.line(x, self.y - rh, x + w, self.y - rh)
            self.y -= rh

    def kv_table(self, pairs, *, x=None, w=None):
        """Two-column facts list: muted label left, ink value right; separators only."""
        x = self.x0 if x is None else x
        w = self.cw if w is None else w
        pad = 6
        rh = FS_BODY + 2 * pad
        c = self.c
        for k, v in pairs:
            self.need(rh)
            base = self.y - rh + pad + 1
            self.text(x, base, k, size=FS_SMALL, color=MUTED)
            self.text(x + w, base, str(v), size=FS_BODY, color=INK_STRONG, align="right")
            c.setStrokeColor(LINE)
            c.setLineWidth(_BORDER)
            c.line(x, self.y - rh, x + w, self.y - rh)
            self.y -= rh


# ---------------------------------------------------------------------------
# Depth plot (matplotlib, styled to the same tokens)
# ---------------------------------------------------------------------------
def _depth_plot_png(depth_profile, by_beam=(), *, figsize=(6.6, 2.5)) -> bytes:
    rc = {
        "font.family": _plot_font_family(),
        "font.size": 12,
        "axes.edgecolor": "#d9d9d9",
        "axes.labelcolor": "#4f4f53",
        "xtick.color": "#6a6b71",
        "ytick.color": "#6a6b71",
        "axes.prop_cycle": matplotlib.cycler(color=_PLOT_CYCLE),
        "legend.fontsize": 10,
        "axes.labelsize": 12,
    }
    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=figsize)
        draw_depth_axes(ax, depth_profile, by_beam)
        ax.grid(True, color="#d9d9d9", alpha=1.0, linewidth=0.5)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(length=2, width=0.5)
        leg = ax.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                t.set_color("#4f4f53")
        buf = io.BytesIO()
        fig.tight_layout(pad=0.6)
        fig.savefig(buf, format="png", dpi=200)
        plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _draw_header(p: _Page):
    r = p.result
    label = _status_text(r)
    kind = _STATUS_KIND.get(label, "review")

    # Eyebrow → display lockup, status capsule on the right.
    p.eyebrow(p.x0, p.y - FS_EYEBROW, "Cone-SRS secondary MU check")
    p.y -= FS_EYEBROW + 8
    title = f"Plan {r.plan_label or '-'}"
    p.text(p.x0, p.y - FS_DISPLAY * 0.78, title, size=FS_DISPLAY, bold=True,
           color=INK_STRONG)
    p.pill(p.x1, p.y - FS_DISPLAY * 0.42, label, kind, size=12.0, align="right")
    p.y -= FS_DISPLAY * 0.95 + 6

    facts = [f"Patient {r.patient_id or '-'}", f"Machine {r.machine or '-'}"]
    if p.timestamp:
        facts.append(f"Checked {p.timestamp}")
    p.text(p.x0, p.y - FS_BODY, "  ·  ".join(facts), size=FS_BODY, color=MUTED)
    p.y -= FS_BODY + 10

    p.c.setStrokeColor(LINE)
    p.c.setLineWidth(_BORDER)
    p.c.line(p.x0, p.y, p.x1, p.y)
    p.y -= 14


def _draw_accepted(p: _Page):
    r = p.result
    flag = r.tolerance_flag or "ACCEPTED"
    kind = _STATUS_KIND.get(flag, "review")

    # 4-up metric band
    gap = 8
    n = 4
    mw = (p.cw - gap * (n - 1)) / n
    mh = 52
    p.need(mh)
    mu = f"{r.mu_consistency:.3f}" if r.mu_consistency is not None else "-"
    metrics = [
        ("Independent dose", f"{r.d_calc_cgy_per_fx:.2f}", "cGy/fx"),
        ("TPS point dose", f"{r.d_tps_cgy_per_fx:.2f}", "cGy/fx"),
        ("Difference", f"{r.percent_diff:+.2f}", "%"),
        ("MU consistency", mu, ""),
    ]
    for i, (lab, val, unit) in enumerate(metrics):
        p.metric(p.x0 + i * (mw + gap), p.y, mw, mh, lab, val, unit)
    p.y -= mh + 16

    # Dose comparison table
    p.h2("Dose comparison")
    cols = [("Quantity", 0.42, "left"), ("TPS", 0.17, "right"),
            ("Independent", 0.17, "right"), ("Difference", 0.13, "right"),
            ("Result", 0.11, "right")]
    sphere_label = "Sphere mean at isocentre (supplementary)"
    if r.sphere_diameter_mm is not None:
        sphere_label = f"Sphere mean, {r.sphere_diameter_mm:.1f} mm dia (supplementary)"
    rows = [
        ["Point dose at isocentre (primary)", _dose(r.d_tps_cgy_per_fx),
         _dose(r.d_calc_cgy_per_fx), _pct(r.percent_diff), ("pill", flag, kind)],
        [sphere_label, _dose(r.d_tps_sphere_cgy_per_fx), _dose(r.d_calc_cgy_per_fx),
         _pct(r.percent_diff_sphere), "-"],
    ]
    p.table(cols, rows)
    if r.cones_used:
        max_cone = max(r.cones_used)
        review, action = tolerance_bands(max_cone)
        prov = " (action limit provisional)" if action_limit_is_provisional(max_cone) else ""
        note = (f"Tolerance band for the largest cone ({max_cone:g} mm): review beyond "
                f"±{review:.1f} %, action beyond ±{action:.1f} %{prov}. "
                f"The point dose drives the result; the sphere mean is context only.")
        p.y -= 6
        p.y = p.wrapped(p.x0, p.y - FS_SMALL, p.cw, note, size=FS_SMALL, color=MUTED)
    p.y -= 10

    # Plan facts (left) + depth plot card (right)
    left_w = p.cw * 0.36
    right_x = p.x0 + left_w + 14
    right_w = p.x1 - right_x
    plot_h = right_w * (2.5 / 6.6)
    card_h = plot_h + FS_H2 + 22
    p.need(card_h)
    top = p.y

    p.h2("Plan")
    p.kv_table([
        ("Fractions", r.n_fractions if r.n_fractions is not None else "-"),
        ("Cones", _cones_text(r.cones_used)),
        ("Mean depth to isocentre",
         f"{r.mean_depth_mm:.1f} mm" if r.mean_depth_mm is not None else "-"),
        ("Beam model", f"{r.model_id} {r.model_version}".strip() or "-"),
        ("Model validated", "Yes" if r.model_validated else "No"),
    ], w=left_w)
    left_bottom = p.y

    p.card(right_x, top, right_w, card_h)
    p.text(right_x + 10, top - 10 - FS_H2 * 0.8, "Depth to isocentre vs gantry angle",
           size=FS_H2 * 0.85, bold=True, color=INK_STRONG)
    img = ImageReader(io.BytesIO(_depth_plot_png(r.depth_profile, r.depth_profile_by_beam)))
    p.c.drawImage(img, right_x + 6, top - card_h + 6, width=right_w - 12,
                  height=plot_h, preserveAspectRatio=True, anchor="s", mask="auto")
    p.y = min(left_bottom, top - card_h) - 14


def _draw_not_checked(p: _Page):
    r = p.result
    if r.status == "REJECTED":
        lead = "Not checked. This plan is outside the tool's scope, so no dose was computed."
        detail = r.reject_reason or "-"
        kind = "warn"
    else:
        lead = "Not checked. The tool failed while processing this plan."
        detail = r.error_detail or "-"
        kind = "error"
    p.y = p.wrapped(p.x0, p.y - FS_BODY, p.cw, lead, size=FS_BODY, color=INK_STRONG,
                    bold=True)
    p.y -= 6
    p.h2("Reason")
    p.notice(detail if detail.endswith(".") else detail + ".", kind)
    p.y -= 4
    if r.model_id:
        facts = [("Beam model", f"{r.model_id} {r.model_version}".strip()),
                 ("Model validated", "Yes" if r.model_validated else "No")]
        if r.cones_used:
            facts.insert(1, ("Cones", _cones_text(r.cones_used)))
        p.h2("Plan")
        p.kv_table(facts, w=p.cw * 0.5)
        p.y -= 14


def _draw_notices(p: _Page):
    r = p.result
    items = []
    if r.model_id and not r.model_validated:
        items.append(("Unvalidated beam model. Results are provisional and not for "
                      "clinical use.", "error"))
    for wmsg in r.warnings:
        msg = wmsg.strip()
        if msg.startswith("UNVALIDATED MODEL"):
            continue   # the red notice above already says this
        items.append((msg if msg.endswith(".") else msg + ".", "warn"))
    if not items:
        return
    p.h2("Notices")
    for text, kind in items:
        p.notice(text, kind)


def write_pdf(result: PlanCheckResult, path: str | Path, *, timestamp: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Cone-SRS secondary MU check - {result.plan_label or 'plan'}")
    c.setAuthor("conesrs")
    p = _Page(c, result, timestamp)

    _draw_header(p)
    if result.status == "ACCEPTED":
        _draw_accepted(p)
    else:
        _draw_not_checked(p)
    _draw_notices(p)

    c.showPage()
    c.save()
