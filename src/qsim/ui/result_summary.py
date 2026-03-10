"""Helpers for summarizing workflow results in notebooks and lightweight UIs."""

from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from qsim.analysis.trace_semantics import state_encoding


def collect_pulse_metrics(out_dir: str | Path) -> dict[str, float]:
    """Extract simple per-channel pulse metrics from workflow artifacts."""
    out_dir = Path(out_dir)
    npz_path = out_dir / "pulse_samples.npz"
    if not npz_path.exists():
        alternatives = sorted(out_dir.glob("pulse_samples*.npz"))
        if not alternatives:
            return {}
        npz_path = alternatives[0]

    data = np.load(npz_path)
    metrics: dict[str, float] = {}
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
        metrics[f"{prefix}_abs_area"] = float(np.trapezoid(np.abs(y), t)) if len(t) > 1 else float(np.abs(y).sum())
        metrics[f"{prefix}_peak"] = float(np.max(np.abs(y)))
    return metrics


def summarize_workflow_result(
    result: dict,
    *,
    task_tag: str,
    task_title: str,
    case_tag: str,
    engine: str,
    hardware: dict | None = None,
    noise: dict | None = None,
    note: str = "",
) -> dict:
    """Build one flat summary row from a ``run_workflow`` result payload."""
    trace = result["trace"]
    final_state = [float(x) for x in (trace.states[-1] if trace.states else [])]
    obs = result.get("analysis", {}).get("observables", {}).get("values", {})
    meta = dict(getattr(trace, "metadata", {}) or {})
    details = dict(meta.get("details", {}) or {})
    hardware = dict(hardware or {})
    noise = dict(noise or {})

    row = {
        "task": task_tag,
        "task_title": task_title,
        "case": case_tag,
        "engine": engine,
        "trace_engine": trace.engine,
        "state_encoding": state_encoding(trace),
        "num_qubits": int(meta.get("num_qubits", 0) or 0),
        "state_len": int(len(final_state)),
        "final_state_json": json.dumps(final_state, ensure_ascii=False),
        "final_state_sum": float(sum(final_state)) if final_state else 0.0,
        "final_state_last": float(final_state[-1]) if final_state else np.nan,
        "final_state_max": float(max(final_state)) if final_state else np.nan,
        "samples": int(len(trace.times)),
        "final_p1_obs": float(obs.get("final_p1", np.nan)),
        "final_p0_obs": float(obs.get("final_p0", np.nan)),
        "mean_excited_obs": float(obs.get("mean_excited", np.nan)),
        "solver": str(meta.get("solver", result.get("solver_mode", ""))),
        "solver_impl": str(details.get("solver_impl", "")),
        "native_solver": bool(meta.get("native_solver", False)),
        "note": str(note),
        "hardware_json": json.dumps(hardware, ensure_ascii=False, sort_keys=True),
        "noise_json": json.dumps(noise, ensure_ascii=False, sort_keys=True),
        "out_dir": str(result["out_dir"]),
    }
    row.update(collect_pulse_metrics(result["out_dir"]))
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
