"""Analysis public API.

This package currently exposes registry-oriented helpers for running analysis
steps and managing analysis implementations.
"""

from qsim.analysis.metrics import DEFAULT_METRIC_REGISTRY, MetricRegistry, build_default_metric_registry, resolve_metrics_payload
from qsim.analysis.registry import AnalysisRegistry, AnalysisRunner
from qsim.analysis.state_utils import final_density_matrix, state_fidelity

__all__ = [
    "AnalysisRegistry",
    "AnalysisRunner",
    "MetricRegistry",
    "DEFAULT_METRIC_REGISTRY",
    "build_default_metric_registry",
    "final_density_matrix",
    "resolve_metrics_payload",
    "state_fidelity",
]
