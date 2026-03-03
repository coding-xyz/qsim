"""Composable analysis-pass helpers used by the workflow runner."""

from __future__ import annotations

from typing import Protocol

from qsim.analysis.error_budget import build_report
from qsim.analysis.observables import compute_observables
from qsim.common.schemas import ModelSpec, Trace


class AnalysisPass(Protocol):
    """Callable protocol for analysis pass implementation.

    An analysis pass consumes ``Trace`` + ``ModelSpec`` and returns a plain
    dictionary payload that can be serialized by the workflow layer.
    """

    def __call__(self, trace: Trace, model_spec: ModelSpec) -> dict:
        ...


def default_analysis_pass(trace: Trace, model_spec: ModelSpec) -> dict:
    """Run built-in observables and error-budget analysis.

    Args:
        trace: Engine trace samples.
        model_spec: Executable model configuration. Included for compatibility
            with custom passes, even though the default pass does not use it.

    Returns:
        A dictionary with ``observables`` and ``report`` entries.
    """
    observables = compute_observables(trace)
    report = build_report(observables)
    return {
        "observables": observables.__dict__,
        "report": report.__dict__,
    }
