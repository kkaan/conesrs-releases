"""Pure-Python single-check flow state machine — no Qt, fully unit-testable.

The view injects Deps: how to enumerate plan sets, parse+resolve a set, run the
aggregating prevalidate, run the full check, and schedule the (slow) run. In
production `schedule` submits to a QThreadPool; in tests it runs synchronously.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Deps:
    match: Callable          # (folder) -> list[PlanSet]
    prepare: Callable        # (planset) -> (plan, structures, dose, model_or_None)
    prevalidate: Callable    # (plan, structures, dose, model) -> list[ValidationIssue]
    run: Callable            # (planset) -> PlanCheckResult
    schedule: Callable       # (fn, on_done) -> None ; calls on_done(fn()) eventually
    build_geometry: Callable | None = None  # (plan, structures, model) -> ViewGeometry|None


def _guarded(fn):
    """Wrap fn so the worker returns ("ok", value) or ("err", exc), never raises."""
    def call():
        try:
            return ("ok", fn())
        except Exception as exc:  # noqa: BLE001 - surfaced to the presenter
            return ("err", exc)
    return call


def _plan_facts(plan) -> dict:
    """Read-only identifiers for the Plan panel (never typed by the user)."""
    iso = getattr(plan, "isocentre", None)
    return {
        "patient": getattr(plan, "patient_id", ""),
        "plan": getattr(plan, "plan_label", ""),
        "machine": getattr(plan, "machine", ""),
        "fractions": getattr(plan, "number_of_fractions", ""),
        "isocentre": tuple(float(v) for v in iso) if iso is not None else (),
    }


def _model_info(model) -> tuple[str, bool | None]:
    """('Name version', validated) or ('', None) when there is no usable model."""
    name = getattr(model, "name", None)
    if model is None or name is None:
        return "", None
    label = f"{name} {getattr(model, 'version', '')}".strip()
    return label, bool(getattr(model, "validated", False))


class SingleCheckPresenter:
    def __init__(self, deps: Deps, on_change: Callable | None = None):
        self._deps = deps
        self._load_generation = 0
        self.on_change = on_change or (lambda: None)
        self.state = "LOAD"          # LOAD|LOAD_ERROR|READING|VALIDATE|RUNNING|RESULT|RUN_ERROR
        self.sets: list = []
        self.planset = None
        self.issues: list = []
        self.result = None
        self.error: str = ""
        self.view_geometry = None
        self.view_error: str = ""
        self.geometry_pending: bool = False
        self.plan_facts: dict | None = None
        self.model_label: str = ""
        self.model_validated: bool | None = None

    def _set_state(self, state):
        self.state = state
        self.on_change()

    @property
    def can_run(self) -> bool:
        return self.state == "VALIDATE" and not any(
            i.severity == "blocker" for i in self.issues)

    def load(self, folder) -> None:
        # Workers may finish after another plan is opened. Only the current
        # load's callbacks may publish facts, geometry, errors, or results.
        self._load_generation += 1
        generation = self._load_generation
        self.result = None
        self.planset = None
        self.view_geometry = None
        self.view_error = ""
        self.geometry_pending = False
        self.issues = []
        self.error = ""
        self.plan_facts = None
        self.model_label = ""
        self.model_validated = None
        self.sets = list(self._deps.match(folder))
        if len(self.sets) != 1:
            self.error = (f"found {len(self.sets)} plan sets in {folder}; "
                          "single check needs exactly one")
            return self._set_state("LOAD_ERROR")
        self.planset = self.sets[0]
        self._set_state("READING")
        planset = self.planset

        def read():
            plan, structures, dose, model = self._deps.prepare(planset)
            issues = list(self._deps.prevalidate(plan, structures, dose, model))
            return plan, structures, model, issues

        def done(outcome):
            if generation != self._load_generation:
                return
            kind, value = outcome
            if kind != "ok":
                self.error = f"failed to read plan: {value!r}"
                return self._set_state("LOAD_ERROR")
            plan, structures, model, issues = value
            self.issues = issues
            self.plan_facts = _plan_facts(plan)
            self.model_label, self.model_validated = _model_info(model)
            self._set_state("VALIDATE")
            self._start_geometry(plan, structures, model, generation)

        self._deps.schedule(_guarded(read), done)

    def _start_geometry(self, plan, structures, model, generation) -> None:
        builder = self._deps.build_geometry
        if builder is None or generation != self._load_generation:
            return
        self.geometry_pending = True
        self.on_change()

        def done(outcome):
            if generation != self._load_generation:
                return
            kind, value = outcome
            self.geometry_pending = False
            if kind == "ok":
                self.view_geometry = value
                self.view_error = ""
            else:
                self.view_geometry = None
                self.view_error = f"{value!r}"
            self.on_change()

        self._deps.schedule(_guarded(lambda: builder(plan, structures, model)), done)

    def run(self) -> None:
        if not self.can_run:
            return
        generation = self._load_generation
        planset = self.planset
        self._set_state("RUNNING")

        def work():
            return self._deps.run(planset)

        def done(outcome):
            if generation != self._load_generation:
                return
            kind, value = outcome
            if kind == "ok":
                self.result = value
                self._set_state("RESULT")
            else:
                self.error = f"{value!r}"
                self._set_state("RUN_ERROR")

        self._deps.schedule(_guarded(work), done)
