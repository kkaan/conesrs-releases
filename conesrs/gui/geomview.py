"""Contour entry view canvas: QPainter only (no OpenGL, no VTK).

ContourCanvas paints decimated contour rings, beam entry points, the selected
central ray and a true-diameter cone from the shared SceneState. It owns its
own Camera (preset, orbit, zoom); everything else comes from the state.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QKeyEvent, QMouseEvent,
                           QPainter, QPainterPath, QPen, QWheelEvent)
from PySide6.QtWidgets import QWidget

from conesrs.gui.camera import PRESETS, Camera, project
from conesrs.gui.scene import SceneState

GROUND = "#0D1320"
COL_BODY, COL_STRUCT, COL_TARGET = "#7FB3D5", "#E8A33D", "#F2C94C"
COL_ENTRY, COL_ENTRY_OTHER = "#86E36A", "#3D6A3A"
COL_RAY, COL_MISS, COL_CONE = "#FFFFFF", "#F0A83A", "#78C8FF"
COL_ISO, COL_SOURCE, COL_TEXT, COL_GRID = "#E5484D", "#4F8EF7", "#C9D3E2", "#1C2536"
SLAB_MM = 20.0
FADE_BINS = ((15.0, 1.0), (40.0, 0.42), (float("inf"), 0.12))


def structure_colour(s) -> str:
    if s.is_body:
        return COL_BODY
    return COL_TARGET if s.default_on else COL_STRUCT


class ContourCanvas(QWidget):
    activated = Signal()

    def __init__(self, state: SceneState, preset: str = "arc", parent=None):
        super().__init__(parent)
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r}")
        self.setMinimumSize(160, 120)
        self.setFocusPolicy(Qt.StrongFocus)
        self.state = state
        self.camera = Camera(preset=preset)
        self._drag = None
        self._last_beam = None
        self.state.listeners.append(self._on_state)
        self._sync_couch()

    @property
    def preset(self) -> str:
        return self.camera.preset

    # ---- state ------------------------------------------------------------
    def _on_state(self) -> None:
        if self.state.beam_index != self._last_beam:
            self._last_beam = self.state.beam_index
            if self.preset == "arc":
                self.camera.reset_orbit()
        self._sync_couch()
        self.update()

    def _sync_couch(self) -> None:
        beam = self.state.selected_beam()
        if beam is not None:
            self.camera.couch_deg = float(beam.couch_deg)

    def set_preset(self, name: str) -> None:
        if name not in PRESETS:
            raise ValueError(f"unknown preset {name!r}")
        self.camera.preset = name
        self.camera.reset_orbit()
        self._sync_couch()
        self.update()

    def fit(self) -> None:
        self.camera.zoom = 1.0
        self.camera.reset_orbit()
        self.update()

    # ---- input --------------------------------------------------------------
    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self._drag = (ev.position(), self.camera.azimuth, self.camera.elevation)
        self.setFocus()
        self.activated.emit()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._drag is None:
            return
        start, az0, el0 = self._drag
        d = ev.position() - start
        self.camera.azimuth = az0
        self.camera.elevation = el0
        self.camera.orbit(-d.x() * 0.008, d.y() * 0.008)
        self.update()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        self._drag = None

    def wheelEvent(self, ev: QWheelEvent) -> None:
        self.camera.zoom_by(1.1 if ev.angleDelta().y() > 0 else 1 / 1.1)
        self.update()

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key_Right:
            self.state.step_sample(1)
        elif ev.key() == Qt.Key_Left:
            self.state.step_sample(-1)
        elif ev.key() == Qt.Key_B:
            self.state.next_beam()
        else:
            super().keyPressEvent(ev)

    # ---- painting -----------------------------------------------------------
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(GROUND))
        geom = self.state.geom
        if geom is None:
            p.setPen(QColor(COL_TEXT))
            p.drawText(self.rect(), Qt.AlignCenter, "No geometry")
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        scale = min(w, h) / 300.0 * self.camera.zoom
        basis = self.camera.basis()
        iso = np.asarray(geom.iso, dtype=float)

        def proj(pts):
            return project(np.asarray(pts, dtype=float).reshape(-1, 3),
                           iso, basis, scale, w, h)

        self._draw_grid(p, w, h, scale)
        for s in geom.display:
            if s.name in self.state.visible_structures and s.rings.n_rings:
                self._draw_rings(p, s, proj)
        self._draw_entries(p, proj)
        self._draw_selected_ray(p, proj, basis, iso)
        self._draw_markers(p, proj)
        self._draw_triad(p, basis, w, h)
        self._draw_scale_bar(p, scale, w, h)
        p.end()

    def _draw_grid(self, p, w, h, scale) -> None:
        step = 10.0 * scale
        if step < 4:
            return
        p.setPen(QPen(QColor(COL_GRID), 1))
        x = (w / 2.0) % step
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += step
        y = (h / 2.0) % step
        while y < h:
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += step

    def _draw_rings(self, p, s, proj) -> None:
        scr = proj(s.rings.points)
        offsets = s.rings.offsets
        # Depth fade only matters for the body (the one large, enclosing ring set);
        # targets and organs are small and drawn at full alpha.
        bins = FADE_BINS if (self.state.fade and s.is_body) else ((float("inf"), 1.0),)
        paths = [QPainterPath() for _ in bins]
        for r in range(s.rings.n_rings):
            seg = scr[int(offsets[r]):int(offsets[r + 1])]
            closed = np.vstack([seg, seg[:1]])
            depth = np.abs(closed[:, 2])
            slab_ok = depth <= SLAB_MM if self.state.slab else np.ones(len(closed), bool)
            xs, ys = closed[:, 0].tolist(), closed[:, 1].tolist()
            lower = -1.0
            for path, (upper, _alpha) in zip(paths, bins):
                keep = (slab_ok & (depth <= upper) & (depth > lower)).tolist()
                lower = upper
                pen_down = False
                for x, y, ok in zip(xs, ys, keep):
                    if not ok:
                        pen_down = False
                    elif pen_down:
                        path.lineTo(x, y)
                    else:
                        path.moveTo(x, y)
                        pen_down = True
        base = 0.55 if s.is_body else 0.9
        p.setBrush(Qt.NoBrush)
        for path, (_upper, alpha) in zip(paths, bins):
            if path.isEmpty():
                continue
            colour = QColor(structure_colour(s))
            colour.setAlphaF(base * alpha)
            p.setPen(QPen(colour, 1.0 if s.is_body else 1.2))
            p.drawPath(path)

    def _draw_entries(self, p, proj) -> None:
        st = self.state
        p.setPen(Qt.NoPen)
        for bi, beam in enumerate(st.geom.beams):
            if bi not in st.visible_beams:
                continue
            sel = bi == st.beam_index
            hits = [s for s in beam.samples if s.entry is not None]
            if not hits:
                continue
            entries = np.vstack([s.entry for s in hits])
            scr = proj(entries)
            p.setBrush(QBrush(QColor(COL_ENTRY if sel else COL_ENTRY_OTHER)))
            rad = 2.6 if sel else 1.8
            for x, y, _ in scr:
                p.drawEllipse(QPointF(x, y), rad, rad)
            if sel:  # short outward stubs: the fan
                dirs = np.vstack([(s.entry - s.source) / np.linalg.norm(s.entry - s.source)
                                  for s in hits])
                outer = proj(entries - 22.0 * dirs)
                stub = QColor(COL_ENTRY)
                stub.setAlphaF(0.28)
                p.setPen(QPen(stub, 1))
                for (x0, y0, _), (x1, y1, _) in zip(scr, outer):
                    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
                p.setPen(Qt.NoPen)

    def _draw_selected_ray(self, p, proj, basis, iso) -> None:
        beam, smp = self.state.selected_beam(), self.state.selected_sample()
        if beam is None or smp is None:
            return
        src = np.asarray(smp.source, dtype=float)
        d = iso - src
        d /= np.linalg.norm(d)
        far = iso - 260.0 * d                      # clipped ray start
        past = iso + 30.0 * d
        a, b = proj(far)[0], proj(past)[0]
        hit = smp.entry is not None
        pen = QPen(QColor(COL_RAY if hit else COL_MISS), 1.6)
        if not hit:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
        if hit:
            n = basis[0]
            side = np.cross(d, n)
            norm = np.linalg.norm(side)
            if norm > 1e-9:
                side /= norm
                r = beam.cone_size_mm / 2.0
                e = np.asarray(smp.entry, dtype=float)
                quad = proj(np.vstack([e + side * r, past + side * r,
                                       past - side * r, e - side * r]))
                path = QPainterPath(QPointF(quad[0, 0], quad[0, 1]))
                for x, y, _ in quad[1:]:
                    path.lineTo(x, y)
                path.closeSubpath()
                fill = QColor(COL_CONE)
                fill.setAlphaF(0.10)
                p.setPen(QPen(QColor(COL_CONE), 1))
                p.setBrush(QBrush(fill))
                p.drawPath(path)
            pe = proj(smp.entry)[0]
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(COL_ENTRY), 1.5))
            p.drawEllipse(QPointF(pe[0], pe[1]), 6, 6)
            p.setPen(QColor(COL_TEXT))
            p.setFont(QFont("Consolas", 9))
            p.drawText(QPointF(pe[0] + 10, pe[1] - 8), f"d = {smp.depth_mm:.1f} mm")
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(COL_SOURCE)))
        p.drawEllipse(QPointF(a[0], a[1]), 4, 4)
        p.setPen(QColor(COL_TEXT))
        p.setFont(QFont("Consolas", 9))
        p.drawText(QPointF(a[0] + 8, a[1] + 4),
                   f"→ source  G {smp.gantry:.0f}°  T {beam.couch_deg:.0f}°")

    def _draw_markers(self, p, proj) -> None:
        geom = self.state.geom
        if geom.target is not None:
            t = proj(geom.target)[0]
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(COL_TARGET)))
            p.drawEllipse(QPointF(t[0], t[1]), 3, 3)
        c = proj(geom.iso)[0]
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(COL_ISO), 1.5))
        p.drawLine(QPointF(c[0] - 8, c[1]), QPointF(c[0] + 8, c[1]))
        p.drawLine(QPointF(c[0], c[1] - 8), QPointF(c[0], c[1] + 8))
        p.drawEllipse(QPointF(c[0], c[1]), 4, 4)

    def _draw_triad(self, p, basis, w, h) -> None:
        n, r, u = basis
        ox, oy, L = w - 46, h - 40, 22.0
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        for label, axis, col in (("L", (1, 0, 0), "#E57373"), ("P", (0, 1, 0), "#81C784"),
                                 ("S", (0, 0, 1), "#64B5F6")):
            v = np.asarray(axis, dtype=float)
            x, y = float(v @ r) * L, -float(v @ u) * L
            p.setPen(QPen(QColor(col), 1.5))
            p.drawLine(QPointF(ox, oy), QPointF(ox + x, oy + y))
            p.drawText(QPointF(ox + x * 1.35 - 3, oy + y * 1.35 + 4), label)

    def _draw_scale_bar(self, p, scale, w, h) -> None:
        bar = 50.0 * scale
        p.setPen(QPen(QColor("#8FA0B8"), 1.5))
        p.drawLine(QPointF(w - 30 - bar, h - 70), QPointF(w - 30, h - 70))
        p.setFont(QFont("Consolas", 8))
        p.drawText(QPointF(w - 30 - bar, h - 75), "50 mm")
