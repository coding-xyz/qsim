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


_TASK_TOP_KEYS = {"schema_version", "target", "input", "features", "output", "tags", "template", "targets"}
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

_SOLVER_TOP_KEYS = {"schema_version", "template", "backend", "run", "frame"}
_SOLVER_BACKEND_KEYS = {"level", "analysis_pipeline", "truncation"}
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
    allowed_run = set(_SOLVER_RUN_COMMON_KEYS)
    is_julia = engine.startswith("julia") or engine in {"quantumoptics", "quantumtoolbox"}
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
    """Load task config (target/input/output/features) from JSON/YAML file."""
    cfg_path, payload = _load_mapping(path)
    payload = _apply_template("tasks", payload)
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
    """Load solver config (backend+run) from JSON/YAML file."""
    cfg_path, payload = _load_mapping(path)
    payload = _apply_template("solvers", payload)
    base_dir = cfg_path.parent

    _validate_solver_payload(payload)
    raw_backend = dict(payload.get("backend", {}) or {})
    raw_run = dict(payload.get("run", {}) or {})
    raw_frame = dict(payload.get("frame", {}) or {})

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
    """Load device/noise config from JSON/YAML file."""
    _cfg_path, payload = _load_mapping(path)
    payload = _apply_template("device", payload)

    _validate_device_payload(payload)
    raw_device = dict(payload.get("device", {}) or {})
    return WorkflowDeviceConfig(
        device=raw_device or None,
        noise=dict(payload.get("noise", {}) or {}) or None,
    )


def load_pulse_config_file(path: str | Path) -> dict[str, Any]:
    """Load pulse config from JSON/YAML file."""
    _cfg_path, payload = _load_mapping(path)
    payload = _apply_template("pulses", payload)
    _validate_pulse_payload(payload)
    return dict(payload.get("pulse", {}) or {})


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
    """Load and compose task/solver/device/pulse file set into ``WorkflowTask``."""
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
