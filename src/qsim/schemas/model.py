"""Top-level engine-neutral simulation model schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qsim.common.channels import canonical_readout_protocol
from qsim.schemas.circuit import CircuitSpec
from qsim.schemas.hamiltonian import HamiltonianSpec, control_dict_to_hamiltonian_term
from qsim.schemas.noise import NoiseSpec
from qsim.schemas.readout import ReadoutSpec
from qsim.schemas.solver import FrameSpec, SolverSpec, TimeSpec
from qsim.schemas.study import AnalysisRequestSpec, StudySpec
from qsim.schemas.system import (
    ModelStructureSpec,
    SystemCavitySpec,
    SystemCouplingSummarySpec,
    SystemQubitSpec,
    SystemSpec,
)

# --- Run-Scoped Containers ---

from enum import Enum, auto

class RunStatus(Enum):
    """Execution status of a model run.

    Attributes:
        PENDING: Run is queued and waiting for execution.
        RUNNING: Run is currently being processed by an engine.
        COMPLETED: Run finished successfully.
        FAILED: Run terminated with an error.
    """
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass(slots=True)
class RunIdentity:
    """Unique identifier for a specific execution run.

    Attributes:
        run_id: Unique UUID or string identifying this specific run.
        solver_id: Identifier of the solver configuration used.
        study_name: Name of the study if this run is part of a study.
        study_index: Index of the step within the study.
    """
    run_id: str
    solver_id: str
    study_name: str | None = None
    study_index: int | None = None

@dataclass(slots=True)
class RunArtifacts:
    """Compiled and intermediate artifacts for a run.

    This container holds all non-factual outputs produced during the 
    compilation and lowering phase, before the numerical engine is invoked.

    Attributes:
        circuit: The original parsed circuit specification.
        normalized_circuit: The circuit after normalization and optimization.
        model_spec: The engine-neutral domain model (authoritative truth).
        pulse_ir: Intermediate representation of pulses for the hardware.
        executable_model: The lowered model ready for engine consumption.
        compile_report: Metadata and logs from the compilation process.
        decoder_outputs: Results from QEC decoding if applicable.
        timings: Calculated time offsets and durations.
    """
    circuit: CircuitSpec | None = None
    normalized_circuit: CircuitSpec | None = None
    model_spec: ModelSpec | None = None
    pulse_ir: "PulseIR | None" = None
    executable_model: "ExecutableModel | None" = None
    compile_report: dict[str, Any] = field(default_factory=dict)
    decoder_outputs: "DecoderOutputs | None" = None
    timings: dict[str, float] = field(default_factory=dict)

@dataclass(slots=True)
class ModelRun:
    """Authoritative home for one execution of one solver/study combination.

    A `ModelRun` encapsulates everything unique to a single execution, including
    its identity, the task contract, the intermediate artifacts, and the final result.

    Attributes:
        identity: The unique identity of this run.
        runtime_task: The runtime contract (input) for this execution.
        artifacts: Compiled and intermediate products (IR).
        result: The factual numerical output (e.g., Trajectory).
        status: Current execution status.
        started_at: Epoch timestamp of start.
        finished_at: Epoch timestamp of completion.
        error: Error message if the run failed.
    """
    identity: RunIdentity
    runtime_task: "WorkflowTask"
    artifacts: RunArtifacts = field(default_factory=RunArtifacts)
    result: "RunResult | None" = None
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None

@dataclass(slots=True)
class ModelManifest:
    """Version and layout metadata for the persisted model.

    Used to ensure compatibility and provenance when loading models from disk.

    Attributes:
        schema_version: Version of the model schema.
        created_at: ISO timestamp of model creation.
        config_layout: Map of configuration keys to their versions/sources.
        state_snapshot: Snapshot of session state at the time of manifest creation.
        provenance: Traceability data regarding the model's origin.
    """
    schema_version: str = "3.0"
    created_at: str = ""
    config_layout: dict[str, str] = field(default_factory=dict)
    state_snapshot: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

# --- Domain Model ---

@dataclass
class ModelSpec:
    """Engine-neutral simulation model specification.

    ``ModelSpec`` is the structured boundary between backend lowering and
    numerical engines. It describes the circuit context, solver request, time
    grid, frame, physical system, Hamiltonian, noise, readout, and analysis
    request without depending on a backend-private runtime representation.

    Attributes:
        circuit: The circuit specification associated with the simulation.
        solver: Solver specification (e.g., SE, ME, SME).
        time: Time grid specification (dt, t_end).
        frame: Reference frame and RWA settings.
        system: Physical system description (qubits, resonators).
        hamiltonian: System Hamiltonian including controls and couplings.
        noise: Noise model and dissipation channels.
        readout: Readout protocol and chain specification.
        analysis_request: Requested post-processing analysis.
        study: Study context if this is part of a parameter sweep.
        metadata: Non-primary technical annotations and debug notes.
    """

    circuit: "CircuitSpec | None" = None
    solver: "SolverSpec | str" = "se"
    time: "TimeSpec" = field(default_factory=lambda: TimeSpec())
    frame: "FrameSpec" = field(default_factory=lambda: FrameSpec())
    system: "SystemSpec" = field(default_factory=lambda: SystemSpec())
    hamiltonian: "HamiltonianSpec" = field(default_factory=lambda: HamiltonianSpec())
    noise: "NoiseSpec" = field(default_factory=lambda: NoiseSpec())
    readout: "ReadoutSpec | None" = None
    analysis_request: "AnalysisRequestSpec | None" = None
    study: "StudySpec | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize string solver shorthands into ``SolverSpec`` objects."""
        if isinstance(self.solver, str):
            self.solver = SolverSpec(mode=str(self.solver))

    @property
    def dimension(self) -> int:
        """Hilbert-space dimension requested by the system model."""
        return int(self.system.dimension)

    @property
    def dt(self) -> float:
        """Simulation timestep in seconds."""
        return float(self.time.dt_s)

    @property
    def t_end(self) -> float:
        """Simulation end time in seconds."""
        return float(self.time.t_end_s)

    @property
    def solver_mode(self) -> str:
        """Normalized solver mode token such as ``se``, ``me``, or ``sme``."""
        return str(self.solver.mode if isinstance(self.solver, SolverSpec) else self.solver).strip().lower()


def model_spec_from_runtime_dict(
    *,
    solver: str = "se",
    dimension: int = 2,
    t_end: float = 0.0,
    dt: float = 1.0,
    engine: str = "qutip",
    model: dict[str, Any] | None = None,
) -> ModelSpec:
    """Build a structured ``ModelSpec`` from a legacy runtime dictionary.

    This function facilitates backward compatibility with models persisted 
    using the legacy dict-based format.

    .. deprecated:: 2.0
       Use direct ModelSpec construction or the formal WorkflowTask pipeline.

    Args:
        solver (str): Solver mode token (e.g., "se", "me", "sme"). Defaults to "se".
        dimension (int): Hilbert-space dimension for the system. Defaults to 2.
        t_end (float): Total simulation time in seconds. Defaults to 0.0.
        dt (float): Simulation time step in seconds. Defaults to 1.0.
        engine (str): The numerical engine to use (e.g., "qutip", "julia"). Defaults to "qutip".
        model (dict[str, Any], optional): Legacy dictionary containing model data. Defaults to None.

    Returns:
        ModelSpec: A structured and typed model specification.
    """
    data = dict(model or {})

    noise_summary = dict(data.get("noise_summary", {}) or {})
    frame_data = dict(data.get("frame", {}) or {})
    primary_step = dict(data.get("primary_step", {}) or {})
    options = dict(primary_step.get("options", {}) or {})
    circuit_data = data.get("circuit")
    return ModelSpec(
        circuit=CircuitSpec.from_dict(circuit_data) if isinstance(circuit_data, dict) else None,
        solver=SolverSpec(mode=str(solver), engine=engine),
        time=TimeSpec(dt_s=float(dt), t_end_s=float(t_end)),
        frame=FrameSpec(
            mode=str(frame_data.get("mode", "rotating")),
            reference=str(frame_data.get("reference", "pulse_carrier")),
            rwa=bool(frame_data.get("rwa", True)),
            qubit_reference_freqs_Hz=[float(x) for x in data.get("reference_freqs_Hz", frame_data.get("qubit_reference_freqs_Hz", []))],
            qubit_reference_omega_rad_s=[float(x) for x in data.get("reference_omega_rad_s", frame_data.get("qubit_reference_omega_rad_s", []))],
            pulse_carrier_reference_freqs_Hz=[float(x) for x in data.get("pulse_carrier_reference_freqs_Hz", [])],
            pulse_carrier_reference_omega_rad_s=[float(x) for x in data.get("pulse_carrier_reference_omega_rad_s", [])],
        ),
        system=SystemSpec(
            model_type=str(data.get("model_type", "qubit_network")),
            simulation_level=str(data.get("simulation_level", "qubit")),
            dimension=int(dimension),
            components=list(data.get("components", []) or []),
            connections=list(data.get("connections", []) or []),
            structure=ModelStructureSpec.from_dict(dict(data.get("model_structure", {}) or {})),
            qubits=SystemQubitSpec(
                num_qubits=int(data.get("num_qubits", 1) or 0),
                transmon_levels=int(data.get("transmon_levels", 2) or 2),
                qubit_freqs_Hz=[float(x) for x in data.get("qubit_freqs_Hz", [])],
                qubit_omega_rad_s=[float(x) for x in data.get("qubit_omega_rad_s", [])],
                lab_frame_qubit_freqs_Hz=[float(x) for x in data.get("lab_frame_qubit_freqs_Hz", [])],
                lab_frame_qubit_omega_rad_s=[float(x) for x in data.get("lab_frame_qubit_omega_rad_s", [])],
                anharmonicity_Hz=[float(x) for x in data.get("anharmonicity_Hz", [])],
                anharmonicity_rad_s=[float(x) for x in data.get("anharmonicity_rad_s", [])],
            ),
            cavity=SystemCavitySpec(
                cavity_nmax=int(data.get("cavity_nmax", 0) or 0),
                cavity_freq_Hz=float(data.get("cavity_freq_Hz", 0.0) or 0.0),
                cavity_omega_rad_s=float(data.get("cavity_omega_rad_s", 0.0) or 0.0),
            ),
            couplings=SystemCouplingSummarySpec(
                g_cavity_Hz=[float(x) for x in data.get("g_cavity_Hz", [])],
                g_cavity_rad_s=[float(x) for x in data.get("g_cavity_rad_s", [])],
            ),
            assumptions=dict(data.get("model_assumptions", {}) or {}),
        ),
        hamiltonian=HamiltonianSpec(
            coupling_terms=list(data.get("couplings", []) or []),
            control_terms=[
                control_dict_to_hamiltonian_term(ctrl, kind="control")
                for ctrl in list(data.get("controls", []) or [])
            ],
            readout_drive_terms=[
                control_dict_to_hamiltonian_term(ctrl, kind="readout_drive")
                for ctrl in list(data.get("readout_controls", []) or [])
            ],
        ),
        noise=NoiseSpec(
            selected_model=str(noise_summary.get("selected_model", "markovian_lindblad")),
            readout_error=float((data.get("noise_cfg", {}) or {}).get("readout_error", 0.0) or 0.0),
            sources=list(noise_summary.get("sources", []) or []),
            realizations=list(noise_summary.get("realizations", []) or []),
            control_crosstalk=list(noise_summary.get("control_crosstalk", []) or []),
            readout_crosstalk=list(noise_summary.get("readout_crosstalk", []) or []),
            collapse_channels=list(data.get("collapse_operators", []) or []),
            stochastic_channels=list(noise_summary.get("stochastic", []) or []),
            per_qubit_rates=list(noise_summary.get("per_qubit_rates", []) or []),
            supported=list(noise_summary.get("supported", []) or []),
            unsupported=list(noise_summary.get("unsupported", []) or []),
            warnings=list(noise_summary.get("warnings", []) or []),
        ),
        readout=ReadoutSpec(
            protocol=canonical_readout_protocol(data),
            update_mode=str(
                options.get(
                    "hybrid_readout_update",
                    options.get("classical_readout_update", options.get("hybrid_update_mode", "predictor_corrector")),
                )
                or "predictor_corrector"
            ),
            subsystem_model=str(options.get("subsystem_model", "") or ""),
            chain=dict(data.get("readout_chain", {}) or {}),
            controls=list(data.get("readout_controls", []) or []),
            lines=list(data.get("readout_lines", []) or []),
            reset_events=list(data.get("reset_events", []) or []),
        ),
        analysis_request=AnalysisRequestSpec(
            trajectory=dict((data.get("analyser", {}) or {}).get("trajectory", {}) or {}),
            config=dict(data.get("analyser", {}) or {}),
        ),
        study=StudySpec(
            steps=list(data.get("study", []) or []),
            primary_step=primary_step,
            summary=dict(data.get("study_summary", {}) or {}),
        ),
        metadata={
            "noise_terms": list(data.get("noise_terms", []) or []),
            "legacy_raw_h_terms": list(data.get("h_terms", []) or []),
        },
    )