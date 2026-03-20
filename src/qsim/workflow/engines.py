"""Engine-level workflow helpers."""

from __future__ import annotations

from qsim.analysis.trace_semantics import annotate_trace_metadata, pointwise_compare_compatibility, state_encoding
from qsim.engines.qoptics_engine import QOpticsEngine
from qsim.engines.qutip_engine import QuTiPEngine
from qsim.engines.qtoolbox_engine import QToolboxEngine


def select_engine(name: str):
    """Return an engine instance by user-facing name."""
    key = str(name).strip().lower()
    if key == "qutip":
        return QuTiPEngine()
    if key in {"qtoolbox", "quantumtoolbox"}:
        return QToolboxEngine()
    if key in {"qoptics", "quantumoptics"}:
        return QOpticsEngine()
    return QuTiPEngine()


def canonical_engine_name(name: str) -> str:
    """Normalize an engine name alias to canonical form."""
    key = str(name).strip().lower()
    if key in {"qtoolbox", "quantumtoolbox"}:
        return "qtoolbox"
    if key in {"qoptics", "quantumoptics"}:
        return "qoptics"
    if key == "qutip":
        return "qutip"
    return key


def trace_summary(trace) -> dict:
    """Build compact summary for trace payload."""
    last = trace.states[-1] if trace.states else []
    final_mean = float(sum(last) / len(last)) if last else 0.0
    return {
        "engine": trace.engine,
        "samples": len(trace.times),
        "state_dim": len(last),
        "final_state": [float(v) for v in last],
        "final_mean": final_mean,
        "state_encoding": state_encoding(trace),
        "metadata": dict(getattr(trace, "metadata", {}) or {}),
    }


def trace_pair_metrics(ref, other) -> dict:
    """Compute pointwise trace deltas when comparable."""
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
    d = 0
    if ref.states and other.states:
        d = min(len(ref.states[0]), len(other.states[0]))
    if d <= 0:
        return {"comparable": True, "samples_compared": n, "mse": 0.0, "mae": 0.0}
    sq_sum = 0.0
    abs_sum = 0.0
    count = 0
    for i in range(n):
        ra = ref.states[i]
        rb = other.states[i]
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
    traces = []
    for name in selected:
        engine = select_engine(name)
        run_opts = {
            "seed": int(seed),
            "solver_mode": model_spec.solver,
            "allow_mock_fallback": bool(allow_mock_fallback),
            "julia_timeout_s": float(julia_timeout_s),
            "ntraj": int(max(1, mcwf_ntraj)),
        }
        if julia_bin:
            run_opts["julia_bin"] = str(julia_bin)
        if julia_depot_path:
            run_opts["julia_depot_path"] = str(julia_depot_path)
        trace = engine.run(
            model_spec,
            run_options=run_opts,
        )
        annotate_trace_metadata(
            trace,
            num_qubits=int(model_spec.payload.get("num_qubits", 0) or 0) or None,
            dimension=int(getattr(model_spec, "dimension", 0) or 0) or None,
            engine_name=name,
        )
        traces.append((name, trace))
        item = trace_summary(trace)
        item["requested_engine"] = name
        runs.append(item)

    baseline_name, baseline_trace = traces[0]
    pairwise = []
    for name, trace in traces[1:]:
        pairwise.append(
            {
                "ref_engine": baseline_name,
                "other_engine": name,
                **trace_pair_metrics(baseline_trace, trace),
            }
        )

    return {
        "schema_version": "1.0",
        "status": "ok",
        "solver_mode": str(model_spec.solver),
        "baseline_engine": baseline_name,
        "runs": runs,
        "pairwise": pairwise,
    }


def collect_runtime_dependencies(trace, selected_engine_name: str) -> dict[str, str]:
    """Extract runtime dependency details from engine trace metadata."""
    deps: dict[str, str] = {}
    meta = dict(getattr(trace, "metadata", {}) or {})
    selected = str(selected_engine_name).lower()
    trace_name = str(trace.engine).lower()
    if selected in {"qoptics", "qtoolbox"} or trace_name in {"qoptics", "qtoolbox"}:
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
    "trace_pair_metrics",
    "trace_summary",
]
