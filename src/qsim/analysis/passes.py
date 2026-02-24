from __future__ import annotations

from typing import Protocol

from qsim.analysis.error_budget import build_report
from qsim.analysis.observables import compute_observables
from qsim.common.schemas import ModelSpec, Trace


class AnalysisPass(Protocol):
    """Callable protocol for analysis pass implementation."""

    def __call__(self, trace: Trace, model_spec: ModelSpec) -> dict:
        ...


def default_analysis_pass(trace: Trace, model_spec: ModelSpec) -> dict:
    """Run built-in observables and error-budget analysis."""
    observables = compute_observables(trace)
    report = build_report(observables)
    return {
        "observables": observables.__dict__,
        "report": report.__dict__,
    }
