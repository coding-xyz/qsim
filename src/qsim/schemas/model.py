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


@dataclass
class ModelSpec:
    """Engine-neutral simulation model specification.

    ``ModelSpec`` is the structured boundary between backend lowering and
    numerical engines. It describes the circuit context, solver request, time
    grid, frame, physical system, Hamiltonian, noise, readout, and analysis
    request without depending on a backend-private runtime representation.
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

    Args:
        solver: Solver mode token to place in ``SolverSpec.mode``.
        dimension: Hilbert-space dimension for ``SystemSpec``.
        t_end: Simulation end time in seconds.
        dt: Simulation timestep in seconds.
        engine: Optional runtime engine hint stored in ``SolverSpec.engine``.
        model: Plain dictionary produced by older model-building paths.

    Returns:
        A structured ``ModelSpec`` with typed system, Hamiltonian, noise, and
        readout sections.
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



