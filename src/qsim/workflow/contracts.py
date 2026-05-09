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
    device_model: dict | None = None
    pulse: dict | None = None
    frame: dict | None = None
    analyser: dict | None = None
    study: list[dict] | None = None
    schedule_policy: str | None = None
    reset_feedback_policy: str | None = None
    noise: dict | None = None
    param_bindings: dict[str, float] | None = None

    @property
    def schedule(self) -> str | None:
        return self.schedule_policy

    @schedule.setter
    def schedule(self, value: str | None) -> None:
        self.schedule_policy = value


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
    qutip_options: dict | None = None
    native_options: dict | None = None
    backend_options: dict | None = None
    one_over_f_components: int | None = None

    @property
    def schedule(self) -> str | None:
        return self.schedule_policy

    @schedule.setter
    def schedule(self, value: str | None) -> None:
        self.schedule_policy = value


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
    analyser_config_path: str | None = None
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

    @property
    def analysis(self) -> str:
        return str(self.analysis_pipeline)

    @analysis.setter
    def analysis(self, value: str) -> None:
        self.analysis_pipeline = str(value)


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
    study: list[dict] | None = None

    def to_backend_config(self, *, noise: dict | None = None, runtime_level: str | None = None) -> BackendConfig:
        """Convert to ``BackendConfig`` dataclass for pipeline internals."""
        return BackendConfig(
            level=str(runtime_level or self.backend.level),
            noise=_normalize_backend_noise_mode(noise),
            solver=str(self.run.solver_mode or "se"),
            analysis_pipeline=str(self.backend.analysis_pipeline),
            truncation=dict(self.backend.truncation or {}),
            sweep=list(self.run.sweep or []),
            seed=int(self.run.seed if self.run.seed is not None else 1234),
        )


@dataclass(slots=True)
class DefaultAnalyserConfig:
    """Default analyser config bound to one solver trajectory."""

    solver_id: str | None = None
    trajectory: dict | None = None
    metrics: list[dict] | list[str] | None = None
    readout_model: dict | None = None
    iq_discrimination: dict | None = None
    noise_analysis: dict | None = None
    report: dict | None = None
    extras: dict | None = None

    def to_payload(self) -> dict[str, object]:
        """Convert to internal analyser payload consumed by analysis stages."""
        payload: dict[str, object] = {}
        if self.solver_id:
            payload["solver_id"] = str(self.solver_id)
        if self.trajectory:
            payload["trajectory"] = dict(self.trajectory)
        if self.metrics:
            payload["metrics"] = list(self.metrics)
        if self.readout_model:
            payload["readout_model"] = dict(self.readout_model)
        if self.iq_discrimination:
            payload["iq_discrimination"] = dict(self.iq_discrimination)
        if self.noise_analysis:
            payload["noise_analysis"] = dict(self.noise_analysis)
        if self.report:
            payload["report"] = dict(self.report)
        if self.extras:
            payload.update(dict(self.extras))
        return payload

    def __getattribute__(self, name: str):
        if name == "__annotations__":
            cls_annotations = type(self).__dict__.get("__annotations__", {})
            payload_keys = set(object.__getattribute__(self, "to_payload")().keys())
            return {key: value for key, value in cls_annotations.items() if key in payload_keys}
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        return f"DefaultAnalyserConfig({self.to_payload()!r})"


@dataclass(slots=True)
class WorkflowDeviceConfig:
    """Device/pulse/noise config independent from task and solver."""

    device: dict | None = None
    pulse: dict | None = None
    noise: dict | None = None


def _normalize_frame_reference_name(value: str | None) -> str:
    reference = str(value or "pulse_carrier").strip().lower()
    if reference == "carrier":
        return "pulse_carrier"
    if reference not in {"pulse_carrier", "explicit", "none"}:
        return "pulse_carrier"
    return reference


def infer_runtime_level(device: dict | None) -> str:
    """Infer legacy runtime level from old or composite device payload."""
    raw = dict(device or {})
    explicit = str(raw.get("simulation_level", "")).strip().lower()
    if explicit in {"qubit", "nlevel", "cqed"}:
        return explicit

    components = list(raw.get("components", []) or [])
    if components:
        has_quantum_resonator = False
        has_quantum_nlevel = False
        for comp in components:
            if not isinstance(comp, dict):
                continue
            representation = str(comp.get("representation", "quantum")).strip().lower()
            if representation != "quantum":
                continue
            basis = dict(comp.get("basis", {}) or {})
            basis_kind = str(basis.get("kind", "two_level")).strip().lower()
            if str(comp.get("type", "")).strip().lower() == "resonator" or basis_kind == "fock":
                has_quantum_resonator = True
            if basis_kind == "nlevel" and int(basis.get("levels", 2) or 2) > 2:
                has_quantum_nlevel = True
        if has_quantum_resonator:
            return "cqed"
        if has_quantum_nlevel:
            return "nlevel"
        return "qubit"

    if int(raw.get("cavity_nmax", 0) or 0) > 0:
        return "cqed"
    return "qubit"


def select_primary_study_step(study: list[dict] | None, *, fallback_solver_mode: str | None = None) -> dict[str, object]:
    """Select the current primary solver step from a composite study definition."""
    entries = [dict(step) for step in list(study or []) if isinstance(step, dict)]
    if not entries:
        return {}
    if fallback_solver_mode:
        wanted = str(fallback_solver_mode).strip().lower()
        for step in entries:
            if str(step.get("solver_mode", "")).strip().lower() == wanted:
                return step
    for step in entries:
        if step.get("solver_mode"):
            return step
    return entries[0]


def extract_study_prep(step: dict | None) -> dict[str, object]:
    """Extract state-preparation metadata from a study step."""
    selected = dict(step or {})
    prep_state = dict(selected.get("prep_state", {}) or {})
    return {
        "prep_label": str(prep_state.get("label", "") or "").strip(),
        "prep_sequence": list(prep_state.get("sequence", []) or []),
    }


def _normalize_component_representation(value: object) -> str:
    token = str(value or "").strip().lower()
    aliases = {"q": "quantum", "quantum": "quantum", "c": "classical", "classical": "classical"}
    return aliases.get(token, token)


def _normalize_component_basis(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    basis = dict(value)
    if "kind" in basis:
        basis["kind"] = str(basis.get("kind", "") or "").strip().lower()
    return basis


def apply_composite_device_step_overrides(device: dict | None, step: dict | None) -> dict[str, object]:
    """Apply study-step component overrides such as per-component representations/bases."""
    raw = dict(device or {})
    if "components" not in raw:
        return raw
    selected = dict(step or {})
    raw_representations = selected.get("representations", {})
    raw_bases = selected.get("bases", {})
    if not isinstance(raw_representations, dict):
        raw_representations = {}
    if not isinstance(raw_bases, dict):
        raw_bases = {}
    representation_overrides = {
        str(comp_id).strip(): _normalize_component_representation(value)
        for comp_id, value in raw_representations.items()
        if str(comp_id).strip() and str(value or "").strip()
    }
    basis_overrides = {
        str(comp_id).strip(): _normalize_component_basis(value)
        for comp_id, value in raw_bases.items()
        if str(comp_id).strip() and isinstance(value, dict)
    }
    if not representation_overrides and not basis_overrides:
        return raw
    components: list[dict[str, object]] = []
    for comp in list(raw.get("components", []) or []):
        if not isinstance(comp, dict):
            continue
        updated = dict(comp)
        comp_id = str(updated.get("id", "")).strip()
        if comp_id in representation_overrides:
            updated["representation"] = representation_overrides[comp_id]
        if comp_id in basis_overrides:
            updated["basis"] = basis_overrides[comp_id]
        components.append(updated)
    return {
        **raw,
        "components": components,
    }


def filter_composite_device_for_step(device: dict | None, step: dict | None) -> dict[str, object]:
    """Filter composite device payload by active components/connections of one study step."""
    raw = dict(device or {})
    if "components" not in raw:
        return raw
    step = dict(step or {})
    active_components = {str(item) for item in list(step.get("active_components", []) or []) if str(item).strip()}
    active_connections = {str(item) for item in list(step.get("active_connections", []) or []) if str(item).strip()}
    if not active_components and not active_connections:
        return raw

    components = [dict(comp) for comp in list(raw.get("components", []) or []) if isinstance(comp, dict)]
    connections = [dict(conn) for conn in list(raw.get("connections", []) or []) if isinstance(conn, dict)]
    filtered_connections = [dict(conn) for conn in connections]
    if active_connections:
        filtered_connections = [conn for conn in filtered_connections if str(conn.get("id", "")) in active_connections]

    implied_component_ids: set[str] = set()
    for conn in filtered_connections:
        implied_component_ids.update(
            {x for x in (str(conn.get("a", "")), str(conn.get("b", "")), str(conn.get("via", ""))) if x}
        )
    kept_component_ids = set(active_components) | implied_component_ids
    if kept_component_ids:
        components = [comp for comp in components if str(comp.get("id", "")) in kept_component_ids]
        kept_component_ids = {str(comp.get("id", "")) for comp in components}

    if not active_connections and active_components:
        filtered_connections = []
        for conn in connections:
            a = str(conn.get("a", ""))
            b = str(conn.get("b", ""))
            via = str(conn.get("via", ""))
            endpoint_ids = {x for x in (a, b, via) if x}
            if endpoint_ids and endpoint_ids.issubset(kept_component_ids):
                filtered_connections.append(conn)
    elif kept_component_ids:
        filtered_connections = [
            conn
            for conn in filtered_connections
            if {x for x in (str(conn.get("a", "")), str(conn.get("b", "")), str(conn.get("via", ""))) if x}.issubset(
                kept_component_ids
            )
        ]

    return {
        **{k: v for k, v in raw.items() if k not in {"components", "connections"}},
        "components": components,
        "connections": filtered_connections,
    }


def merge_solver_runtime_from_study(
    solver_cfg: WorkflowSolverConfig,
) -> tuple[WorkflowRunOptions, WorkflowFrameOptions, dict[str, object]]:
    """Apply primary study-step defaults onto runtime run/frame options."""
    run_cfg = WorkflowRunOptions(**asdict(solver_cfg.run))
    frame_cfg = WorkflowFrameOptions(**asdict(solver_cfg.frame))
    primary_step = select_primary_study_step(solver_cfg.study, fallback_solver_mode=run_cfg.solver_mode)
    if not primary_step:
        frame_cfg.reference = _normalize_frame_reference_name(frame_cfg.reference)
        return run_cfg, frame_cfg, {}

    if not run_cfg.solver_mode and primary_step.get("solver_mode"):
        run_cfg.solver_mode = str(primary_step.get("solver_mode")).strip().lower()

    time_cfg = dict(primary_step.get("time", {}) or {})
    if run_cfg.dt_s is None and time_cfg.get("dt_s") is not None:
        run_cfg.dt_s = float(time_cfg.get("dt_s"))
    if run_cfg.t_end_s is None and time_cfg.get("t_end_s") is not None:
        run_cfg.t_end_s = float(time_cfg.get("t_end_s"))
    if run_cfg.t_padding_s is None and time_cfg.get("t_padding_s") is not None:
        run_cfg.t_padding_s = float(time_cfg.get("t_padding_s"))

    schedule_cfg = dict(primary_step.get("schedule", {}) or {})
    if run_cfg.schedule_policy is None and schedule_cfg.get("policy") is not None:
        run_cfg.schedule_policy = str(schedule_cfg.get("policy")).strip().lower()

    frame_override = dict(primary_step.get("frame", {}) or {})
    if frame_override.get("mode") is not None:
        frame_cfg.mode = str(frame_override.get("mode")).strip().lower()
    if "reference" in frame_override:
        frame_cfg.reference = _normalize_frame_reference_name(frame_override.get("reference"))
    else:
        frame_cfg.reference = _normalize_frame_reference_name(frame_cfg.reference)
    if "rwa" in frame_override:
        frame_cfg.rwa = bool(frame_override.get("rwa"))
    if frame_override.get("qubit_reference_freqs_Hz") is not None:
        frame_cfg.qubit_reference_freqs_Hz = list(frame_override.get("qubit_reference_freqs_Hz") or []) or None
    return run_cfg, frame_cfg, dict(primary_step)


def _normalize_composite_device_payload(raw: dict[str, object]) -> dict[str, object]:
    components = list(raw.get("components", []) or [])
    connections = list(raw.get("connections", []) or [])

    qubits: list[dict[str, object]] = []
    qubit_index: dict[str, int] = {}
    max_transmon_levels = 2
    cavity_freq_hz = 0.0
    cavity_nmax = 0

    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("representation", "quantum")).strip().lower() == "disabled":
            continue
        comp_type = str(comp.get("type", "")).strip().lower()
        basis = dict(comp.get("basis", {}) or {})
        parameters = dict(comp.get("parameters", {}) or {})
        raw_noise = comp.get("noise", {}) or {}
        local_noise = dict(raw_noise) if isinstance(raw_noise, dict) else {}
        if comp_type == "transmon":
            q_payload = {
                "freq_Hz": float(parameters.get("freq_Hz", 0.0)),
                "anharmonicity_Hz": float(parameters.get("anharmonicity_Hz", -2.0e8)),
            }
            for key in ("T1_s", "T2_s", "Tphi_s", "Tup_s", "gamma1_Hz", "gamma_phi_Hz", "gamma_up_Hz"):
                if key in local_noise:
                    q_payload[key] = local_noise[key]
            qubit_index[str(comp.get("id", f"q{len(qubits)}"))] = len(qubits)
            qubits.append(q_payload)
            if str(basis.get("kind", "")).strip().lower() == "nlevel":
                max_transmon_levels = max(max_transmon_levels, int(basis.get("levels", 2) or 2))
        elif comp_type == "resonator" and str(comp.get("representation", "quantum")).strip().lower() == "quantum":
            if cavity_freq_hz == 0.0:
                cavity_freq_hz = float(parameters.get("freq_Hz", 0.0))
                cavity_nmax = int(basis.get("nmax", 0) or 0)

    normalized: dict[str, object] = {
        **{k: v for k, v in raw.items() if k not in {"components", "connections"}},
        "components": components,
        "connections": connections,
    }
    if qubits:
        normalized["qubits"] = qubits
    if max_transmon_levels > 2:
        normalized["transmon_levels"] = max_transmon_levels
    if cavity_nmax > 0:
        normalized["cavity_freq_Hz"] = cavity_freq_hz
        normalized["cavity_nmax"] = cavity_nmax

    g_cavity_hz = [0.0 for _ in range(len(qubits))]
    couplings: list[dict[str, object]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        conn_type = str(conn.get("type", "")).strip().lower()
        params = dict(conn.get("parameters", {}) or {})
        a = str(conn.get("a", ""))
        b = str(conn.get("b", ""))
        if conn_type in {"jc", "dispersive"}:
            qid = a if a in qubit_index else b if b in qubit_index else ""
            if qid:
                q = qubit_index[qid]
                if "g_Hz" in params:
                    g_cavity_hz[q] = float(params.get("g_Hz", 0.0))
        elif conn_type in {"exchange", "zz", "mediated_exchange"}:
            i = qubit_index.get(a)
            j = qubit_index.get(b)
            if i is None or j is None or i == j:
                continue
            kind = "zz" if conn_type == "zz" else "xx+yy"
            couplings.append(
                {
                    "i": int(i),
                    "j": int(j),
                    "g_Hz": float(params.get("g_Hz", 0.0)),
                    "kind": kind,
                }
            )
    if any(abs(x) > 0.0 for x in g_cavity_hz):
        normalized["g_cavity_Hz"] = g_cavity_hz
    if couplings:
        normalized["couplings"] = couplings
    return normalized


def normalize_device_payload(device: dict | None) -> dict[str, object]:
    """Normalize legacy and component-based device payloads for model building."""
    raw = dict(device or {})
    if "components" in raw:
        return _normalize_composite_device_payload(raw)
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
    analyser_cfg: DefaultAnalyserConfig | None,
    *,
    backend_source: str | None = None,
) -> WorkflowTask:
    """Compose task/solver/device/analyser configs into one runtime task contract."""
    run_cfg, frame_cfg, _primary_step = merge_solver_runtime_from_study(solver_cfg)
    runtime_source_device = apply_composite_device_step_overrides(device_cfg.device, _primary_step)
    runtime_level = infer_runtime_level(runtime_source_device)
    runtime_device = normalize_device_payload(runtime_source_device)
    if "simulation_level" not in runtime_device:
        runtime_device["simulation_level"] = runtime_level

    return WorkflowTask(
        input=WorkflowInput(
            qasm_text=task_cfg.input.qasm_text,
            backend_path=backend_source,
            backend_config=solver_cfg.to_backend_config(noise=device_cfg.noise, runtime_level=runtime_level),
            device=runtime_device or None,
            device_model=dict(runtime_source_device or {}) or None,
            pulse=dict(device_cfg.pulse or {}) or None,
            frame=asdict(frame_cfg),
            analyser=analyser_cfg.to_payload() if analyser_cfg is not None else None,
            study=list(solver_cfg.study or []) or None,
            schedule_policy=(
                str(run_cfg.schedule_policy).strip().lower() if run_cfg.schedule_policy else None
            ),
            reset_feedback_policy=(
                str(run_cfg.reset_feedback_policy).strip().lower()
                if run_cfg.reset_feedback_policy
                else None
            ),
            noise=dict(device_cfg.noise or {}),
            param_bindings=dict(task_cfg.input.param_bindings or {}) or None,
        ),
        run=run_cfg,
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
    "DefaultAnalyserConfig",
    "WorkflowInput",
    "WorkflowOutputOptions",
    "WorkflowRunOptions",
    "WorkflowSolverConfig",
    "WorkflowTask",
    "WorkflowTaskConfig",
    "apply_composite_device_step_overrides",
    "compose_workflow_task",
    "extract_study_prep",
    "filter_composite_device_for_step",
    "infer_runtime_level",
    "merge_solver_runtime_from_study",
    "select_primary_study_step",
    "normalize_targets",
]
