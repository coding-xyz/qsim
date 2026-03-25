"""Task/Solver/Hardware config loading, template merge, and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from qsim.backend.config import validate_backend_config
from qsim.workflow.contracts import (
    SolverBackendConfig,
    TaskInputConfig,
    WorkflowDeviceConfig,
    WorkflowFeatureFlags,
    WorkflowFrameOptions,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
    normalize_targets,
)


_TASK_TOP_KEYS = {"schema_version", "target", "input", "features", "output", "tags", "template", "targets", "task"}
_TASK_INPUT_KEYS = {"qasm_text", "qasm_path", "solver_config", "device_config", "pulse_config", "param_bindings"}
_TASK_OUTPUT_KEYS = {
    "out_dir",
    "persist_artifacts",
    "artifact_mode",
    "export_dxf",
    "export_plots",
    "session_dir",
    "session_auto_commit",
    "session_commit_kinds",
}
_TASK_FEATURE_KEYS = {
    "pauli_plus_analysis",
    "pauli_plus_code_distances",
    "pauli_plus_shots",
    "decoder_eval",
    "eval_decoders",
    "eval_seeds",
    "eval_option_grid",
    "eval_parallelism",
    "eval_retries",
    "eval_resume",
}

_TARGET_FEATURE_KEYS: dict[str, set[str]] = {
    "trace": set(),
    "logical_error": set(),
    "sensitivity_report": set(),
    "decoder_eval_report": {
        "decoder_eval",
        "eval_decoders",
        "eval_seeds",
        "eval_option_grid",
        "eval_parallelism",
        "eval_retries",
        "eval_resume",
    },
    "scaling_report": {"pauli_plus_analysis", "pauli_plus_code_distances", "pauli_plus_shots"},
    "error_budget_pauli_plus": {"pauli_plus_analysis", "pauli_plus_code_distances", "pauli_plus_shots"},
    "cross_engine_compare": set(),
}

_SOLVER_TOP_KEYS = {"schema_version", "template", "backend", "run", "frame", "solver"}
_SOLVER_BACKEND_KEYS = {"level", "analysis_pipeline", "analysis", "truncation"}
_SOLVER_FRAME_KEYS = {"mode", "reference", "rwa", "qubit_reference_freqs_Hz"}
_SOLVER_RUN_COMMON_KEYS = {
    "engine",
    "solver_mode",
    "sweep",
    "seed",
    "dt_s",
    "t_end_s",
    "t_padding_s",
    "schedule_policy",
    "schedule",
    "reset_feedback_policy",
    "compare_engines",
    "allow_mock_fallback",
    "mcwf_ntraj",
    "prior_backend",
    "decoder",
    "decoder_options",
    "qec_engine",
}
_SOLVER_RUN_JULIA_KEYS = {"julia_bin", "julia_depot_path", "julia_timeout_s"}

_DEVICE_TOP_KEYS = {"schema_version", "template", "device", "noise"}
_PULSE_TOP_KEYS = {"schema_version", "template", "pulse"}


def _is_v3_task_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("task"), dict)


def _is_v3_solver_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("solver"), dict)


def _is_v3_pulse_payload(payload: dict[str, Any]) -> bool:
    raw_pulse = payload.get("pulse", {}) or {}
    return isinstance(raw_pulse, dict) and any(k in raw_pulse for k in {"channels", "carriers", "waveforms", "operations", "acquisition"})


def _map_v3_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    task = dict(payload.get("task", {}) or {})
    task_input = dict(task.get("input", {}) or {})
    task_output = dict(task.get("output", {}) or {})
    qasm_text = task_input.get("qasm_text")
    sequence = task.get("sequence")
    if not qasm_text and isinstance(sequence, dict):
        qasm_text = sequence.get("qasm_text")
    mapped: dict[str, Any] = {
        "schema_version": str(payload.get("schema_version", "3.0")),
        "target": "trace",
        "input": {
            "qasm_text": qasm_text,
            "solver_config": task_input.get("solver_config"),
            "device_config": task_input.get("device_config"),
            "pulse_config": task_input.get("pulse_config"),
            "param_bindings": dict(task_input.get("param_bindings", {}) or {}) or None,
        },
        "output": {
            "out_dir": task_output.get("out_dir", "runs/qsim"),
            "persist_artifacts": bool(task_output.get("persist_artifacts", True)),
            "artifact_mode": str(task_output.get("artifact_mode", "all")),
            "export_dxf": bool(task_output.get("export_dxf", False)),
            "export_plots": bool(task_output.get("export_plots", False)),
        },
        "tags": [str(task.get("experiment", "task")).strip().lower()],
    }
    return mapped


def _map_v3_pulse_payload(raw_pulse: dict[str, Any]) -> dict[str, Any]:
    channels = list(raw_pulse.get("channels", []) or [])
    carriers = dict(raw_pulse.get("carriers", {}) or {})
    waveforms = dict(raw_pulse.get("waveforms", {}) or {})
    operations = dict(raw_pulse.get("operations", {}) or {})
    acquisition = dict(raw_pulse.get("acquisition", {}) or {})

    def _carrier_freq_for_kind(kind: str, default: float) -> float:
        for ch in channels:
            if not isinstance(ch, dict):
                continue
            if str(ch.get("kind", "")).strip().lower() != kind:
                continue
            name = str(ch.get("name", ""))
            if isinstance(carriers.get(name), dict) and "freq_Hz" in carriers[name]:
                return float(carriers[name]["freq_Hz"])
        return float(default)

    def _waveform_from_operation(name: str, fallback_shapes: set[str]) -> dict[str, Any]:
        steps = list(operations.get(name, []) or [])
        for step in steps:
            if not isinstance(step, dict):
                continue
            wf_name = str(step.get("waveform", ""))
            if wf_name and isinstance(waveforms.get(wf_name), dict):
                return dict(waveforms[wf_name])
        for wf in waveforms.values():
            if isinstance(wf, dict) and str(wf.get("shape", "")).strip().lower() in fallback_shapes:
                return dict(wf)
        return {}

    gate_wf = _waveform_from_operation("x", {"drag", "gaussian", "rect"})
    measure_wf = _waveform_from_operation("measure", {"readout", "rect"})

    mapped: dict[str, Any] = {}
    mapped["xy_freq_Hz"] = _carrier_freq_for_kind("drive", 5.0e9)
    mapped["ro_freq_Hz"] = _carrier_freq_for_kind("readout_drive", mapped["xy_freq_Hz"])
    if "duration_ns" in gate_wf:
        mapped["gate_duration_ns"] = float(gate_wf["duration_ns"])
    if "duration_ns" in measure_wf:
        mapped["measure_duration_ns"] = float(measure_wf["duration_ns"])
    if "edge_ns" in measure_wf:
        mapped["readout_edge_ns"] = float(measure_wf["edge_ns"])
    if "integration_window_ns" in acquisition:
        mapped["measure_duration_ns"] = float(acquisition["integration_window_ns"])
    schedule_cfg = dict(raw_pulse.get("schedule", {}) or {})
    if schedule_cfg.get("policy"):
        mapped["schedule_policy"] = str(schedule_cfg.get("policy"))
    return mapped


def _resolve_path(base_dir: Path, value: str | None) -> str | None:
    if not value:
        return value
    p = Path(value)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return str(p)


def _load_mapping(path: str | Path) -> tuple[Path, dict[str, Any]]:
    p = Path(path).resolve()
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        payload = json.loads(text)
    elif p.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    else:
        raise ValueError(f"Unsupported config extension: {p.suffix}. Use .json/.yaml/.yml")
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must be a mapping object: {p}")
    return p, dict(payload)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(dict(merged[key]), dict(value))
        else:
            merged[key] = value
    return merged


def _template_file(kind: str, template_name: str) -> Path:
    root = Path(__file__).resolve().parent / "templates" / kind
    stem = str(template_name).strip()
    candidates = [root / f"{stem}.yaml", root / f"{stem}.yml", root / f"{stem}.json"]
    for c in candidates:
        if c.exists():
            return c
    raise ValueError(f"Unknown {kind} template: {template_name!r}")


def _apply_template(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    template_name = payload.get("template")
    if not template_name:
        return payload
    template_path = _template_file(kind, str(template_name))
    _, template_payload = _load_mapping(template_path)
    merged = _deep_merge(template_payload, {k: v for k, v in payload.items() if k != "template"})
    return merged


def _reject_unknown(section: str, keys: set[str], allowed: set[str]) -> None:
    unknown = sorted(keys - allowed)
    if unknown:
        raise ValueError(f"Unsupported keys in {section}: {unknown}")


def _normalize_targets_from_task_payload(payload: dict[str, Any]) -> list[str]:
    if "target" in payload:
        return normalize_targets(payload["target"])
    if "targets" in payload:
        return normalize_targets(payload["targets"])
    raise ValueError("Task config requires `target`.")


def _validate_task_payload(
    payload: dict[str, Any],
    *,
    require_solver_config: bool = True,
    require_device_config: bool = True,
) -> list[str]:
    _reject_unknown("task top-level", set(payload), _TASK_TOP_KEYS)

    targets = _normalize_targets_from_task_payload(payload)
    unknown_targets = sorted([t for t in targets if t not in _TARGET_FEATURE_KEYS])
    if unknown_targets:
        raise ValueError(f"Unknown task target(s): {unknown_targets}")

    raw_input = payload.get("input")
    if not isinstance(raw_input, dict):
        raise ValueError("Task config requires `input` mapping.")
    _reject_unknown("task.input", set(raw_input), _TASK_INPUT_KEYS)

    qasm_text = raw_input.get("qasm_text")
    qasm_path = raw_input.get("qasm_path")
    if bool(qasm_text) == bool(qasm_path):
        raise ValueError("Task config must provide exactly one of input.qasm_text or input.qasm_path.")
    if require_solver_config and not raw_input.get("solver_config"):
        raise ValueError("Task config requires input.solver_config.")
    if require_device_config and not raw_input.get("device_config"):
        raise ValueError("Task config requires input.device_config.")

    raw_output = payload.get("output", {}) or {}
    if not isinstance(raw_output, dict):
        raise ValueError("Task config `output` must be a mapping.")
    _reject_unknown("task.output", set(raw_output), _TASK_OUTPUT_KEYS)
    if not raw_output.get("out_dir"):
        raise ValueError("Task config requires output.out_dir.")

    raw_features = payload.get("features", {}) or {}
    if not isinstance(raw_features, dict):
        raise ValueError("Task config `features` must be a mapping.")
    _reject_unknown("task.features", set(raw_features), _TASK_FEATURE_KEYS)

    allowed_feature_keys: set[str] = set()
    for t in targets:
        allowed_feature_keys.update(_TARGET_FEATURE_KEYS[t])
    disallowed_feature_keys = sorted(set(raw_features) - allowed_feature_keys)
    if disallowed_feature_keys:
        raise ValueError(
            "Task features contain keys not supported by selected target(s): "
            f"{disallowed_feature_keys}; targets={targets}"
        )

    return targets


def _validate_solver_payload(payload: dict[str, Any]) -> str:
    _reject_unknown("solver top-level", set(payload), _SOLVER_TOP_KEYS)
    raw_backend = payload.get("backend", {}) or {}
    raw_run = payload.get("run", {}) or {}
    raw_frame = payload.get("frame", {}) or {}

    if not isinstance(raw_backend, dict):
        raise ValueError("Solver config `backend` must be a mapping.")
    if not isinstance(raw_run, dict):
        raise ValueError("Solver config `run` must be a mapping.")
    if not isinstance(raw_frame, dict):
        raise ValueError("Solver config `frame` must be a mapping.")

    _reject_unknown("solver.backend", set(raw_backend), _SOLVER_BACKEND_KEYS)
    _reject_unknown("solver.run", set(raw_run), _SOLVER_RUN_COMMON_KEYS | _SOLVER_RUN_JULIA_KEYS)
    _reject_unknown("solver.frame", set(raw_frame), _SOLVER_FRAME_KEYS)

    engine = str(raw_run.get("engine", "qutip")).strip().lower()
    if engine not in {"qutip", "qoptics", "qtoolbox"}:
        raise ValueError(f"Unsupported solver.run.engine: {engine!r}. Supported engines: qutip, qoptics, qtoolbox.")
    allowed_run = set(_SOLVER_RUN_COMMON_KEYS)
    is_julia = engine in {"qoptics", "qtoolbox"}
    if is_julia:
        allowed_run.update(_SOLVER_RUN_JULIA_KEYS)

    disallowed_run = sorted(set(raw_run) - allowed_run)
    if disallowed_run:
        raise ValueError(
            "Solver `run` contains keys not supported by selected engine "
            f"{engine!r}: {disallowed_run}"
        )
    return engine


def _validate_device_payload(payload: dict[str, Any]) -> None:
    _reject_unknown("device top-level", set(payload), _DEVICE_TOP_KEYS)
    raw_device = payload.get("device", {}) or {}
    raw_noise = payload.get("noise", {}) or {}
    if not isinstance(raw_device, dict):
        raise ValueError("Device config `device` must be a mapping.")
    if not isinstance(raw_noise, dict):
        raise ValueError("Device config `noise` must be a mapping.")


def _validate_pulse_payload(payload: dict[str, Any]) -> None:
    _reject_unknown("pulse top-level", set(payload), _PULSE_TOP_KEYS)
    raw_pulse = payload.get("pulse", {}) or {}
    if not isinstance(raw_pulse, dict):
        raise ValueError("Pulse config `pulse` must be a mapping.")


def load_task_config_file(
    path: str | Path,
    *,
    require_solver_config: bool = True,
    require_device_config: bool = True,
) -> WorkflowTaskConfig:
    """Load a task config file into ``WorkflowTaskConfig``.

    The task config is the workflow-facing entry file that describes targets,
    input references, optional features, and output policy.

    Args:
        path: Path to a JSON or YAML task config file.
        require_solver_config: Whether ``input.solver_config`` must be present
            when no external override is provided.
        require_device_config: Whether ``input.device_config`` must be present
            when no external override is provided.

    Returns:
        Parsed and validated ``WorkflowTaskConfig``.
    """
    cfg_path, payload = _load_mapping(path)
    payload = _apply_template("tasks", payload)
    if _is_v3_task_payload(payload):
        payload = _map_v3_task_payload(payload)
    base_dir = cfg_path.parent

    targets = _validate_task_payload(
        payload,
        require_solver_config=require_solver_config,
        require_device_config=require_device_config,
    )
    raw_input = dict(payload.get("input", {}) or {})

    qasm_text = raw_input.get("qasm_text")
    qasm_path = raw_input.get("qasm_path")
    if qasm_path:
        qasm_full = Path(_resolve_path(base_dir, str(qasm_path)))
        qasm_text = qasm_full.read_text(encoding="utf-8")

    task = WorkflowTaskConfig(
        target=targets,
        input=TaskInputConfig(
            qasm_text=str(qasm_text),
            solver_config_path=_resolve_path(base_dir, str(raw_input.get("solver_config"))),
            device_config_path=_resolve_path(base_dir, str(raw_input.get("device_config"))),
            pulse_config_path=_resolve_path(base_dir, str(raw_input.get("pulse_config"))),
            param_bindings=dict(raw_input.get("param_bindings", {}) or {}) or None,
        ),
        features=WorkflowFeatureFlags(**dict(payload.get("features", {}) or {})),
        output=WorkflowOutputOptions(**dict(payload.get("output", {}) or {})),
        tags=list(payload.get("tags", []) or []),
    )
    task.output.out_dir = _resolve_path(base_dir, task.output.out_dir) or task.output.out_dir
    task.output.session_dir = _resolve_path(base_dir, task.output.session_dir)
    return task


def load_solver_config_file(path: str | Path) -> WorkflowSolverConfig:
    """Load a solver config file into ``WorkflowSolverConfig``.

    The solver config controls the backend model level, runtime engine
    selection, solver options, and reference-frame settings.
    """
    cfg_path, payload = _load_mapping(path)
    payload = _apply_template("solvers", payload)
    if _is_v3_solver_payload(payload):
        solver = dict(payload.get("solver", {}) or {})
        engine = str(solver.get("engine", "qutip")).strip().lower()
        if engine not in {"qutip", "qoptics", "qtoolbox"}:
            raise ValueError(f"Unsupported solver.engine: {engine!r}. Supported engines: qutip, qoptics, qtoolbox.")
        raw_study = [dict(step) for step in list(solver.get("study", []) or []) if isinstance(step, dict)] or None
        raw_analysis = dict(solver.get("analysis", {}) or {}) or None
        raw_schedule = dict(solver.get("schedule", {}) or {})
        raw_run = {
            "engine": engine,
            "seed": int(solver.get("seed", 12345)),
            "schedule_policy": raw_schedule.get("policy"),
        }
        solver_cfg = WorkflowSolverConfig(
            backend=SolverBackendConfig(level="qubit", analysis_pipeline="structured", truncation={}),
            run=WorkflowRunOptions(**raw_run),
            frame=WorkflowFrameOptions(),
            analysis=raw_analysis,
            study=raw_study,
        )
        if raw_run.get("julia_bin"):
            solver_cfg.run.julia_bin = _resolve_path(cfg_path.parent, str(raw_run["julia_bin"]))
        if raw_run.get("julia_depot_path"):
            solver_cfg.run.julia_depot_path = _resolve_path(cfg_path.parent, str(raw_run["julia_depot_path"]))
        validate_backend_config(solver_cfg.to_backend_config())
        return solver_cfg
    base_dir = cfg_path.parent

    _validate_solver_payload(payload)
    raw_backend = dict(payload.get("backend", {}) or {})
    raw_run = dict(payload.get("run", {}) or {})
    raw_frame = dict(payload.get("frame", {}) or {})

    if "analysis" in raw_backend and "analysis_pipeline" not in raw_backend:
        raw_backend["analysis_pipeline"] = raw_backend["analysis"]
    if "schedule" in raw_run and "schedule_policy" not in raw_run:
        raw_run["schedule_policy"] = raw_run["schedule"]

    if raw_run.get("julia_bin"):
        raw_run["julia_bin"] = _resolve_path(base_dir, str(raw_run["julia_bin"]))
    if raw_run.get("julia_depot_path"):
        raw_run["julia_depot_path"] = _resolve_path(base_dir, str(raw_run["julia_depot_path"]))

    solver_cfg = WorkflowSolverConfig(
        backend=SolverBackendConfig(**raw_backend),
        run=WorkflowRunOptions(**raw_run),
        frame=WorkflowFrameOptions(**raw_frame),
    )
    validate_backend_config(solver_cfg.to_backend_config())
    return solver_cfg


def load_device_config_file(path: str | Path) -> WorkflowDeviceConfig:
    """Load a device config file into ``WorkflowDeviceConfig``.

    Device configs contain device-level parameters and noise model settings.
    """
    _cfg_path, payload = _load_mapping(path)
    payload = _apply_template("device", payload)

    _validate_device_payload(payload)
    raw_device = dict(payload.get("device", {}) or {})
    nested_noise = dict(raw_device.get("noise", {}) or {}) if isinstance(raw_device.get("noise"), dict) else {}
    raw_device = {k: v for k, v in raw_device.items() if k != "noise"}
    top_noise = dict(payload.get("noise", {}) or {})
    return WorkflowDeviceConfig(
        device=raw_device or None,
        noise=top_noise or nested_noise or None,
    )


def load_pulse_config_file(path: str | Path) -> dict[str, Any]:
    """Load a pulse config file.

    Pulse configs contain gate duration, carrier frequency, readout, and reset
    pulse parameters. The returned mapping is later merged into
    ``WorkflowDeviceConfig.pulse``.
    """
    _cfg_path, payload = _load_mapping(path)
    payload = _apply_template("pulses", payload)
    _validate_pulse_payload(payload)
    raw_pulse = dict(payload.get("pulse", {}) or {})
    if _is_v3_pulse_payload(payload):
        return _map_v3_pulse_payload(raw_pulse)
    return raw_pulse


def load_task_file(path: str | Path) -> WorkflowTaskConfig:
    """Compatibility alias: load task-config only."""
    return load_task_config_file(path)


def load_config_bundle_files(
    *,
    task_config: str | Path,
    solver_config: str | Path | None = None,
    device_config: str | Path | None = None,
    pulse_config: str | Path | None = None,
) -> WorkflowTask:
    """Load and compose a 4-file config bundle into ``WorkflowTask``.

    This is the main file-driven composition helper used by the CLI and by
    ``run_task_files``.
    """
    task_cfg = load_task_config_file(
        task_config,
        require_solver_config=(solver_config is None),
        require_device_config=(device_config is None),
    )
    solver_path = str(solver_config) if solver_config is not None else task_cfg.input.solver_config_path
    device_path = str(device_config) if device_config is not None else task_cfg.input.device_config_path
    pulse_path = str(pulse_config) if pulse_config is not None else task_cfg.input.pulse_config_path
    if not solver_path:
        raise ValueError("Task input must provide solver_config, or pass solver_config override.")
    if not device_path:
        raise ValueError("Task input must provide device_config, or pass device_config override.")
    solver_cfg = load_solver_config_file(solver_path)
    device_cfg = load_device_config_file(device_path)
    if pulse_path:
        device_cfg.pulse = {**dict(device_cfg.pulse or {}), **load_pulse_config_file(pulse_path)}
    return compose_workflow_task(task_cfg, solver_cfg, device_cfg, backend_source=str(Path(solver_path).resolve()))


__all__ = [
    "load_config_bundle_files",
    "load_device_config_file",
    "load_pulse_config_file",
    "load_solver_config_file",
    "load_task_config_file",
    "load_task_file",
]
