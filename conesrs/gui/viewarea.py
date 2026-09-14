"""Central view area: a 1x1 / 2x2 grid of ContourCanvas over an arc scrubber."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QSlider,
                               QToolButton, QVBoxLayout, QWidget)

from conesrs.gui.geomview import ContourCanvas
from conesrs.gui.scene import SceneState

PRESET_TITLES = {"arc": "Along arc axis", "axial": "Axial",
                 "coronal": "Coronal", "sagittal": "Sagittal"}
GRID_PRESETS = ("arc", "axial", "coronal", "sagittal")


class _Tile(QFrame):
    def __init__(self, canvas: ContourCanvas, on_maximise, show_maximise: bool):
        super().__init__()
        self.canvas = canvas
        self.header = QLabel(PRESET_TITLES[canvas.preset])
        self.header.setStyleSheet("padding:2px 6px; font-size:11px;")
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.header)
        head.addStretch(1)
        if show_maximise:
            btn = QToolButton()
            btn.setText("⤢")
            btn.setToolTip("Maximise this view")
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda: on_maximise(canvas.preset))
            head.addWidget(btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(head)
        lay.addWidget(canvas, 1)


class ViewGrid(QWidget):
    layout_changed = Signal(str)

    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.state = state
        self.canvases: list[ContourCanvas] = []
        self.layout_mode = "1x1"
        self._single_preset = "arc"
        self._tiles: list[_Tile] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(2)
        self._build()

    def _clear(self) -> None:
        for tile in self._tiles:
            self._grid.removeWidget(tile)
            self.state.listeners.remove(tile.canvas._on_state)
            tile.setParent(None)
            tile.deleteLater()
        self._tiles = []
        self.canvases = []

    def _build(self) -> None:
        self._clear()
        if self.layout_mode == "2x2":
            for i, preset in enumerate(GRID_PRESETS):
                canvas = ContourCanvas(self.state, preset)
                tile = _Tile(canvas, self.maximise, show_maximise=True)
                self._grid.addWidget(tile, i // 2, i % 2)
                self._tiles.append(tile)
                self.canvases.append(canvas)
        else:
            canvas = ContourCanvas(self.state, self._single_preset)
            tile = _Tile(canvas, self.maximise, show_maximise=False)
            self._grid.addWidget(tile, 0, 0)
            self._tiles.append(tile)
            self.canvases.append(canvas)

    def set_layout(self, mode: str) -> None:
        if mode not in ("1x1", "2x2"):
            raise ValueError(f"unknown layout {mode!r}")
        if mode == self.layout_mode:
            return
        self.layout_mode = mode
        self._build()
        self.layout_changed.emit(mode)

    def maximise(self, preset: str) -> None:
        self._single_preset = preset
        if self.layout_mode == "1x1":
            self.set_preset(preset)
        else:
            self.set_layout("1x1")

    def set_preset(self, name: str) -> None:
        self._single_preset = name
        if self.layout_mode == "1x1":
            self.canvases[0].set_preset(name)
            self._tiles[0].header.setText(PRESET_TITLES[name])

    def active_preset(self) -> str:
        return self._single_preset

    def fit_all(self) -> None:
        for c in self.canvases:
            c.fit()


class ArcScrubber(QWidget):
    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.state = state
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._on_slider)
        self.readout = QLabel()
        # Fixed width so a longer readout never shifts the slider track.
        self.readout.setMinimumWidth(
            self.readout.fontMetrics().horizontalAdvance("G 000.0° · couch 000° · 00.0 mm · d 000.0 mm · sample 000/000"))
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.tick_labels = [QLabel() for _ in range(5)]
        for lab in self.tick_labels:
            lab.setStyleSheet("font-size:10px;")
        ticks = QHBoxLayout()
        ticks.setContentsMargins(6, 0, 6, 0)
        for i, lab in enumerate(self.tick_labels):
            if i:
                ticks.addStretch(1)
            ticks.addWidget(lab)
        track = QVBoxLayout()
        track.setSpacing(0)
        track.addWidget(self.slider)
        track.addLayout(ticks)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.addWidget(QLabel("Arc"))
        lay.addLayout(track, 1)
        lay.addWidget(self.readout)
        self.state.listeners.append(self._sync)
        self._sync()

    def _on_slider(self, value: int) -> None:
        if value != self.state.sample_index:
            self.state.set_sample(value)

    def _sync(self) -> None:
        n = self.state.n_samples()
        beam = self.state.selected_beam()
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, n - 1))
        self.slider.setValue(self.state.sample_index)
        self.slider.setEnabled(n > 1)
        self.slider.blockSignals(False)
        for i, lab in enumerate(self.tick_labels):
            if beam is not None and n:
                g = beam.samples[round(i / 4 * (n - 1))].gantry
                lab.setText(f"G {g:.0f}°")
            else:
                lab.setText("")
        self.readout.setText(self.state.readout())


class ViewArea(QWidget):
    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.state = state
        self.grid = ViewGrid(state)
        self.scrubber = ArcScrubber(state)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.grid, 1)
        lay.addWidget(self.scrubber)
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        # Arrow keys scrub, B cycles beams, wherever focus sits inside the area.
        if ev.key() == Qt.Key_Right:
            self.state.step_sample(1)
        elif ev.key() == Qt.Key_Left:
            self.state.step_sample(-1)
        elif ev.key() == Qt.Key_B:
            self.state.next_beam()
        else:
            super().keyPressEvent(ev)
