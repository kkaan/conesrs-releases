"""Shared, Qt-free view state for every canvas and panel.

One SceneState per window. Panels mutate it; canvases and the scrubber repaint
from it. Every mutator notifies the registered listeners exactly once.
"""
from __future__ import annotations

from typing import Callable


class SceneState:
    def __init__(self):
        self.geom = None
        self.beam_index = 0
        self.sample_index = 0
        self.visible_beams: set[int] = set()
        self.visible_structures: set[str] = set()
        self.fade = True
        self.slab = False
        self.listeners: list[Callable[[], None]] = []

    def _notify(self) -> None:
        for fn in list(self.listeners):
            fn()

    # ---- queries ----------------------------------------------------------
    def n_beams(self) -> int:
        return len(self.geom.beams) if self.geom is not None else 0

    def selected_beam(self):
        return self.geom.beams[self.beam_index] if self.n_beams() else None

    def n_samples(self) -> int:
        beam = self.selected_beam()
        return len(beam.samples) if beam is not None else 0

    def selected_sample(self):
        beam = self.selected_beam()
        if beam is None or not beam.samples:
            return None
        return beam.samples[self.sample_index]

    def readout(self) -> str:
        beam, smp = self.selected_beam(), self.selected_sample()
        if beam is None or smp is None:
            return "Body only — no in-scope beams"
        depth = (f"d {smp.depth_mm:.1f} mm" if smp.depth_mm is not None
                 else "ray missed body")
        return (f"G {smp.gantry:.1f}° · couch {beam.couch_deg:g}° · "
                f"{beam.cone_size_mm:g} mm · {depth} · "
                f"sample {self.sample_index + 1}/{len(beam.samples)}")

    # ---- mutations (each notifies exactly once) ------------------------------
    def set_geometry(self, geom) -> None:
        self.geom = geom
        self.beam_index = 0
        self.sample_index = 0
        self.visible_beams = set(range(self.n_beams()))
        self.visible_structures = (
            {s.name for s in geom.display if s.default_on}
            if geom is not None else set())
        self._notify()

    def select_beam(self, i: int) -> None:
        n = self.n_beams()
        self.beam_index = int(max(0, min(i, n - 1))) if n else 0
        self.sample_index = 0
        if n:
            self.visible_beams.add(self.beam_index)
        self._notify()

    def toggle_beam_visible(self, i: int) -> None:
        if i == self.beam_index or not (0 <= i < self.n_beams()):
            return
        if i in self.visible_beams:
            self.visible_beams.discard(i)
        else:
            self.visible_beams.add(i)
        self._notify()

    def set_sample(self, i: int) -> None:
        n = self.n_samples()
        self.sample_index = int(max(0, min(i, n - 1))) if n else 0
        self._notify()

    def step_sample(self, delta: int) -> None:
        self.set_sample(self.sample_index + delta)

    def next_beam(self) -> None:
        if self.n_beams():
            self.select_beam((self.beam_index + 1) % self.n_beams())

    def set_structure_visible(self, name: str, on: bool) -> None:
        if on:
            self.visible_structures.add(name)
        else:
            self.visible_structures.discard(name)
        self._notify()

    def set_structures_visible(self, names) -> None:
        self.visible_structures = set(names)
        self._notify()

    def set_fade(self, on: bool) -> None:
        self.fade = bool(on)
        self._notify()

    def set_slab(self, on: bool) -> None:
        self.slab = bool(on)
        self._notify()
