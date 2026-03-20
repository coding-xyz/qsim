"""Minimal helpers for Task-style qsim runs and reference comparison."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
SRC_DIR = THIS_DIR.parents[1] / "src"
REQUIRED_TASK_DIR = THIS_DIR / "required_tasks"
REFERENCE_DIR = THIS_DIR / "references"
DEFAULT_RUN_DIR = THIS_DIR / "runs" / "minimal_notebooks"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qsim.analysis.trace_semantics import extract_p1_series, state_encoding
from qsim.common.schemas import BackendConfig
from qsim.workflow import run_task
from qsim.workflow.contracts import WorkflowInput, WorkflowOutputOptions, WorkflowRunOptions, WorkflowTask


DEFAULT_TRUNCATION = {"transmon_levels": 3, "cavity_nmax": 8}
ENGINE_TO_REFERENCE = {
    "qutip": "qutip_native",
    "julia_qoptics": "julia_qoptics_native",
    "julia_qtoolbox": "julia_quantumtoolbox_native",
}


def _mean(values: list[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def _noise_mode(noise: dict[str, Any] | None) -> str:
    model = str((noise or {}).get("model", "")).strip().lower()
    return "lindblad" if "lindblad" in model else (model or "deterministic")


def _resolve_task_path(task_config: str | Path) -> Path:
    path = Path(task_config)
    if path.is_absolute():
        return path

    for candidate in [Path.cwd() / path, THIS_DIR / path, REQUIRED_TASK_DIR / path]:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return path.resolve()


def _load_task(task_config: str | Path) -> dict[str, Any]:
    return json.loads(_resolve_task_path(task_config).read_text(encoding="utf-8"))


def _pick_cases(task: dict[str, Any], cases: list[str] | None) -> list[dict[str, Any]]:
    all_cases = list(task.get("cases", []) or [])
    if not cases:
        return all_cases

    wanted = {str(case).strip() for case in cases}
    selected = [case for case in all_cases if str(case.get("tag", "")).strip() in wanted]
    if len(selected) != len(wanted):
        missing = sorted(wanted - {str(case.get("tag", "")).strip() for case in selected})
        raise ValueError(f"Unknown case tag(s): {', '.join(missing)}")
    return selected


def _pick_engines(task: dict[str, Any], engines: list[str] | None) -> list[str]:
    values = engines if engines else (task.get("engines", []) or ["qutip"])
    return [str(engine).strip() for engine in values if str(engine).strip()]


def _build_workflow_task(
    task: dict[str, Any],
    *,
    case: dict[str, Any],
    engine: str,
    out_dir: Path,
    persist_artifacts: bool,
    export_plots: bool,
    export_dxf: bool,
    seed: int,
    allow_mock_fallback: bool,
) -> WorkflowTask:
    device = dict(case.get("device", {}) or {})
    pulse = dict(case.get("pulse", {}) or {})
    device.setdefault("simulation_level", "qubit")
    noise = dict(case.get("noise", {}) or {})
    solver_mode = str(task.get("solver_mode") or "me")
    backend = BackendConfig(
        level=str(device.get("simulation_level", "qubit")),
        noise=_noise_mode(noise),
        solver=solver_mode,
        analysis_pipeline="default",
        truncation=dict(DEFAULT_TRUNCATION),
        sweep=[],
        seed=int(seed),
    )

    return WorkflowTask(
        input=WorkflowInput(
            qasm_text=str(task["qasm_text"]),
            backend_config=backend,
            device=device,
            pulse=pulse,
            noise=noise,
        ),
        run=WorkflowRunOptions(
            engine=str(engine),
            solver_mode=solver_mode,
            allow_mock_fallback=allow_mock_fallback,
        ),
        output=WorkflowOutputOptions(
            out_dir=str(out_dir),
            persist_artifacts=bool(persist_artifacts),
            artifact_mode="targeted",
            export_dxf=bool(export_dxf),
            export_plots=bool(export_plots),
        ),
        targets=["trace"],
        tags=[str(task.get("tag") or "legacy_task"), str(case.get("tag") or "case"), str(engine)],
    )


def _run_reference_command(command: list[str], label: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        return {"engine": label, "status": "error", "note": str(exc), "cases": {}}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {"engine": label, "status": "error", "note": (stderr or stdout or f"exit={proc.returncode}"), "cases": {}}

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"engine": label, "status": "error", "note": f"invalid json: {exc}", "cases": {}}

    payload["status"] = "ok"
    payload["note"] = ""
    return payload


def run_qsim(
    task_config: str | Path,
    *,
    engines: list[str] | None = None,
    cases: list[str] | None = None,
    out_root: str | Path | None = None,
    persist_artifacts: bool = False,
    export_plots: bool = False,
    export_dxf: bool = False,
    seed: int = 12345,
    allow_mock_fallback: bool = False,
) -> dict[str, Any]:
    task_path = _resolve_task_path(task_config)
    task = _load_task(task_path)
    task_tag = str(task.get("tag") or task_path.stem)
    selected_cases = _pick_cases(task, cases)
    selected_engines = _pick_engines(task, engines)
    out_root_path = Path(out_root).resolve() if out_root else (DEFAULT_RUN_DIR / task_tag).resolve()

    rows: list[dict[str, Any]] = []
    runs: dict[str, dict[str, dict[str, Any]]] = {}

    for case in selected_cases:
        case_tag = str(case.get("tag") or "case")
        runs[case_tag] = {}
        for engine in selected_engines:
            workflow_task = _build_workflow_task(
                task,
                case=case,
                engine=engine,
                out_dir=out_root_path / case_tag / engine,
                persist_artifacts=persist_artifacts,
                export_plots=export_plots,
                export_dxf=export_dxf,
                seed=seed,
                allow_mock_fallback=allow_mock_fallback,
            )

            started_at = time.perf_counter()
            result = run_task(workflow_task)
            elapsed_s = time.perf_counter() - started_at
            trace = result["core"]["trace"]

            note = ""
            try:
                p1_t = [float(value) for value in extract_p1_series(trace)]
            except ValueError as exc:
                p1_t = []
                note = str(exc)

            times = [float(value) for value in list(getattr(trace, "times", []))[: len(p1_t)]]
            row = {
                "task": task_tag,
                "case": case_tag,
                "engine": engine,
                "elapsed_s": float(elapsed_s),
                "samples": int(len(list(getattr(trace, "times", [])))),
                "p1_samples": int(len(p1_t)),
                "final_p1": (float(p1_t[-1]) if p1_t else None),
                "mean_p1": _mean(p1_t),
                "state_encoding": state_encoding(trace),
                "solver_mode": result["runtime"]["solver_mode"],
                "out_dir": result["runtime"]["out_dir"],
                "note": note,
            }
            rows.append(row)
            runs[case_tag][engine] = {
                "row": row,
                "result": result,
                "trace": trace,
                "times": times,
                "p1_t": p1_t,
            }

    return {
        "task_path": str(task_path),
        "task": task,
        "task_tag": task_tag,
        "case_tags": [str(case.get("tag") or "case") for case in selected_cases],
        "engines": selected_engines,
        "rows": rows,
        "runs": runs,
    }


def run_reference(*, include_julia: bool = True, julia_bin: str = "julia") -> dict[str, dict[str, Any]]:
    references = {
        "qutip_native": _run_reference_command(
            [sys.executable, str(REFERENCE_DIR / "task1_qutip_native_reference.py")],
            "qutip_native",
        )
    }
    if include_julia:
        references["julia_qoptics_native"] = _run_reference_command(
            [julia_bin, str(REFERENCE_DIR / "task1_quantumoptics_native_reference.jl")],
            "julia_qoptics_native",
        )
        references["julia_quantumtoolbox_native"] = _run_reference_command(
            [julia_bin, str(REFERENCE_DIR / "task1_quantumtoolbox_native_reference.jl")],
            "julia_quantumtoolbox_native",
        )
    return references


def compare_runs(
    qsim_runs: dict[str, Any],
    references: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    refs = references or run_reference()
    rows: list[dict[str, Any]] = []

    for case_tag, case_runs in qsim_runs["runs"].items():
        for engine, run_info in case_runs.items():
            ref_key = ENGINE_TO_REFERENCE.get(engine, "")
            ref_payload = refs.get(ref_key, {})
            ref_case = dict(ref_payload.get("cases", {})).get(case_tag, {})
            qsim_p1 = list(run_info.get("p1_t", []) or [])
            ref_p1 = [float(value) for value in list(ref_case.get("p1_t", []) or [])]
            overlap = min(len(qsim_p1), len(ref_p1))

            row = {
                "case": case_tag,
                "engine": engine,
                "reference_engine": ref_key or None,
                "qsim_final_p1": run_info["row"]["final_p1"],
                "ref_final_p1": (float(ref_p1[-1]) if ref_p1 else None),
                "abs_final_p1_error": None,
                "qsim_mean_p1": run_info["row"]["mean_p1"],
                "ref_mean_p1": _mean(ref_p1),
                "abs_mean_p1_error": None,
                "curve_mae": None,
                "reference_status": ref_payload.get("status", "missing"),
                "note": str(ref_payload.get("note", "")),
            }
            if row["qsim_final_p1"] is not None and row["ref_final_p1"] is not None:
                row["abs_final_p1_error"] = abs(float(row["qsim_final_p1"]) - float(row["ref_final_p1"]))
            if row["qsim_mean_p1"] is not None and row["ref_mean_p1"] is not None:
                row["abs_mean_p1_error"] = abs(float(row["qsim_mean_p1"]) - float(row["ref_mean_p1"]))
            if overlap:
                row["curve_mae"] = float(
                    statistics.fmean(abs(float(qsim_p1[idx]) - float(ref_p1[idx])) for idx in range(overlap))
                )
            rows.append(row)
    return rows


def plot_case_series(
    qsim_runs: dict[str, Any],
    *,
    case_tag: str,
    references: dict[str, dict[str, Any]] | None = None,
):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for engine, run_info in dict(qsim_runs["runs"].get(case_tag, {})).items():
        if run_info["p1_t"]:
            ax.plot(run_info["times"], run_info["p1_t"], label=f"qsim:{engine}", linewidth=2)

    for ref_key, payload in (references or {}).items():
        if payload.get("status") != "ok":
            continue
        ref_case = dict(payload.get("cases", {})).get(case_tag, {})
        ref_p1 = list(ref_case.get("p1_t", []) or [])
        ref_times = list(ref_case.get("times", []) or [])[: len(ref_p1)]
        if ref_p1:
            ax.plot(ref_times, ref_p1, "--", label=ref_key, linewidth=1.5, alpha=0.85)

    ax.set_title(f"{qsim_runs['task_tag']} / {case_tag}")
    ax.set_xlabel("time")
    ax.set_ylabel("p1(t)")
    ax.grid(alpha=0.3)
    ax.legend()
    return fig, ax


# Thin compatibility aliases for current notebooks/scripts.
run_required_task_grid = run_qsim
load_task1_references = run_reference
compare_task1_to_references = compare_runs


def run_required_task_suite(
    *,
    task_configs: list[str | Path] | None = None,
    engines: list[str] | None = None,
    persist_artifacts: bool = False,
) -> dict[str, Any]:
    configs = [_resolve_task_path(path) for path in (task_configs or sorted(REQUIRED_TASK_DIR.glob("*.json")))]
    rows: list[dict[str, Any]] = []
    bundles: dict[str, dict[str, Any]] = {}
    for task_path in configs:
        bundle = run_qsim(task_path, engines=engines, persist_artifacts=persist_artifacts)
        bundles[bundle["task_tag"]] = bundle
        rows.extend(bundle["rows"])
    return {"task_paths": [str(path) for path in configs], "rows": rows, "bundles": bundles}


__all__ = [
    "DEFAULT_RUN_DIR",
    "REFERENCE_DIR",
    "REQUIRED_TASK_DIR",
    "compare_runs",
    "compare_task1_to_references",
    "load_task1_references",
    "plot_case_series",
    "run_qsim",
    "run_reference",
    "run_required_task_grid",
    "run_required_task_suite",
]
