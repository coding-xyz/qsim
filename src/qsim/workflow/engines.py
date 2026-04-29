"""Engine-level workflow helpers."""

from __future__ import annotations

from qsim.analysis.trajectory_semantics import pointwise_compare_compatibility, state_encoding, state_rows
from qsim.engines.qoptics import QOpticsEngine
from qsim.engines.qutip import QuTiPEngine
from qsim.engines.qtoolbox import QToolboxEngine


def select_engine(name: str):
    """Return an engine instance by user-facing name."""
    key = str(name).strip().lower()
    if key == "qutip":
        return QuTiPEngine()
    if key == "qtoolbox":
        return QToolboxEngine()
    if key == "qoptics":
        return QOpticsEngine()
    raise ValueError(f"Unknown engine: {name!r}. Supported engines: qutip, qoptics, qtoolbox.")


def canonical_engine_name(name: str) -> str:
    """Normalize an engine name alias to canonical form."""
    key = str(name).strip().lower()
    if key == "qtoolbox":
        return "qtoolbox"
    if key == "qoptics":
        return "qoptics"
    if key == "qutip":
        return "qutip"
    raise ValueError(f"Unknown engine: {name!r}. Supported engines: qutip, qoptics, qtoolbox.")


def trajectory_summary(trajectory) -> dict:
    """Build compact summary for a trajectory payload."""
    rows = state_rows(trajectory)
    last = rows[-1] if rows else []
    final_mean = float(sum(last) / len(last)) if last else 0.0
    return {
        "engine": trajectory.engine,
        "samples": len(trajectory.times),
        "state_dim": len(last),
        "final_state": [float(v) for v in last],
        "final_mean": final_mean,
        "state_encoding": state_encoding(trajectory),
        "metadata": dict(getattr(trajectory, "metadata", {}) or {}),
    }


def trajectory_pair_metrics(ref, other) -> dict:
    """Compute pointwise trajectory deltas when comparable."""
    comparable, reason = pointwise_compare_compatibility(ref, other)
    if not comparable:
        return {
            "comparable": False,
            "reason": reason,
            "samples_compared": 0,
        }
    n = min(len(ref.times), len(other.times))
    if n <= 0:
        return {"comparable": True, "samples_compared": 0, "mse": 0.0, "mae": 0.0}
    ref_rows = state_rows(ref)
    other_rows = state_rows(other)
    d = 0
    if ref_rows and other_rows:
        d = min(len(ref_rows[0]), len(other_rows[0]))
    if d <= 0:
        return {"comparable": True, "samples_compared": n, "mse": 0.0, "mae": 0.0}
    sq_sum = 0.0
    abs_sum = 0.0
    count = 0
    for i in range(n):
        ra = ref_rows[i]
        rb = other_rows[i]
        for j in range(d):
            dv = float(ra[j]) - float(rb[j])
            sq_sum += dv * dv
            abs_sum += abs(dv)
            count += 1
    if count <= 0:
        return {"samples_compared": n, "mse": 0.0, "mae": 0.0}
    return {
        "comparable": True,
        "samples_compared": n,
        "state_dim_compared": d,
        "mse": float(sq_sum / count),
        "mae": float(abs_sum / count),
    }


def run_cross_engine_compare(
    model_spec,
    *,
    engines: list[str],
    seed: int,
    allow_mock_fallback: bool,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
) -> dict:
    """Run model on selected engines and build a compact consistency report."""
    selected: list[str] = []
    seen: set[str] = set()
    for name in engines:
        k = canonical_engine_name(name)
        if k and k not in seen:
            selected.append(k)
            seen.add(k)
    if not selected:
        return {"schema_version": "1.0", "status": "empty", "runs": [], "pairwise": []}

    runs: list[dict] = []
    trajectories = []
    for name in selected:
        engine = select_engine(name)
        model_spec.solver.seed = int(seed)
        model_spec.solver.ntraj = int(max(1, mcwf_ntraj))
        if str(name).strip().lower() == "qutip":
            trajectory = engine.run(model_spec)
        else:
            run_opts = {
                "allow_mock_fallback": bool(allow_mock_fallback),
                "julia_timeout_s": float(julia_timeout_s),
            }
            if julia_bin:
                run_opts["julia_bin"] = str(julia_bin)
            if julia_depot_path:
                run_opts["julia_depot_path"] = str(julia_depot_path)
            trajectory = engine.run(model_spec, run_options=run_opts)
        trajectories.append((name, trajectory))
        item = trajectory_summary(trajectory)
        item["requested_engine"] = name
        runs.append(item)

    baseline_name, baseline_trajectory = trajectories[0]
    pairwise = []
    for name, trajectory in trajectories[1:]:
        pairwise.append(
            {
                "ref_engine": baseline_name,
                "other_engine": name,
                **trajectory_pair_metrics(baseline_trajectory, trajectory),
            }
        )

    return {
        "schema_version": "1.0",
        "status": "ok",
        "solver_mode": model_spec.solver_mode,
        "baseline_engine": baseline_name,
        "runs": runs,
        "pairwise": pairwise,
    }


def collect_runtime_dependencies(trajectory, selected_engine_name: str) -> dict[str, str]:
    """Extract runtime dependency details from engine trajectory metadata."""
    deps: dict[str, str] = {}
    meta = dict(getattr(trajectory, "metadata", {}) or {})
    selected = str(selected_engine_name).lower()
    trajectory_name = str(trajectory.engine).lower()
    if selected in {"qoptics", "qtoolbox"} or trajectory_name in {"qoptics", "qtoolbox"}:
        julia_ver = str(meta.get("julia_version", "")).strip()
        backend = str(meta.get("julia_backend", "")).strip()
        backend_ver = str(meta.get("julia_backend_version", "")).strip()
        if julia_ver:
            deps["julia"] = julia_ver
        if backend:
            deps[f"julia_backend:{backend}"] = backend_ver or "unknown"
    return deps


__all__ = [
    "canonical_engine_name",
    "collect_runtime_dependencies",
    "run_cross_engine_compare",
    "select_engine",
    "trajectory_pair_metrics",
    "trajectory_summary",
]

