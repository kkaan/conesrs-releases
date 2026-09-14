"""Plan dock: plan facts, beam list (select / Ctrl-click visibility), structures."""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from conesrs.gui.geomview import COL_ENTRY, COL_ENTRY_OTHER, structure_colour
from conesrs.gui.scene import SceneState


def _section_label(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setStyleSheet("font-size:10px; letter-spacing:1px; padding:6px 4px 2px; "
                      "font-weight:600; color:palette(mid);")
    return lab


class PlanFacts(QLabel):
    """Read-only facts about the loaded plan (never typed by the user)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.set_facts(None)

    def set_facts(self, facts: dict | None) -> None:
        if not facts:
            self.setText("<i>No plan loaded</i>")
            return
        iso = ", ".join(f"{float(v):.1f}" for v in facts.get("isocentre", ()))
        rows = (("Patient", facts.get("patient", "")), ("Plan", facts.get("plan", "")),
                ("Machine", facts.get("machine", "")),
                ("Fractions", facts.get("fractions", "")), ("Isocentre", iso))
        cells = "".join(f"<tr><td style='color:gray;padding-right:8px'>{k}</td>"
                        f"<td>{v}</td></tr>" for k, v in rows)
        self.setText(f"<table style='font-size:12px'>{cells}</table>")


class BeamList(QWidget):
    """One row per in-scope beam. Click selects; Ctrl+click toggles visibility."""

    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.state = state
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setToolTip("Click: select beam (drives the scrubber and ray).\n"
                             "Ctrl+click: show / hide this beam's entry points.")
        self.list.viewport().installEventFilter(self)
        self.list.currentRowChanged.connect(self._on_row)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.list)
        self.state.listeners.append(self._render)
        self._render()

    def row_text(self, i: int) -> str:
        return self.list.item(i).text()

    def eventFilter(self, obj, ev):
        if (obj is self.list.viewport() and ev.type() == QEvent.MouseButtonPress
                and ev.modifiers() & Qt.ControlModifier):
            item = self.list.itemAt(ev.position().toPoint())
            if item is not None:
                self.state.toggle_beam_visible(self.list.row(item))
            return True  # swallow: Ctrl+click never changes the selection
        return super().eventFilter(obj, ev)

    def _on_row(self, row: int) -> None:
        if row >= 0 and row != self.state.beam_index:
            self.state.select_beam(row)

    @staticmethod
    def _label(beam) -> str:
        if beam.samples:
            g = f"G {beam.samples[0].gantry:.0f}→{beam.samples[-1].gantry:.0f}"
        else:
            g = "G —"
        return (f"Beam {beam.beam_number} · {beam.cone_size_mm:g} mm · "
                f"couch {beam.couch_deg:g}° · {g} · {beam.mu:.0f} MU")

    def _render(self) -> None:
        geom = self.state.geom
        beams = geom.beams if geom is not None else ()
        self.list.blockSignals(True)
        if self.list.count() != len(beams):
            self.list.clear()
            for _ in beams:
                self.list.addItem(QListWidgetItem())
        for i, beam in enumerate(beams):
            item = self.list.item(i)
            visible = i in self.state.visible_beams
            item.setText(("● " if visible else "○ ") + self._label(beam))
            item.setForeground(QColor(COL_ENTRY if visible else COL_ENTRY_OTHER)
                               if i != self.state.beam_index else self.palette().text())
        if beams:
            self.list.setCurrentRow(self.state.beam_index)
        self.list.blockSignals(False)


class StructureList(QWidget):
    """Filterable, checkable structure rows with colour swatches."""

    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.state = state
        self._syncing = False
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter structures…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _t: self._render())
        self.btn_targets = QPushButton("Targets")
        self.btn_all = QPushButton("All")
        self.btn_none = QPushButton("None")
        for b in (self.btn_targets, self.btn_all, self.btn_none):
            b.setFlat(True)
        self.btn_targets.clicked.connect(lambda: self._quick("targets"))
        self.btn_all.clicked.connect(lambda: self._quick("all"))
        self.btn_none.clicked.connect(lambda: self._quick("none"))
        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item)
        quick = QHBoxLayout()
        quick.setContentsMargins(0, 0, 0, 0)
        for b in (self.btn_targets, self.btn_all, self.btn_none):
            quick.addWidget(b)
        quick.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.filter)
        lay.addLayout(quick)
        lay.addWidget(self.list, 1)
        self.state.listeners.append(self._render)
        self._render()

    def _display(self):
        geom = self.state.geom
        return geom.display if geom is not None else ()

    def _quick(self, which: str) -> None:
        names = set()
        for s in self._display():
            if s.is_body or which == "all" or (which == "targets" and s.default_on):
                names.add(s.name)
        self.state.set_structures_visible(names)

    def _on_item(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        self.state.set_structure_visible(item.data(Qt.UserRole),
                                         item.checkState() == Qt.Checked)

    def _render(self) -> None:
        q = self.filter.text().strip().lower()
        self._syncing = True
        self.list.clear()
        for s in self._display():
            if q and q not in s.name.lower():
                continue
            item = QListWidgetItem(f"■ {s.name}   ·  {s.roi_type.lower()}")
            item.setForeground(QColor(structure_colour(s)))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if s.name in self.state.visible_structures
                               else Qt.Unchecked)
            item.setData(Qt.UserRole, s.name)
            self.list.addItem(item)
        self._syncing = False


class PlanPanel(QWidget):
    def __init__(self, state: SceneState, parent=None):
        super().__init__(parent)
        self.facts = PlanFacts()
        self.beams = BeamList(state)
        self.structures = StructureList(state)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        lay.addWidget(_section_label("Plan"))
        lay.addWidget(self.facts)
        lay.addWidget(_section_label("Beams"))
        lay.addWidget(self.beams)
        lay.addWidget(_section_label("Structures"))
        lay.addWidget(self.structures, 1)
        self.beams.setMaximumHeight(140)
