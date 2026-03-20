"""Workflow contracts for task/solver/device-driven execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from qsim.common.schemas import BackendConfig


@dataclass(slots=True)
class WorkflowInput:
    """Merged runtime input payload used by pipeline stages."""

    qasm_text: str
    backend_path: str | None = None
    backend_config: BackendConfig | None = None
    device: dict | None = None
    pulse: dict | None = None
    frame: dict | None = None
    schedule_policy: str | None = None
    reset_feedback_policy: str | None = None
    noise: dict | None = None
    param_bindings: dict[str, float] | None = None


@dataclass(slots=True)
class WorkflowRunOptions:
    """Runtime engine and decoder options."""

    engine: str = "qutip"
    solver_mode: str | None = None
    sweep: list[dict] | None = None
    seed: int | None = None
    dt_s: float | None = None
    t_end_s: float | None = None
    t_padding_s: float | None = None
    schedule_policy: str | None = None
    reset_feedback_policy: str | None = None
    compare_engines: list[str] | None = None
    allow_mock_fallback: bool = False
    julia_bin: str | None = None
    julia_depot_path: str | None = None
    julia_timeout_s: float = 120.0
    mcwf_ntraj: int = 128
    prior_backend: str = "auto"
    decoder: str | None = None
    decoder_options: dict | None = None
    qec_engine: str = "auto"


@dataclass(slots=True)
class WorkflowFrameOptions:
    """Reference-frame and RWA controls for model construction/engines."""

    mode: str = "rotating"
    reference: str = "pulse_carrier"
    rwa: bool = True
    qubit_reference_freqs_Hz: list[float] | None = None


@dataclass(slots=True)
class WorkflowFeatureFlags:
    """Optional feature branches toggles and settings."""

    pauli_plus_analysis: bool = False
    pauli_plus_code_distances: list[int] | None = None
    pauli_plus_shots: int = 20000
    decoder_eval: bool = False
    eval_decoders: list[str] | None = None
    eval_seeds: list[int] | None = None
    eval_option_grid: list[dict] | None = None
    eval_parallelism: int = 1
    eval_retries: int = 0
    eval_resume: bool = False


@dataclass(slots=True)
class WorkflowOutputOptions:
    """Output and persistence policy."""

    out_dir: str = "runs/qsim"
    persist_artifacts: bool = True
    artifact_mode: str = "all"
    export_dxf: bool = True
    export_plots: bool = True
    session_dir: str | None = None
    session_auto_commit: bool = False
    session_commit_kinds: list[str] | None = None


@dataclass(slots=True)
class WorkflowTask:
    """Canonical merged runtime contract consumed by pipeline."""

    input: WorkflowInput
    run: WorkflowRunOptions = field(default_factory=WorkflowRunOptions)
    features: WorkflowFeatureFlags = field(default_factory=WorkflowFeatureFlags)
    output: WorkflowOutputOptions = field(default_factory=WorkflowOutputOptions)
    template: str | None = None
    targets: list[str] | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskInputConfig:
    """Task-level input with references to solver/device/pulse config files."""

    qasm_text: str
    solver_config_path: str | None = None
    device_config_path: str | None = None
    pulse_config_path: str | None = None
    param_bindings: dict[str, float] | None = None


@dataclass(slots=True)
class WorkflowTaskConfig:
    """Task config: target + input/output/features."""

    target: str | list[str]
    input: TaskInputConfig
    output: WorkflowOutputOptions = field(default_factory=WorkflowOutputOptions)
    features: WorkflowFeatureFlags = field(default_factory=WorkflowFeatureFlags)
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SolverBackendConfig:
    """Solver-side backend model configuration."""

    level: str = "qubit"
    analysis_pipeline: str = "default"
    truncation: dict = field(default_factory=dict)


def _normalize_backend_noise_mode(noise: dict | None) -> str:
    model = str((noise or {}).get("model", "")).strip().lower()
    if "lindblad" in model:
        return "lindblad"
    if model in {"sde", "tls", "hybrid", "deterministic"}:
        return model
    return "deterministic"


@dataclass(slots=True)
class WorkflowSolverConfig:
    """Solver config: backend model + engine/runtime controls."""

    backend: SolverBackendConfig = field(default_factory=SolverBackendConfig)
    run: WorkflowRunOptions = field(default_factory=WorkflowRunOptions)
    frame: WorkflowFrameOptions = field(default_factory=WorkflowFrameOptions)

    def to_backend_config(self, *, noise: dict | None = None) -> BackendConfig:
        """Convert to ``BackendConfig`` dataclass for pipeline internals."""
        return BackendConfig(
            level=str(self.backend.level),
            noise=_normalize_backend_noise_mode(noise),
            solver=str(self.run.solver_mode or "se"),
            analysis_pipeline=str(self.backend.analysis_pipeline),
            truncation=dict(self.backend.truncation or {}),
            sweep=list(self.run.sweep or []),
            seed=int(self.run.seed if self.run.seed is not None else 1234),
        )


@dataclass(slots=True)
class WorkflowDeviceConfig:
    """Device/pulse/noise config independent from task and solver."""

    device: dict | None = None
    pulse: dict | None = None
    noise: dict | None = None


def normalize_device_payload(device: dict | None) -> dict[str, object]:
    raw = dict(device or {})
    qubits = list(raw.get("qubits", []) or [])
    normalized = {k: v for k, v in raw.items() if k != "qubits"}
    if qubits:
        if "qubit_freqs_Hz" not in normalized:
            normalized["qubit_freqs_Hz"] = [float((q or {}).get("freq_Hz", 0.0)) for q in qubits]
        if "anharmonicity_Hz" not in normalized:
            normalized["anharmonicity_Hz"] = [float((q or {}).get("anharmonicity_Hz", -0.2)) for q in qubits]
        for src_key, dst_key in (
            ("T1_s", "T1_s"),
            ("T2_s", "T2_s"),
            ("Tphi_s", "Tphi_s"),
            ("Tup_s", "Tup_s"),
            ("gamma1_Hz", "gamma1_Hz"),
            ("gamma_phi_Hz", "gamma_phi_Hz"),
            ("gamma_up_Hz", "gamma_up_Hz"),
        ):
            if dst_key not in normalized and any(src_key in (q or {}) for q in qubits):
                normalized[dst_key] = [float((q or {}).get(src_key, 0.0)) for q in qubits]
    return normalized


def normalize_targets(value: str | list[str]) -> list[str]:
    """Normalize one-or-many target field to deduplicated lowercase list."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(v) for v in value]
    else:
        raise ValueError("`task.target` must be a string or a list of strings.")
    cleaned = [v.strip().lower() for v in items if str(v).strip()]
    if not cleaned:
        raise ValueError("`task.target` must not be empty.")
    return list(dict.fromkeys(cleaned))


def compose_workflow_task(
    task_cfg: WorkflowTaskConfig,
    solver_cfg: WorkflowSolverConfig,
    device_cfg: WorkflowDeviceConfig,
    *,
    backend_source: str | None = None,
) -> WorkflowTask:
    """Compose 3-way configs into one canonical runtime task contract."""
    runtime_device = dict(device_cfg.device or {})
    if "simulation_level" not in runtime_device:
        runtime_device["simulation_level"] = str(solver_cfg.backend.level).strip().lower()

    return WorkflowTask(
        input=WorkflowInput(
            qasm_text=task_cfg.input.qasm_text,
            backend_path=backend_source,
            backend_config=solver_cfg.to_backend_config(noise=device_cfg.noise),
            device=runtime_device or None,
            pulse=dict(device_cfg.pulse or {}) or None,
            frame=asdict(solver_cfg.frame),
            schedule_policy=(
                str(solver_cfg.run.schedule_policy).strip().lower() if solver_cfg.run.schedule_policy else None
            ),
            reset_feedback_policy=(
                str(solver_cfg.run.reset_feedback_policy).strip().lower()
                if solver_cfg.run.reset_feedback_policy
                else None
            ),
            noise=dict(device_cfg.noise or {}),
            param_bindings=dict(task_cfg.input.param_bindings or {}) or None,
        ),
        run=solver_cfg.run,
        features=task_cfg.features,
        output=task_cfg.output,
        targets=normalize_targets(task_cfg.target),
        tags=list(task_cfg.tags or []),
    )


__all__ = [
    "TaskInputConfig",
    "SolverBackendConfig",
    "WorkflowFeatureFlags",
    "WorkflowDeviceConfig",
    "WorkflowInput",
    "WorkflowOutputOptions",
    "WorkflowRunOptions",
    "WorkflowSolverConfig",
    "WorkflowTask",
    "WorkflowTaskConfig",
    "compose_workflow_task",
    "normalize_targets",
]
