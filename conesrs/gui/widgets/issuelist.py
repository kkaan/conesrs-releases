"""Aggregated validation issues: blockers then warnings, as notices."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from conesrs.gui import theme


class IssueList(QWidget):
    def __init__(self, issues):
        super().__init__()
        self._blockers = [i for i in issues if i.severity == "blocker"]
        self._warnings = [i for i in issues if i.severity == "warning"]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for grp, title, kind in ((self._blockers, "Blockers", theme.ERROR),
                                 (self._warnings, "Warnings", theme.NEAR)):
            if not grp:
                continue
            lay.addWidget(theme.h2(f"{title} ({len(grp)})"))
            for issue in grp:
                lay.addWidget(theme.notice(issue.message, kind))
            lay.addSpacing(6)

    def blocker_count(self) -> int:
        return len(self._blockers)

    def warning_count(self) -> int:
        return len(self._warnings)
