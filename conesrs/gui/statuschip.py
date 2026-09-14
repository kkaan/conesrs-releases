"""Beam-model status chip (status bar) and the Loaded models dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget,
                               QVBoxLayout)

from conesrs.config.machines import MachineConfig
from conesrs.data.formats import load_beam_data

_STYLE = {
    "ok": "color:#4CC38A; background:#14301F; border:1px solid #4CC38A;",
    "warn": "color:#E8B339; background:#2E2712; border:1px solid #E8B339;",
    "block": "color:#F0645A; background:#3A1B18; border:1px solid #F0645A;",
    "none": "color:palette(mid); border:1px solid palette(mid);",
}


def describe_models(config: MachineConfig) -> list[tuple[str, str, bool | None]]:
    """(model_id, 'Name vVersion', validated) per configured model; None = missing."""
    rows = []
    for model_id in sorted(set(config.models)):
        try:
            model = load_beam_data(config.model_path(model_id))
            rows.append((model_id, f"{model.name} {model.version}",
                         bool(model.validated)))
        except Exception:  # noqa: BLE001 - missing or unreadable model file
            rows.append((model_id, "(missing)", None))
    return rows


class ModelChip(QLabel):
    """`Banksia → ⚠ Elekta cones v0-provisional · unvalidated` in the status bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_model(None, "", None)

    def set_model(self, machine: str | None, label: str,
                  validated: bool | None) -> None:
        if machine is None:
            state, text = "none", "No plan loaded"
        elif not label:
            state, text = "block", f"{machine} → ✕ no model mapped"
        elif validated:
            state, text = "ok", f"{machine} → ✓ {label} · validated"
        else:
            state, text = "warn", f"{machine} → ⚠ {label} · unvalidated"
        self.setProperty("state", state)
        self.setText(text)
        self.setStyleSheet("QLabel { padding:1px 8px; border-radius:3px; "
                           + _STYLE[state] + " }")


class ModelsDialog(QDialog):
    def __init__(self, config: MachineConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loaded beam data")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Configured beam models and their validation state. "
                             "Validation is set in the import wizard (Plan 3d)."))
        self.list = QListWidget()
        for model_id, label, validated in describe_models(config):
            mark = ("✓ validated" if validated else
                    "⚠ unvalidated" if validated is False else "✕ missing file")
            machines = ", ".join(sorted(m for m, mid in config.machines.items()
                                        if mid == model_id))
            self.list.addItem(f"{model_id} · {label} · {mark} · machines: {machines or '—'}")
        lay.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)
