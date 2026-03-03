"""Pauli-plus component modeling and scaling sweep helpers."""

from __future__ import annotations

from typing import Any

from qsim.engines.cirq_qec_engine import CirqQECAnalysisEngine
from qsim.engines.stim_qec_engine import StimQECAnalysisEngine


def build_component_error_model(
    *,
    logical_x: float,
    logical_z: float,
    mean_excited: float,
    final_p1: float,
) -> dict[str, float]:
    """Build component-level error seeds from current run metrics.

    This is a bridge model for offline analysis. It converts available workflow
    observables/logical-error summaries into component bins expected by Pauli+
    scaling and ablation routines.
    """
    return {
        "one_qubit": max(0.0, 0.3 * logical_x + 0.02 * mean_excited),
        "cz": max(0.0, 0.5 * logical_x + 0.2 * logical_z),
        "cz_stray": max(0.0, 0.3 * logical_z + 0.1 * mean_excited),
        "measure_reset": max(0.0, 0.2 * final_p1 + 0.2 * logical_z),
        "leakage": max(0.0, 0.15 * final_p1 + 0.05 * mean_excited),
        "dd_idle": max(0.0, 0.1 * logical_z),
    }


def _select_qec_engine(name: str):
    key = (name or "auto").lower()
    if key == "stim":
        return StimQECAnalysisEngine()
    if key == "cirq":
        return CirqQECAnalysisEngine()
    if key == "mock":
        return StimQECAnalysisEngine()
    # auto path handled in ``run_pauli_plus_sim``.
    return None


def run_pauli_plus_sim(
    model_spec: dict[str, Any],
    *,
    qec_engine: str,
    code_distance: int,
    shots: int,
    seed: int,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one code-distance Pauli+ simulation through selected engine.

    For ``qec_engine='auto'``, this function tries Stim first and falls back to
    Cirq if Stim returns fallback quality.
    """
    key = (qec_engine or "auto").lower()
    if key == "auto":
        stim_out = StimQECAnalysisEngine().run_pauli_plus(
            model_spec,
            code_distance=int(code_distance),
            shots=int(max(1, shots)),
            seed=int(seed),
            options=options,
        )
        if str(stim_out.get("backend", "")) != "fallback":
            out = stim_out
        else:
            out = CirqQECAnalysisEngine().run_pauli_plus(
                model_spec,
                code_distance=int(code_distance),
                shots=int(max(1, shots)),
                seed=int(seed),
                options=options,
            )
            out.setdefault("metadata", {})
            out["metadata"]["auto_probe"] = {"stim_backend": stim_out.get("backend"), "stim_quality": stim_out.get("quality")}
    else:
        engine = _select_qec_engine(qec_engine)
        assert engine is not None
        out = engine.run_pauli_plus(
            model_spec,
            code_distance=int(code_distance),
            shots=int(max(1, shots)),
            seed=int(seed),
            options=options,
        )
    out["engine_requested"] = qec_engine
    return out


def build_scaling_report(epsilon_by_d: dict[int, float]) -> dict[str, Any]:
    """Build scaling report with Lambda3/5 from epsilon-by-distance results."""
    e3 = float(epsilon_by_d.get(3, 0.0))
    e5 = float(epsilon_by_d.get(5, 0.0))
    lam = (e3 / e5) if e5 > 0 else 0.0
    return {
        "schema_version": "1.0",
        "status": "ok",
        "epsilon_by_d": {str(int(k)): float(v) for k, v in sorted(epsilon_by_d.items())},
        "epsilon_3": e3,
        "epsilon_5": e5,
        "lambda_3_5": float(lam),
    }


def run_scaling_sweep(
    *,
    qec_engine: str,
    component_errors: dict[str, float],
    code_distances: list[int],
    shots: int,
    seed: int,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Pauli+ simulations across code distances and return scaling report.

    Includes run-level backend quality statistics:
    ``native_runs``, ``fallback_runs``, ``native_runs_ratio``.
    """
    eps_by_d: dict[int, float] = {}
    engine_runs: list[dict[str, Any]] = []
    for d in code_distances:
        out_pp = run_pauli_plus_sim(
            {"component_errors": dict(component_errors)},
            qec_engine=qec_engine,
            code_distance=int(d),
            shots=int(max(1, shots)),
            seed=int(seed),
            options=options,
        )
        eps_by_d[int(d)] = float(out_pp.get("epsilon_d", 0.0))
        engine_runs.append(out_pp)
    report = build_scaling_report(eps_by_d)
    report["engine_runs"] = engine_runs
    report["qec_engine_requested"] = qec_engine
    n_total = max(1, len(engine_runs))
    n_native = sum(1 for r in engine_runs if str(r.get("quality", "")).lower() == "native")
    report["native_runs"] = int(n_native)
    report["fallback_runs"] = int(n_total - n_native)
    report["native_runs_ratio"] = float(n_native / n_total)
    return report
