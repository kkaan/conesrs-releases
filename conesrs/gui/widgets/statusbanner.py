"""Result header: eyebrow → plan title lockup with the outcome as a capsule pill.

Icon-free; the three outcomes (PASS/REVIEW/ACTION vs REJECTED vs ERROR) stay
visually distinct through the pill pairing and the "Not checked." lead.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout

from conesrs.gui import theme

_LEAD = {
    "REJECTED": "Not checked. This plan is outside the tool's scope, so no dose was computed.",
    "ERROR": "Not checked. The tool failed while processing this plan.",
}


def status_label(result) -> str:
    if result.status == "ACCEPTED":
        return result.tolerance_flag or "ACCEPTED"
    return result.status


class StatusBanner(QFrame):
    def __init__(self, result):
        super().__init__()
        label = status_label(result)
        self._label = label
        kind = theme.STATUS_KIND.get(label, theme.REVIEW)

        self.setObjectName("gcCard")
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(4)

        lay.addWidget(theme.eyebrow("Cone-SRS secondary MU check"))
        row = QHBoxLayout()
        row.setSpacing(8)
        title = theme.label(f"Plan {result.plan_label or '-'}", "gcH2")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        row.addWidget(title, 1)
        row.addWidget(theme.pill(label, kind, size=11), 0)
        lay.addLayout(row)

        facts = [f"Patient {result.patient_id or '-'}", f"Machine {result.machine or '-'}"]
        lay.addWidget(theme.label("  ·  ".join(facts), "gcMuted"))

        if result.status != "ACCEPTED":
            lay.addSpacing(6)
            lead = theme.label(_LEAD.get(result.status, "Not checked."), "gcValue")
            lead.setStyleSheet("font-weight: 700;")
            lay.addWidget(lead)
            reason = result.reject_reason or result.error_detail or ""
            if reason:
                notice_kind = theme.NEAR if result.status == "REJECTED" else theme.ERROR
                lay.addWidget(theme.notice(reason, notice_kind))

    def text_label(self) -> str:
        return self._label
