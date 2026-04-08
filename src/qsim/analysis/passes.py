"""Composable analysis-pass helpers used by the workflow runner."""

from __future__ import annotations

from typing import Protocol

from qsim.analysis.error_budget import build_report
from qsim.analysis.observables import compute_observables
from qsim.common.schemas import ModelSpec, Trajectory


class AnalysisPass(Protocol):
    """Callable protocol for analysis pass implementation.

    An analysis pass consumes ``Trajectory`` + ``ModelSpec`` and returns a plain
    dictionary payload that can be serialized by the workflow layer.
    """

    def __call__(self, Trajectory: Trajectory, model_spec: ModelSpec) -> dict:
        ...


def default_analysis_pass(Trajectory: Trajectory, model_spec: ModelSpec) -> dict:
    """Run built-in observables and error-budget analysis.

    Args:
        Trajectory: Engine Trajectory samples.
        model_spec: Executable model configuration. Included for compatibility
            with custom passes, even though the default pass does not use it.

    Returns:
        A dictionary with ``observables`` and ``report`` entries.
    """
    observables = compute_observables(Trajectory)
    report = build_report(observables)
    return {
        "observables": observables.__dict__,
        "report": report.__dict__,
    }

