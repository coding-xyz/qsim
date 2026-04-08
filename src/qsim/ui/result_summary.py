"""Helpers for summarizing workflow results in notebooks and lightweight UIs."""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd
from qsim.analysis.trajectory_semantics import state_channel_name, state_encoding, state_rows
from qsim.workflow.model import Model


def _integrate_abs(y: np.ndarray, t: np.ndarray) -> float:
    """Integrate ``|y|`` over ``t`` with NumPy-version fallback."""
    abs_y = np.abs(y)
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(abs_y, t))
    return float(np.trapz(abs_y, t))


def collect_pulse_metrics(out_dir: str | Path) -> dict[str, float]:
    """Extract simple per-channel pulse metrics from workflow artifacts."""
    out_dir = Path(out_dir)
    npz_path = out_dir / "pulse_samples.npz"
    if not npz_path.exists():
        alternatives = sorted(out_dir.glob("pulse_samples*.npz"))
        if not alternatives:
            return {}
        npz_path = alternatives[0]

    metrics: dict[str, float] = {}
    with np.load(npz_path) as data:
        prefixes = sorted({name[:-2] for name in data.files if name.endswith("_t")})
        for prefix in prefixes:
            t_key = f"{prefix}_t"
            y_key = f"{prefix}_y"
            if t_key not in data.files or y_key not in data.files:
                continue
            t = np.asarray(data[t_key], dtype=float)
            y = np.asarray(data[y_key], dtype=float)
            if t.size == 0 or y.size == 0:
                continue
            metrics[f"{prefix}_samples"] = float(len(t))
            metrics[f"{prefix}_duration"] = float(t[-1] - t[0]) if len(t) > 1 else 0.0
            metrics[f"{prefix}_abs_area"] = _integrate_abs(y, t) if len(t) > 1 else float(np.abs(y).sum())
            metrics[f"{prefix}_peak"] = float(np.max(np.abs(y)))
    return metrics


def summarize_workflow_result(
    model: Model,
    *,
    task_tag: str,
    task_title: str,
    case_tag: str,
    engine: str,
    device: dict | None = None,
    noise: dict | None = None,
    note: str = "",
) -> dict:
    """Build one flat summary row from a completed ``Model``."""
    if not getattr(model.results, "trajectories", None):
        raise ValueError("summarize_workflow_result expects a model that has already produced results.")
    solver_id = sorted(model.results.trajectories.keys())[0]
    bundle = model.results.solver_runs[solver_id]
    trajectory = bundle.trajectory
    assert trajectory is not None
    analysis = next(iter(bundle.analyses.values()), None)
    metrics = dict((analysis.metrics if analysis is not None else {}) or {})
    runtime = dict(bundle.runtime_metadata or {})
    model_payload = dict(getattr(bundle.model_spec, "payload", {}) or {})

    inferred_state_encoding = state_encoding(trajectory)
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    if density_matrix:
        state_kind = "density_matrix"
    elif wave_function:
        state_kind = "wave_function"
    else:
        state_kind = state_channel_name(trajectory)
    rows = state_rows(trajectory)
    final_state_raw = list(rows[-1]) if rows else []
    times = list(trajectory.times or [])
    details = dict(runtime.get("details", {}) or {})
    device = dict(device or {})
    noise = dict(noise or {})

    final_state_json = json.dumps(final_state_raw, ensure_ascii=False)
    final_state_sum = np.nan
    final_state_last = np.nan
    final_state_max = np.nan
    state_len = 0
    if isinstance(final_state_raw, list):
        state_len = len(final_state_raw)
        if final_state_raw and all(isinstance(x, (int, float)) for x in final_state_raw):
            numeric_state = [float(x) for x in final_state_raw]
            final_state_sum = float(sum(numeric_state))
            final_state_last = float(numeric_state[-1])
            final_state_max = float(max(numeric_state))

    population_metric = dict(metrics.get("population", {}) or {})
    population_series = dict(population_metric.get("values", {}) or {})
    final_p0 = np.nan
    final_p1 = np.nan
    if isinstance(population_series.get("0"), list) and population_series["0"]:
        final_p0 = float(population_series["0"][-1])
    if isinstance(population_series.get("1"), list) and population_series["1"]:
        final_p1 = float(population_series["1"][-1])

    mean_excited_metric = dict(metrics.get("mean_excited", {}) or {})
    mean_excited_values = list(mean_excited_metric.get("values", []) or [])
    variance_metric = dict(metrics.get("variance", {}) or {})
    variance_values = list(variance_metric.get("values", []) or [])

    row = {
        "task": task_tag,
        "task_title": task_title,
        "case": case_tag,
        "engine": engine,
        "trajectory_engine": str(trajectory.engine),
        "state_encoding": inferred_state_encoding,
        "state_kind": state_kind,
        "num_qubits": int(model_payload.get("num_qubits", 0) or 0),
        "state_len": int(state_len),
        "final_state_json": final_state_json,
        "final_state_sum": final_state_sum,
        "final_state_last": final_state_last,
        "final_state_max": final_state_max,
        "samples": int(len(times)),
        "final_p1_obs": final_p1,
        "final_p0_obs": final_p0,
        "mean_excited_obs": float(mean_excited_values[-1]) if mean_excited_values else np.nan,
        "variance_obs": float(variance_values[-1]) if variance_values else np.nan,
        "solver_impl": str(details.get("solver_impl", "")),
        "solver": str(runtime.get("solver_mode", "")),
        "native_solver": bool(details.get("native_solver", False)),
        "note": str(note),
        "device_json": json.dumps(device, ensure_ascii=False, sort_keys=True),
        "noise_json": json.dumps(noise, ensure_ascii=False, sort_keys=True),
        "out_dir": str(model.out_dir or ""),
    }
    row.update(collect_pulse_metrics(row["out_dir"]))
    return row


def attach_compare_status(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate whether rows in a task/case group are pointwise comparable."""
    df = df.copy()
    statuses: dict[tuple[str, str], str] = {}
    reasons: dict[tuple[str, str], str] = {}
    for (task, case), group in df.groupby(["task", "case"]):
        encodings = sorted(set(str(x) for x in group["state_encoding"]))
        if len(encodings) == 1 and encodings[0] == "per_qubit_excited_probability":
            statuses[(task, case)] = "pointwise-comparable"
            reasons[(task, case)] = "all engines expose per-qubit excited probabilities"
        else:
            statuses[(task, case)] = "semantic-review-needed"
            reasons[(task, case)] = " | ".join(encodings)
    df["compare_status"] = [statuses[(t, c)] for t, c in zip(df["task"], df["case"])]
    df["compare_reason"] = [reasons[(t, c)] for t, c in zip(df["task"], df["case"])]
    return df

