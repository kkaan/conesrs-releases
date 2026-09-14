"""Check dock: a page stack that mirrors the single-check presenter's state."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from conesrs.gui import theme
from conesrs.gui.single.presenter import SingleCheckPresenter
from conesrs.gui.widgets.dosecompare import DoseCompare
from conesrs.gui.widgets.depthplot import DepthPlot
from conesrs.gui.widgets.issuelist import IssueList
from conesrs.gui.widgets.provenance import ProvenancePanel
from conesrs.gui.widgets.statusbanner import StatusBanner

_ORDER = {"LOAD": 0, "LOAD_ERROR": 0, "READING": 0, "VALIDATE": 1,
          "RUNNING": 2, "RESULT": 3, "RUN_ERROR": 3}


def _wrap_labels(root: QWidget) -> None:
    for lab in root.findChildren(QLabel):
        lab.setWordWrap(True)


def _page() -> tuple[QWidget, QVBoxLayout]:
    """A themed page whose content lives in a vertical scroll area."""
    w = theme.page(QWidget())
    inner = QWidget()
    inner.setObjectName("gcPage")
    inner.setAttribute(Qt.WA_StyledBackground, True)
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(10)
    scroll = QScrollArea()
    scroll.setObjectName("gcScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(inner)
    outer = QVBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)
    return w, lay


class CheckPanel(QWidget):
    def __init__(self, presenter: SingleCheckPresenter, parent=None):
        super().__init__(parent)
        self._p = presenter
        self._stack = QStackedWidget()
        for _ in range(4):
            self._stack.addWidget(QWidget())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)
        self.refresh()

    def current_state(self) -> str:
        return self._p.state

    def _replace(self, index, widget):
        old = self._stack.widget(index)
        self._stack.removeWidget(old)
        old.deleteLater()
        self._stack.insertWidget(index, widget)

    def refresh(self):
        p = self._p
        if p.state == "READING":
            w, lay = _page()
            lay.addWidget(theme.notice("Reading plan: parsing DICOM and checking scope.",
                                       theme.INFO))
            lay.addStretch(1)
            self._replace(0, w)
        elif p.state in ("LOAD", "LOAD_ERROR"):
            w, lay = _page()
            lay.addWidget(theme.eyebrow("Cone-SRS secondary MU check"))
            if p.error:
                lay.addWidget(theme.notice(p.error, theme.ERROR))
            else:
                lay.addWidget(theme.label(
                    "Open an RTPLAN (RP*.dcm) file to begin. Its structure set and dose "
                    "are matched automatically by DICOM reference."))
            open_btn = theme.primary_button("Open plan (RTPLAN file)…")
            open_btn.clicked.connect(self.open_plan)
            lay.addWidget(open_btn)
            lay.addStretch(1)
            self._replace(0, w)
        elif p.state == "VALIDATE":
            w, lay = _page()
            lay.addWidget(theme.eyebrow("Scope check"))
            if not p.issues:
                lay.addWidget(theme.notice("No blockers found. The plan is in scope.",
                                           theme.INFO))
            lay.addWidget(IssueList(p.issues))
            run = theme.primary_button("Run check")
            run.setEnabled(p.can_run)
            run.clicked.connect(p.run)
            lay.addWidget(run)
            lay.addStretch(1)
            self._replace(1, w)
        elif p.state == "RUNNING":
            w, lay = _page()
            lay.addWidget(theme.notice("Computing independent dose.", theme.INFO))
            lay.addStretch(1)
            self._replace(2, w)
        elif p.state in ("RESULT", "RUN_ERROR"):
            w, lay = _page()
            if p.state == "RUN_ERROR":
                lay.addWidget(theme.eyebrow("Cone-SRS secondary MU check"))
                lay.addWidget(theme.label("Not checked. The tool failed while processing "
                                          "this plan.", "gcValue"))
                lay.addWidget(theme.notice(f"Processing error: {p.error}", theme.ERROR))
            else:
                r = p.result
                lay.addWidget(StatusBanner(r))
                if r.status == "ACCEPTED":
                    lay.addWidget(DoseCompare(r))
                    plot_card, plot_lay = theme.card((10, 8, 10, 6), 4)
                    plot_lay.addWidget(theme.h2("Depth to isocentre vs gantry angle"))
                    plot_lay.addWidget(DepthPlot(r.depth_profile, r.depth_profile_by_beam))
                    lay.addWidget(plot_card)
                lay.addWidget(ProvenancePanel(r))
                save = theme.primary_button("Save report (PDF)…")
                save.clicked.connect(self.save_report)
                lay.addWidget(save)
            lay.addStretch(1)
            _wrap_labels(w)   # the dock is narrow: long dose/provenance lines must wrap
            self._replace(3, w)
        self._stack.setCurrentIndex(_ORDER[p.state])

    def open_plan(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an RTPLAN file", "",
            "DICOM RTPLAN (RP*.dcm);;DICOM files (*.dcm);;All files (*)")
        if path:
            self._p.load(path)

    def save_report(self):
        # Generate the REAL PDF (report.pdf), save to a chosen path, open it.
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QFileDialog

        from conesrs.report.pdf import write_pdf

        if self._p.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save report", "report.pdf",
                                              "PDF (*.pdf)")
        if not path:
            return
        write_pdf(self._p.result, path, timestamp="")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
