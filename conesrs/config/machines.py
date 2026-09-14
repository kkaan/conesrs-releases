"""Machine->model configuration and beam-data file registry.

Treatment-machine names are local per-unit nicknames, so the mapping from a
machine to which beam model it uses is explicit and physicist-editable. Model
file paths resolve relative to the config file's directory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DEFAULT = Path(__file__).with_name("machines.default.json")


class UnknownMachineError(KeyError):
    """Raised when a plan's treatment machine is not in the config."""


@dataclass(frozen=True)
class MachineConfig:
    machines: dict[str, str]       # machine name -> model_id
    models: dict[str, str]         # model_id -> beam-data file (relative or absolute)
    base_dir: Path                 # directory the model paths resolve against

    @classmethod
    def load(cls, path: str | Path) -> "MachineConfig":
        p = Path(path)
        doc = json.loads(p.read_text(encoding="utf-8"))
        return cls(machines=dict(doc["machines"]), models=dict(doc["models"]),
                   base_dir=p.parent)

    @classmethod
    def load_default(cls) -> "MachineConfig":
        return cls.load(_DEFAULT)

    def model_id_for(self, machine: str) -> str:
        if machine not in self.machines:
            raise UnknownMachineError(
                f"machine {machine!r} not in config (known: {sorted(self.machines)})"
            )
        return self.machines[machine]

    def model_path(self, model_id: str) -> Path:
        rel = self.models[model_id]
        p = Path(rel)
        return p if p.is_absolute() else (self.base_dir / p)
