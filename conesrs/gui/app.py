"""PySide6 workspace window. PySide6 is imported only under conesrs.gui.

Layout (Monaco / Eclipse habits): menu bar + toolbar on top, Plan dock on the
left (facts, beams, structures), contour view(s) with the arc scrubber in the
centre, Check dock on the right, and a status bar showing only the beam model
the loaded plan uses.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QLabel, QMainWindow, QMessageBox,
                               QToolBar)

from conesrs.config.machines import MachineConfig
from conesrs.dicomio.matching import match_plan_file
from conesrs.dicomio.rtdose import parse_rtdose
from conesrs.dicomio.rtplan import parse_rtplan
from conesrs.dicomio.rtstruct import parse_rtstruct
from conesrs.engine.batch import check_plan_set
from conesrs.engine.validate import prevalidate, resolve_model_for_plan
from conesrs.engine.viewgeom import build_view_geometry
from conesrs.gui.checkpanel import CheckPanel
from conesrs.gui.planpanel import PlanPanel
from conesrs.gui.scene import SceneState
from conesrs.gui.single.presenter import Deps, SingleCheckPresenter
from conesrs.gui.statuschip import ModelChip, ModelsDialog
from conesrs.gui.viewarea import PRESET_TITLES, ViewArea
from conesrs.gui.worker import make_qt_scheduler

_TITLE = "Cone SRS — Secondary MU Check"


def _single_deps(config: MachineConfig) -> Deps:
    def prepare(planset):
        plan = parse_rtplan(planset.plan_path, with_mlc=True)
        structures = parse_rtstruct(planset.struct_path).structures
        dose = parse_rtdose(planset.dose_path)
        model, _issue = resolve_model_for_plan(plan, config)
        return plan, structures, dose, model

    def run(planset):
        return check_plan_set(planset, config)

    return Deps(match=match_plan_file, prepare=prepare, prevalidate=prevalidate,
                run=run, schedule=make_qt_scheduler(),
                build_geometry=build_view_geometry)


class MainWindow(QMainWindow):
    def __init__(self, config: MachineConfig | None = None, deps: Deps | None = None):
        super().__init__()
        self.setWindowTitle(_TITLE)
        self.resize(1400, 860)
        self.config = config or MachineConfig.load_default()
        self.presenter = SingleCheckPresenter(deps or _single_deps(self.config))
        self.state = SceneState()
        self._bound_geom_id = id(None)

        self.check_panel = CheckPanel(self.presenter)
        self.plan_panel = PlanPanel(self.state)
        self.view_area = ViewArea(self.state)
        self.setCentralWidget(self.view_area)

        self.plan_dock = QDockWidget("Plan", self)
        self.plan_dock.setObjectName("planDock")
        self.plan_dock.setWidget(self.plan_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.plan_dock)
        self.check_dock = QDockWidget("Check", self)
        self.check_dock.setObjectName("checkDock")
        self.check_dock.setWidget(self.check_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.check_dock)
        self._docks_sized = False

        self.model_chip = ModelChip()
        self.statusBar().addWidget(self.model_chip)
        self.statusBar().addWidget(QLabel("Arc step 2° · Sphere 2 mm"))
        self._status_right = QLabel()
        self.statusBar().addPermanentWidget(self._status_right)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self.view_area.grid.layout_changed.connect(self._on_layout_changed)

        self.presenter.on_change = self._on_change
        self.state.listeners.append(self._on_scene)
        self._on_change()
        self._on_scene()

    # ---- actions / menus / toolbar -------------------------------------------
    def _build_actions(self) -> None:
        def act(text, slot=None, shortcut=None, checkable=False, checked=False,
                enabled=True, tip=""):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            a.setChecked(checked)
            a.setEnabled(enabled)
            if tip:
                a.setStatusTip(tip)
            if slot is not None:
                (a.toggled if checkable else a.triggered).connect(slot)
            return a

        self.act_open = act("&Open plan…", lambda: self.check_panel.open_plan(), "Ctrl+O",
                            tip="Open an RTPLAN file; its RTSTRUCT and RTDOSE are matched by reference")
        self.act_batch = act("Open &batch folder…", enabled=False,
                             tip="Batch checking arrives in Plan 3c")
        self.act_save = act("&Save report (PDF)…", lambda: self.check_panel.save_report(),
                            "Ctrl+S", enabled=False)
        self.act_settings = act("Se&ttings…", enabled=False, tip="Settings arrive in Plan 3d")
        self.act_exit = act("E&xit", self.close, "Ctrl+Q")
        self.act_run = act("&Run check", lambda: self.presenter.run(), "F5", enabled=False,
                           tip="Recompute the dose at isocentre and compare with the TPS")

        self._preset_group = QActionGroup(self)
        self._preset_group.setExclusive(True)
        self.act_presets: dict[str, QAction] = {}
        for i, (name, title) in enumerate(PRESET_TITLES.items(), start=1):
            a = act(title, None, str(i), checkable=True, checked=(name == "arc"))
            a.triggered.connect(lambda _c=False, n=name: self.view_area.grid.set_preset(n))
            self._preset_group.addAction(a)
            self.act_presets[name] = a
        self.act_grid = act("2×2 &views", self._on_grid_toggled, checkable=True,
                            tip="Show the arc-axis view with axial, coronal and sagittal")
        self.act_fade = act("Depth &fade", self.state.set_fade, checkable=True, checked=True,
                            tip="Fade rings by distance from the viewing plane through iso")
        self.act_slab = act("Slab ±20 mm", self.state.set_slab, checkable=True,
                            tip="Hide rings more than 20 mm from the viewing plane")
        self.act_fit = act("&Fit", lambda: self.view_area.grid.fit_all(), "F")
        self.act_models = act("&Loaded models…", self._show_models)
        self.act_wizard = act("&Import wizard…", enabled=False,
                              tip="Beam-data import and validation arrive in Plan 3d")
        self.act_about = act("&About", self._about)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        m.addActions([self.act_open, self.act_batch])
        m.addSeparator()
        m.addAction(self.act_save)
        m.addSeparator()
        m.addActions([self.act_settings, self.act_exit])
        m = mb.addMenu("&Check")
        m.addAction(self.act_run)
        m = mb.addMenu("&View")
        m.addActions(list(self.act_presets.values()))
        m.addSeparator()
        m.addActions([self.act_grid, self.act_fade, self.act_slab, self.act_fit])
        m.addSeparator()
        plan_act, check_act = self.plan_dock.toggleViewAction(), self.check_dock.toggleViewAction()
        plan_act.setText("&Plan pane")
        check_act.setText("Chec&k pane")
        m.addActions([plan_act, check_act])
        m = mb.addMenu("&Beam data")
        m.addActions([self.act_models, self.act_wizard])
        m = mb.addMenu("&Help")
        m.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("mainToolBar")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addActions([self.act_open, self.act_run])
        tb.addSeparator()
        tb.addActions(list(self.act_presets.values()))
        tb.addSeparator()
        tb.addActions([self.act_grid, self.act_fade, self.act_slab, self.act_fit])

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not self._docks_sized:   # give the geometry the width; docks stay draggable
            self._docks_sized = True
            self.resizeDocks([self.plan_dock, self.check_dock], [290, 320], Qt.Horizontal)

    # ---- reactions ------------------------------------------------------------
    def _on_grid_toggled(self, on: bool) -> None:
        self.view_area.grid.set_layout("2x2" if on else "1x1")

    def _on_layout_changed(self, mode: str) -> None:
        on = mode == "2x2"
        self.act_grid.blockSignals(True)
        self.act_grid.setChecked(on)
        self.act_grid.blockSignals(False)
        for a in self.act_presets.values():
            a.setEnabled(not on)
        if not on:
            self.act_presets[self.view_area.grid.active_preset()].setChecked(True)

    def _on_change(self) -> None:
        p = self.presenter
        self.check_panel.refresh()
        self.plan_panel.facts.set_facts(p.plan_facts)
        if p.plan_facts is None:
            self.model_chip.set_model(None, "", None)
            self.setWindowTitle(_TITLE)
        else:
            self.model_chip.set_model(p.plan_facts.get("machine", ""), p.model_label,
                                      p.model_validated)
            self.setWindowTitle(f"{_TITLE} — {p.plan_facts.get('patient', '')} · "
                                f"{p.plan_facts.get('plan', '')}")
        if id(p.view_geometry) != self._bound_geom_id:
            self._bound_geom_id = id(p.view_geometry)
            self.state.set_geometry(p.view_geometry)
        self.act_run.setEnabled(p.can_run)
        self.act_save.setEnabled(p.state == "RESULT" and p.result is not None
                                 and p.result.status == "ACCEPTED")
        if p.state in ("RUNNING", "RESULT", "RUN_ERROR"):
            self.check_dock.show()      # a run must be seen: un-hide / un-tabify the pane
            self.check_dock.raise_()
        if p.state == "READING":
            self.statusBar().showMessage("Reading plan…")
        elif p.state == "RUNNING":
            self.statusBar().showMessage("Computing independent dose…")
        else:
            self.statusBar().clearMessage()

    def _on_scene(self) -> None:
        mode = ("depth fade" if self.state.fade else "full rings")
        if self.state.slab:
            mode += " · slab ±20 mm"
        self._status_right.setText(mode)   # the scrubber already shows the sample readout

    def _show_models(self) -> None:
        ModelsDialog(self.config, self).exec()

    def _about(self) -> None:
        QMessageBox.about(self, "About",
                          f"{_TITLE}\n\nIndependent secondary dose/MU check for "
                          "fixed-cone cranial SRS (TG-71/TG-219 formalism).")


def run() -> int:
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()
