"""Registered analyser metrics and metric payload resolution."""

from __future__ import annotations

from typing import Any

from qsim.analysis.observables import compute_observables
from qsim.analysis.registry import MetricRegistry
from qsim.common.schemas import ModelSpec, Observables, Report, Trajectory


def _complex_scalar(value) -> complex:
    if isinstance(value, complex):
        return value
    if isinstance(value, dict) and "__qsim_complex__" in value:
        pair = list(value.get("__qsim_complex__", []) or [])
        if len(pair) >= 2:
            return complex(float(pair[0]), float(pair[1]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return complex(float(value[0]), float(value[1]))
    return complex(float(value), 0.0)


def _basis_labels(dimension: int, num_qubits: int, levels: int) -> list[str]:
    if dimension <= 0:
        return []
    if num_qubits > 0 and levels > 1:
        expected = levels**num_qubits
        if expected == dimension:
            labels: list[str] = []
            for idx in range(dimension):
                digits: list[str] = []
                rem = idx
                for _ in range(num_qubits):
                    digits.append(str(rem % levels))
                    rem //= levels
                labels.append("".join(reversed(digits)))
            return labels
    return [str(i) for i in range(dimension)]


def _label_excitation_value(label: str, *, num_qubits: int) -> float:
    digits = [int(ch) for ch in str(label) if ch.isdigit()]
    if not digits:
        return 0.0
    if num_qubits > 0 and len(digits) >= num_qubits:
        return float(sum(digits[:num_qubits])) / float(num_qubits)
    return float(sum(digits)) / float(len(digits))


def _population_series_from_quantum_state(trajectory: Trajectory, model_spec: ModelSpec) -> dict[str, list[float]]:
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    if density_matrix:
        qstate = density_matrix
    elif wave_function:
        qstate = wave_function
    else:
        return {}
    snapshots = list(qstate.get("snapshots", []) or [])
    if not snapshots:
        return {}
    actual_kind = str(qstate.get("actual_kind", "")).strip().lower()
    num_qubits = int(model_spec.system.num_qubits or 0)
    levels = (
        int(model_spec.system.transmon_levels or 2)
        if str(model_spec.system.model_type).strip().lower() in {"transmon_nlevel", "cqed_jc", "cqed_dispersive"}
        else 2
    )
    series: dict[str, list[float]] = {}
    labels: list[str] = []

    for snapshot in snapshots:
        populations: list[float]
        if actual_kind == "density_matrix":
            populations = []
            for i, row in enumerate(snapshot):
                if i >= len(row):
                    populations.append(0.0)
                else:
                    populations.append(max(0.0, float(_complex_scalar(row[i]).real)))
        elif actual_kind == "wave_function":
            populations = [abs(_complex_scalar(v)) ** 2 for v in snapshot]
        else:
            return {}

        if not labels:
            labels = _basis_labels(len(populations), num_qubits, max(2, levels))
            series = {label: [] for label in labels}
        for idx, label in enumerate(labels):
            value = float(populations[idx]) if idx < len(populations) else 0.0
            series[label].append(value)
    return series


def _population_series_from_classical(trajectory: Trajectory, model_spec: ModelSpec) -> dict[str, list[float]]:
    classical = dict(getattr(trajectory, "classical", {}) or {})
    basis_payload = dict(classical.get("basis_population", {}) or {})
    basis_values = [list(row) for row in list(basis_payload.get("values", []) or [])]
    if basis_values:
        labels = list(basis_payload.get("series_labels", []) or [])
        if not labels and basis_values[0]:
            labels = [str(i) for i in range(len(basis_values[0]))]
        series = {label: [] for label in labels}
        for row in basis_values:
            for idx, label in enumerate(labels):
                series[label].append(float(row[idx]) if idx < len(row) else 0.0)
        return series
    return {}


def _population_series(trajectory: Trajectory, model_spec: ModelSpec) -> dict[str, list[float]]:
    quantum_series = _population_series_from_quantum_state(trajectory, model_spec)
    quantum_len = max((len(values) for values in quantum_series.values()), default=0)
    if quantum_series and (quantum_len > 1 or quantum_len == len(trajectory.times)):
        return quantum_series
    return _population_series_from_classical(trajectory, model_spec) or quantum_series


def _mean_excited_series_from_population(series: dict[str, list[float]], model_spec: ModelSpec) -> list[float]:
    if not series:
        return []
    num_qubits = int(model_spec.system.num_qubits or 0)
    labels = list(series.keys())
    length = max(len(values) for values in series.values())
    values: list[float] = []
    for idx in range(length):
        total = 0.0
        for label in labels:
            sample = series[label][idx] if idx < len(series[label]) else 0.0
            total += _label_excitation_value(label, num_qubits=num_qubits) * float(sample)
        values.append(float(total))
    return values


def _variance_series_from_population(series: dict[str, list[float]], model_spec: ModelSpec) -> list[float]:
    if not series:
        return []
    num_qubits = int(model_spec.system.num_qubits or 0)
    labels = list(series.keys())
    label_values = {label: _label_excitation_value(label, num_qubits=num_qubits) for label in labels}
    means = _mean_excited_series_from_population(series, model_spec)
    values: list[float] = []
    for idx, mean in enumerate(means):
        total = 0.0
        for label in labels:
            sample = series[label][idx] if idx < len(series[label]) else 0.0
            delta = label_values[label] - mean
            total += float(sample) * float(delta * delta)
        values.append(float(total))
    return values


def _metric_result(payload: Any, *, observable_updates: dict[str, float] | None = None) -> dict[str, Any]:
    return {
        "payload": payload,
        "observable_updates": dict(observable_updates or {}),
    }


def metric_population(trajectory: Trajectory, model_spec: ModelSpec, metric_cfg: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    del metric_cfg, context
    basis_series = _population_series(trajectory, model_spec)
    series_length = max((len(values) for values in basis_series.values()), default=0)
    updates: dict[str, float] = {}
    for label, values in basis_series.items():
        if values:
            updates[str(label)] = float(values[-1])
    if "0" in basis_series and basis_series["0"]:
        updates["final_p0"] = float(basis_series["0"][-1])
    if "1" in basis_series and basis_series["1"]:
        updates["final_p1"] = float(basis_series["1"][-1])
    return _metric_result(
        {
            "times": list(trajectory.times[:series_length]),
            "values": basis_series,
        },
        observable_updates=updates,
    )


def metric_mean_excited(trajectory: Trajectory, model_spec: ModelSpec, metric_cfg: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    del metric_cfg, context
    basis_series = _population_series(trajectory, model_spec)
    mean_series = _mean_excited_series_from_population(basis_series, model_spec)
    updates = {"mean_excited": float(mean_series[-1])} if mean_series else {}
    return _metric_result(
        {
            "times": list(trajectory.times),
            "values": mean_series,
        },
        observable_updates=updates,
    )


def metric_variance(trajectory: Trajectory, model_spec: ModelSpec, metric_cfg: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    del metric_cfg, context
    basis_series = _population_series(trajectory, model_spec)
    variance_series = _variance_series_from_population(basis_series, model_spec)
    updates = {"variance": float(variance_series[-1])} if variance_series else {}
    return _metric_result(
        {
            "times": list(trajectory.times),
            "values": variance_series,
        },
        observable_updates=updates,
    )


def _metric_terminal_value(value: Any):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if isinstance(value.get("values"), list) and value.get("values"):
            tail = value["values"][-1]
            if isinstance(tail, (int, float)):
                return float(tail)
        if isinstance(value.get("values"), dict):
            return None
    return None


def build_default_metric_registry() -> MetricRegistry:
    registry = MetricRegistry()
    registry.register("population", metric_population)
    registry.register("mean_excited", metric_mean_excited)
    registry.register("variance", metric_variance)
    return registry


DEFAULT_METRIC_REGISTRY = build_default_metric_registry()


def resolve_metrics_payload(
    trajectory: Trajectory,
    model_spec: ModelSpec,
    analyser_cfg: dict[str, Any] | None,
    *,
    registry: MetricRegistry | None = None,
) -> tuple[dict[str, Any], Observables, Report]:
    requested_metrics = list((analyser_cfg or {}).get("metrics", []) or [])
    observables = compute_observables(trajectory)
    observable_values = dict(observables.values or {})
    metrics_out: dict[str, Any] = {}
    metric_registry = registry or DEFAULT_METRIC_REGISTRY

    if not requested_metrics:
        metrics_out = dict(observable_values)
    else:
        for item in requested_metrics:
            if isinstance(item, str):
                name = str(item).strip()
                metric_cfg = {}
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                metric_cfg = dict(item)
            else:
                continue
            if not name:
                continue
            key = name.lower()
            if metric_registry.has(key):
                entry = metric_registry.get(key)
                result = entry.callable_obj(
                    trajectory,
                    model_spec,
                    metric_cfg,
                    {"observable_values": dict(observable_values)},
                )
                metrics_out[name] = result.get("payload")
                for obs_name, obs_value in dict(result.get("observable_updates", {}) or {}).items():
                    observable_values[str(obs_name)] = float(obs_value)
                continue
            if key in observable_values:
                metrics_out[name] = float(observable_values[key])
            elif name in observable_values:
                metrics_out[name] = float(observable_values[name])

    error_budget = {}
    for key, value in metrics_out.items():
        terminal = _metric_terminal_value(value)
        if terminal is not None:
            error_budget[key] = float(terminal)
    report = Report(
        summary={
            "metrics": list(metrics_out.keys()),
            "metric_mode": "time_series",
            "metric_terminal_values": error_budget,
            "metric_registry": metric_registry.names(),
        },
        error_budget=error_budget,
    )
    return metrics_out, Observables(values=observable_values), report


__all__ = [
    "DEFAULT_METRIC_REGISTRY",
    "MetricRegistry",
    "build_default_metric_registry",
    "metric_mean_excited",
    "metric_population",
    "metric_variance",
    "resolve_metrics_payload",
]
