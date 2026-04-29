"""Dataclasses and JSON helpers for qsim workflow schemas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from qsim.common.channels import canonical_readout_protocol

SCHEMA_VERSION = "1.0"
COMPLEX_JSON_TAG = "__qsim_complex__"


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 digest for a file."""
    p = Path(path)
    hasher = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def to_json_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass object to JSON-serializable dictionary."""
    return asdict(obj)


def json_safe(value: Any) -> Any:
    """Convert nested values into a JSON-safe representation."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, complex):
        return {COMPLEX_JSON_TAG: [float(value.real), float(value.imag)]}
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def json_restore(value: Any) -> Any:
    """Restore nested values previously converted by ``json_safe``."""
    if isinstance(value, dict):
        if set(value.keys()) == {COMPLEX_JSON_TAG}:
            pair = list(value.get(COMPLEX_JSON_TAG, []) or [])
            if len(pair) >= 2:
                return complex(float(pair[0]), float(pair[1]))
        return {str(k): json_restore(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_restore(item) for item in value]
    return value


def make_series_payload(
    values: list[list[float]] | list[float],
    *,
    quantity: str,
    description: str,
    series_labels: list[str] | None = None,
    unit: str = "",
) -> dict[str, Any]:
    """Build a named time-series payload for classical trajectory channels."""
    if values and isinstance(values[0], (int, float)):
        rows = [[float(v)] for v in list(values)]  # type: ignore[index]
    else:
        rows = [[float(v) for v in row] for row in list(values)]  # type: ignore[arg-type]
    if series_labels is None and rows:
        series_labels = [f"s{i}" for i in range(len(rows[0]))]
    return {
        "quantity": str(quantity),
        "description": str(description),
        "unit": str(unit or ""),
        "series_labels": list(series_labels or []),
        "values": rows,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write UTF-8 pretty JSON file and return output path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


@dataclass
class CircuitGate:
    """One logical gate operation in circuit IR."""

    name: str
    qubits: list[int] = field(default_factory=list)
    params: list[float] = field(default_factory=list)
    clbits: list[int] = field(default_factory=list)


@dataclass
class CircuitIR:
    """Normalized circuit representation used by compile pipeline."""

    schema_version: str = SCHEMA_VERSION
    format: str = "openqasm3"
    num_qubits: int = 0
    num_clbits: int = 0
    gates: list[CircuitGate] = field(default_factory=list)
    source_qasm: str = ""


@dataclass
class CircuitSpec:
    """Circuit snapshot kept with ``ModelSpec`` for engines that need gate context."""

    schema_version: str = SCHEMA_VERSION
    format: str = "openqasm3"
    num_qubits: int = 0
    num_clbits: int = 0
    gates: list[CircuitGate] = field(default_factory=list)
    source_qasm: str = ""
    stage: str = "normalized"

    @classmethod
    def from_circuit_ir(cls, circuit: CircuitIR, *, stage: str = "normalized") -> "CircuitSpec":
        return cls(
            schema_version=str(circuit.schema_version),
            format=str(circuit.format),
            num_qubits=int(circuit.num_qubits),
            num_clbits=int(circuit.num_clbits),
            gates=[
                gate if isinstance(gate, CircuitGate) else CircuitGate(**dict(gate))
                for gate in list(circuit.gates or [])
            ],
            source_qasm=str(circuit.source_qasm or ""),
            stage=str(stage),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CircuitSpec":
        raw = dict(data or {})
        return cls(
            schema_version=str(raw.get("schema_version", SCHEMA_VERSION)),
            format=str(raw.get("format", "openqasm3")),
            num_qubits=int(raw.get("num_qubits", 0) or 0),
            num_clbits=int(raw.get("num_clbits", 0) or 0),
            gates=[
                gate if isinstance(gate, CircuitGate) else CircuitGate(**dict(gate))
                for gate in list(raw.get("gates", []) or [])
            ],
            source_qasm=str(raw.get("source_qasm", "") or ""),
            stage=str(raw.get("stage", "normalized") or "normalized"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "num_qubits": self.num_qubits,
            "num_clbits": self.num_clbits,
            "gates": [asdict(gate) for gate in self.gates],
            "source_qasm": self.source_qasm,
            "stage": self.stage,
        }


@dataclass
class BackendConfig:
    """Backend execution configuration loaded from YAML."""

    schema_version: str = SCHEMA_VERSION
    level: str = "qubit"
    noise: str = "deterministic"
    solver: str = "se"
    analysis_pipeline: str = "default"
    truncation: dict[str, int] = field(default_factory=dict)
    sweep: list[dict[str, Any]] = field(default_factory=list)
    seed: int = 1234

    @property
    def analysis(self) -> str:
        return str(self.analysis_pipeline)

    @analysis.setter
    def analysis(self, value: str) -> None:
        self.analysis_pipeline = str(value)


@dataclass
class Carrier:
    """Carrier tone parameters for pulse modulation."""

    freq: float
    phase: float = 0.0


@dataclass
class PulseSpec:
    """Single pulse segment scheduled on a channel."""

    t0_s: float
    t1_s: float
    amp: float
    shape: str
    params: dict[str, Any] = field(default_factory=dict)
    carrier: Carrier | None = None

    @property
    def duration_s(self) -> float:
        return float(self.t1_s) - float(self.t0_s)

    @property
    def t0_ns(self) -> float:
        return round(float(self.t0_s) * 1e9, 12)

    @property
    def t1_ns(self) -> float:
        return round(float(self.t1_s) * 1e9, 12)

    @property
    def duration_ns(self) -> float:
        return round(self.duration_s * 1e9, 12)


@dataclass
class ChannelSpec:
    """Collection of pulses for one hardware channel."""

    name: str
    pulses: list[PulseSpec] = field(default_factory=list)


@dataclass
class PulseIR:
    """Pulse-level intermediate representation for one schedule."""

    schema_version: str = SCHEMA_VERSION
    t_end_s: float = 0.0
    channels: list[ChannelSpec] = field(default_factory=list)

    @property
    def t_end_ns(self) -> float:
        return round(float(self.t_end_s) * 1e9, 12)


@dataclass
class ExecutableModel:
    """Lowered executable model before numeric model construction."""

    schema_version: str = SCHEMA_VERSION
    level: str = "qubit"
    solver: str = "se"
    h_terms: list[dict[str, Any]] = field(default_factory=list)
    noise_terms: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSpec:
    """Engine-neutral simulation model specification."""

    engine: str = "mock"
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
        if isinstance(self.solver, str):
            self.solver = SolverSpec(mode=str(self.solver))

    @property
    def dimension(self) -> int:
        return int(self.system.dimension)

    @property
    def dt(self) -> float:
        return float(self.time.dt_s)

    @property
    def t_end(self) -> float:
        return float(self.time.t_end_s)

    @property
    def solver_mode(self) -> str:
        return str(self.solver.mode if isinstance(self.solver, SolverSpec) else self.solver).strip().lower()


@dataclass
class SolverSpec:
    """Solver selection and numerical run controls."""

    mode: str = "se"
    engine: str | None = None
    seed: int | None = None
    ntraj: int | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return str(self.mode)


@dataclass
class TimeSpec:
    """Simulation time-grid request."""

    dt_s: float = 1.0
    t_end_s: float = 0.0
    t_padding_s: float = 0.0


@dataclass
class FrameSpec:
    """Reference-frame and RWA configuration."""

    mode: str = "rotating"
    reference: str = "pulse_carrier"
    rwa: bool = True
    qubit_reference_freqs_Hz: list[float] = field(default_factory=list)
    qubit_reference_omega_rad_s: list[float] = field(default_factory=list)
    pulse_carrier_reference_freqs_Hz: list[float] = field(default_factory=list)
    pulse_carrier_reference_omega_rad_s: list[float] = field(default_factory=list)


@dataclass
class SystemComponentSpec:
    """Normalized component entry in an engine-neutral system graph."""

    id: str = ""
    type: str = ""
    representation: str = "quantum"
    basis: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    noise: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemComponentSpec":
        raw = dict(data or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            type=str(raw.get("type", "") or ""),
            representation=str(raw.get("representation", "quantum") or "quantum"),
            basis=dict(raw.get("basis", {}) or {}),
            parameters=dict(raw.get("parameters", {}) or {}),
            noise=dict(raw.get("noise", {}) or {}),
            description=str(raw.get("description", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "type": self.type,
            "representation": self.representation,
            "parameters": dict(self.parameters),
        }
        if self.basis:
            data["basis"] = dict(self.basis)
        if self.noise:
            data["noise"] = dict(self.noise)
        if self.description:
            data["description"] = self.description
        return data


@dataclass
class SystemConnectionSpec:
    """Normalized connection entry in an engine-neutral system graph."""

    id: str = ""
    type: str = ""
    a: str = ""
    b: str = ""
    via: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemConnectionSpec":
        raw = dict(data or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            type=str(raw.get("type", "") or ""),
            a=str(raw.get("a", "") or ""),
            b=str(raw.get("b", "") or ""),
            via=str(raw.get("via", "") or ""),
            parameters=dict(raw.get("parameters", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {"id": self.id, "type": self.type, "a": self.a, "b": self.b, "parameters": dict(self.parameters)}
        if self.via:
            data["via"] = self.via
        return data


@dataclass
class ComponentSummarySpec:
    """Compact component inventory."""

    count: int = 0
    ids: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    representations: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ComponentSummarySpec":
        raw = dict(data or {})
        return cls(
            count=int(raw.get("count", 0) or 0),
            ids=[str(x) for x in list(raw.get("ids", []) or [])],
            types=[str(x) for x in list(raw.get("types", []) or [])],
            representations=[str(x) for x in list(raw.get("representations", []) or [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "ids": list(self.ids),
            "types": list(self.types),
            "representations": list(self.representations),
        }


@dataclass
class ModelStructureSpec:
    """Resolved subsystem structure after study selection."""

    qubit_representation: str = "quantum"
    cavity_representation: str = ""
    feedline_representation: str = ""
    qubit_cavity_coupling: str = ""
    cavity_feedline_coupling: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ModelStructureSpec":
        raw = dict(data or {})
        return cls(
            qubit_representation=str(raw.get("qubit_representation", "quantum") or "quantum"),
            cavity_representation=str(raw.get("cavity_representation", "") or ""),
            feedline_representation=str(raw.get("feedline_representation", "") or ""),
            qubit_cavity_coupling=str(raw.get("qubit_cavity_coupling", "") or ""),
            cavity_feedline_coupling=str(raw.get("cavity_feedline_coupling", "") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "qubit_representation": self.qubit_representation,
            "cavity_representation": self.cavity_representation,
            "feedline_representation": self.feedline_representation,
            "qubit_cavity_coupling": self.qubit_cavity_coupling,
            "cavity_feedline_coupling": self.cavity_feedline_coupling,
        }


@dataclass
class SystemSpec:
    """Engine-neutral physical system description."""

    model_type: str = "qubit_network"
    simulation_level: str = "qubit"
    num_qubits: int = 1
    dimension: int = 2
    transmon_levels: int = 2
    cavity_nmax: int = 0
    qubit_freqs_Hz: list[float] = field(default_factory=list)
    qubit_omega_rad_s: list[float] = field(default_factory=list)
    lab_frame_qubit_freqs_Hz: list[float] = field(default_factory=list)
    lab_frame_qubit_omega_rad_s: list[float] = field(default_factory=list)
    anharmonicity_Hz: list[float] = field(default_factory=list)
    anharmonicity_rad_s: list[float] = field(default_factory=list)
    cavity_freq_Hz: float = 0.0
    cavity_omega_rad_s: float = 0.0
    g_cavity_Hz: list[float] = field(default_factory=list)
    g_cavity_rad_s: list[float] = field(default_factory=list)
    components: list[SystemComponentSpec] = field(default_factory=list)
    connections: list[SystemConnectionSpec] = field(default_factory=list)
    component_summary: ComponentSummarySpec = field(default_factory=ComponentSummarySpec)
    structure: ModelStructureSpec = field(default_factory=ModelStructureSpec)
    assumptions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.components = [
            comp if isinstance(comp, SystemComponentSpec) else SystemComponentSpec.from_dict(comp)
            for comp in list(self.components or [])
        ]
        self.connections = [
            conn if isinstance(conn, SystemConnectionSpec) else SystemConnectionSpec.from_dict(conn)
            for conn in list(self.connections or [])
        ]
        if not isinstance(self.component_summary, ComponentSummarySpec):
            self.component_summary = ComponentSummarySpec.from_dict(self.component_summary)
        if not isinstance(self.structure, ModelStructureSpec):
            self.structure = ModelStructureSpec.from_dict(self.structure)


@dataclass
class OperatorRef:
    """Symbolic operator reference before backend-specific lowering."""

    name: str
    target: int | None = None
    target_pair: list[int] | None = None
    scope: str = "system"


@dataclass
class CarrierSpec:
    """Carrier metadata attached to a sampled signal."""

    freq_Hz: float = 0.0
    omega_rad_s: float = 0.0
    phase_rad: float = 0.0


@dataclass
class SignalSpec:
    """Sampled or analytic coefficient signal for time-dependent terms."""

    kind: str = "sampled"
    unit: str = ""
    times_s: list[float] = field(default_factory=list)
    values: list[Any] = field(default_factory=list)
    interpolation: str = "linear"
    scale: float = 1.0
    carrier: CarrierSpec | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HamiltonianTerm:
    """Static Hamiltonian term."""

    operator: OperatorRef
    coefficient: float = 1.0
    unit: str = "rad_per_s"
    kind: str = "static"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeDependentHamiltonianTerm:
    """Time-dependent Hamiltonian term driven by a signal."""

    operator: OperatorRef
    coefficient: SignalSpec
    kind: str = "control"
    metadata: dict[str, Any] = field(default_factory=dict)


_CONTROL_TERM_CORE_KEYS = {
    "axis",
    "target",
    "target_pair",
    "times",
    "values",
    "scale",
    "carrier_freq_Hz",
    "carrier_omega_rad_s",
    "carrier_phase_rad",
    "channel",
}


def control_dict_to_hamiltonian_term(ctrl: dict[str, Any], *, kind: str) -> TimeDependentHamiltonianTerm:
    """Convert a sampled control/readout-drive dictionary into a Hamiltonian term."""
    target = int(ctrl.get("target", -1)) if "target" in ctrl else None
    target_pair = list(ctrl.get("target_pair", []) or []) or None
    op_name = str(ctrl.get("axis", "readout") if kind == "control" else "readout")
    carrier = CarrierSpec(
        freq_Hz=float(ctrl.get("carrier_freq_Hz", 0.0) or 0.0),
        omega_rad_s=float(ctrl.get("carrier_omega_rad_s", 0.0) or 0.0),
        phase_rad=float(ctrl.get("carrier_phase_rad", 0.0) or 0.0),
    )
    return TimeDependentHamiltonianTerm(
        operator=OperatorRef(
            name=op_name,
            target=target if target is not None and target >= 0 else None,
            target_pair=[int(x) for x in target_pair] if target_pair else None,
        ),
        coefficient=SignalSpec(
            kind="sampled",
            unit="rad_per_s",
            times_s=[float(x) for x in ctrl.get("times", [])],
            values=[float(x) for x in ctrl.get("values", [])],
            interpolation="linear",
            scale=float(ctrl.get("scale", 1.0)),
            carrier=carrier,
            metadata={"channel": str(ctrl.get("channel", ""))},
        ),
        kind=kind,
        metadata={key: value for key, value in dict(ctrl).items() if key not in _CONTROL_TERM_CORE_KEYS},
    )


@dataclass
class HamiltonianSpec:
    """Engine-neutral Hamiltonian terms."""

    static_terms: list[HamiltonianTerm] = field(default_factory=list)
    coupling_terms: list[dict[str, Any]] = field(default_factory=list)
    control_terms: list[TimeDependentHamiltonianTerm] = field(default_factory=list)
    readout_drive_terms: list[TimeDependentHamiltonianTerm] = field(default_factory=list)
    raw_terms: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CollapseChannelSpec:
    """Markovian collapse channel."""

    target: int = 0
    kind: str = ""
    rate_Hz: float = 0.0
    rate_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CollapseChannelSpec":
        raw = dict(data or {})
        return cls(
            target=int(raw.get("target", 0) or 0),
            kind=str(raw.get("kind", "") or ""),
            rate_Hz=float(raw.get("rate_Hz", 0.0) or 0.0),
            rate_rad_s=float(raw.get("rate_rad_s", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "kind": self.kind,
            "rate_Hz": self.rate_Hz,
            "rate_rad_s": self.rate_rad_s,
        }


@dataclass
class StochasticChannelSpec:
    """Classical stochastic-noise channel parameters for one qubit."""

    q: int = 0
    one_over_f_amp_Hz: float = 0.0
    one_over_f_amp_rad_s: float = 0.0
    one_over_f_fmin: float = 0.0
    one_over_f_fmax: float = 0.0
    one_over_f_exponent: float = 1.0
    ou_sigma_Hz: float = 0.0
    ou_sigma_rad_s: float = 0.0
    ou_tau: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StochasticChannelSpec":
        raw = dict(data or {})
        return cls(
            q=int(raw.get("q", 0) or 0),
            one_over_f_amp_Hz=float(raw.get("one_over_f_amp_Hz", 0.0) or 0.0),
            one_over_f_amp_rad_s=float(raw.get("one_over_f_amp_rad_s", 0.0) or 0.0),
            one_over_f_fmin=float(raw.get("one_over_f_fmin", 0.0) or 0.0),
            one_over_f_fmax=float(raw.get("one_over_f_fmax", 0.0) or 0.0),
            one_over_f_exponent=float(raw.get("one_over_f_exponent", 1.0) or 1.0),
            ou_sigma_Hz=float(raw.get("ou_sigma_Hz", 0.0) or 0.0),
            ou_sigma_rad_s=float(raw.get("ou_sigma_rad_s", 0.0) or 0.0),
            ou_tau=float(raw.get("ou_tau", 1.0) or 1.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerQubitRateSpec:
    """Resolved per-qubit Markovian rates."""

    q: int = 0
    gamma1_Hz: float = 0.0
    gamma_phi_Hz: float = 0.0
    gamma_up_Hz: float = 0.0
    gamma1_rad_s: float = 0.0
    gamma_phi_rad_s: float = 0.0
    gamma_up_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PerQubitRateSpec":
        raw = dict(data or {})
        return cls(
            q=int(raw.get("q", 0) or 0),
            gamma1_Hz=float(raw.get("gamma1_Hz", 0.0) or 0.0),
            gamma_phi_Hz=float(raw.get("gamma_phi_Hz", 0.0) or 0.0),
            gamma_up_Hz=float(raw.get("gamma_up_Hz", 0.0) or 0.0),
            gamma1_rad_s=float(raw.get("gamma1_rad_s", 0.0) or 0.0),
            gamma_phi_rad_s=float(raw.get("gamma_phi_rad_s", 0.0) or 0.0),
            gamma_up_rad_s=float(raw.get("gamma_up_rad_s", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NoiseSpec:
    """Engine-neutral noise model."""

    selected_model: str = "markovian_lindblad"
    collapse_channels: list[CollapseChannelSpec] = field(default_factory=list)
    stochastic_channels: list[StochasticChannelSpec] = field(default_factory=list)
    per_qubit_rates: list[PerQubitRateSpec] = field(default_factory=list)
    supported: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.collapse_channels = [
            ch if isinstance(ch, CollapseChannelSpec) else CollapseChannelSpec.from_dict(ch)
            for ch in list(self.collapse_channels or [])
        ]
        self.stochastic_channels = [
            ch if isinstance(ch, StochasticChannelSpec) else StochasticChannelSpec.from_dict(ch)
            for ch in list(self.stochastic_channels or [])
        ]
        self.per_qubit_rates = [
            item if isinstance(item, PerQubitRateSpec) else PerQubitRateSpec.from_dict(item)
            for item in list(self.per_qubit_rates or [])
        ]


@dataclass
class ReadoutControlSpec:
    """Sampled readout-drive channel."""

    channel: str = ""
    target: int = 0
    kind: str = "readout"
    times: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    scale: float = 1.0
    carrier_freq_Hz: float = 0.0
    carrier_omega_rad_s: float = 0.0
    carrier_phase_rad: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutControlSpec":
        raw = dict(data or {})
        core = {
            "channel",
            "target",
            "kind",
            "times",
            "values",
            "scale",
            "carrier_freq_Hz",
            "carrier_omega_rad_s",
            "carrier_phase_rad",
        }
        return cls(
            channel=str(raw.get("channel", "") or ""),
            target=int(raw.get("target", 0) or 0),
            kind=str(raw.get("kind", "readout") or "readout"),
            times=[float(x) for x in list(raw.get("times", []) or [])],
            values=[float(x) for x in list(raw.get("values", []) or [])],
            scale=float(raw.get("scale", 1.0) or 1.0),
            carrier_freq_Hz=float(raw.get("carrier_freq_Hz", 0.0) or 0.0),
            carrier_omega_rad_s=float(raw.get("carrier_omega_rad_s", 0.0) or 0.0),
            carrier_phase_rad=float(raw.get("carrier_phase_rad", 0.0) or 0.0),
            metadata={key: value for key, value in raw.items() if key not in core},
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "channel": self.channel,
            "target": self.target,
            "kind": self.kind,
            "times": list(self.times),
            "values": list(self.values),
            "scale": self.scale,
            "carrier_freq_Hz": self.carrier_freq_Hz,
            "carrier_omega_rad_s": self.carrier_omega_rad_s,
            "carrier_phase_rad": self.carrier_phase_rad,
        }
        data.update(dict(self.metadata))
        return data


@dataclass
class ReadoutLineSpec:
    """Readout line component projected into the model spec."""

    id: str = ""
    representation: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutLineSpec":
        raw = dict(data or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            representation=str(raw.get("representation", "") or ""),
            description=str(raw.get("description", "") or ""),
            parameters=dict(raw.get("parameters", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "representation": self.representation,
            "description": self.description,
            "parameters": dict(self.parameters),
        }


@dataclass
class ReadoutChainSpec:
    """Readout-chain parameters used by dispersive and classical readout paths."""

    kappa_int_Hz: float = 0.0
    kappa_ext_Hz: float = 0.0
    chi_Hz: float | list[float] = field(default_factory=list)
    eta_chain: float = 1.0
    gain_dB: float = 0.0
    added_noise_photons: float = 0.0
    center_freq_Hz: float = 0.0
    bandwidth_Hz: float = 0.0
    cavity_freq_Hz: float = 0.0
    input_amplitude_noise_rel_sigma: float = 0.0
    input_phase_noise_std_rad: float = 0.0
    input_additive_noise_sigma: float = 0.0
    feedback_success_prob: float = 1.0
    cavity_equation: str = ""
    output_equation: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutChainSpec":
        raw = dict(data or {})
        known = {
            "kappa_int_Hz",
            "kappa_ext_Hz",
            "chi_Hz",
            "eta_chain",
            "gain_dB",
            "added_noise_photons",
            "center_freq_Hz",
            "bandwidth_Hz",
            "cavity_freq_Hz",
            "input_amplitude_noise_rel_sigma",
            "input_phase_noise_std_rad",
            "input_additive_noise_sigma",
            "feedback_success_prob",
            "cavity_equation",
            "output_equation",
        }
        chi_raw = raw.get("chi_Hz", [])
        chi: float | list[float]
        if isinstance(chi_raw, (list, tuple)):
            chi = [float(x) for x in list(chi_raw)]
        else:
            chi = float(chi_raw or 0.0)
        return cls(
            kappa_int_Hz=float(raw.get("kappa_int_Hz", 0.0) or 0.0),
            kappa_ext_Hz=float(raw.get("kappa_ext_Hz", 0.0) or 0.0),
            chi_Hz=chi,
            eta_chain=float(raw.get("eta_chain", 1.0) or 1.0),
            gain_dB=float(raw.get("gain_dB", 0.0) or 0.0),
            added_noise_photons=float(raw.get("added_noise_photons", 0.0) or 0.0),
            center_freq_Hz=float(raw.get("center_freq_Hz", 0.0) or 0.0),
            bandwidth_Hz=float(raw.get("bandwidth_Hz", 0.0) or 0.0),
            cavity_freq_Hz=float(raw.get("cavity_freq_Hz", 0.0) or 0.0),
            input_amplitude_noise_rel_sigma=float(raw.get("input_amplitude_noise_rel_sigma", 0.0) or 0.0),
            input_phase_noise_std_rad=float(raw.get("input_phase_noise_std_rad", 0.0) or 0.0),
            input_additive_noise_sigma=float(raw.get("input_additive_noise_sigma", 0.0) or 0.0),
            feedback_success_prob=float(raw.get("feedback_success_prob", 1.0) or 1.0),
            cavity_equation=str(raw.get("cavity_equation", "") or ""),
            output_equation=str(raw.get("output_equation", "") or ""),
            extras={key: value for key, value in raw.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "kappa_int_Hz": self.kappa_int_Hz,
            "kappa_ext_Hz": self.kappa_ext_Hz,
            "chi_Hz": list(self.chi_Hz) if isinstance(self.chi_Hz, list) else self.chi_Hz,
            "eta_chain": self.eta_chain,
            "gain_dB": self.gain_dB,
            "added_noise_photons": self.added_noise_photons,
            "center_freq_Hz": self.center_freq_Hz,
            "bandwidth_Hz": self.bandwidth_Hz,
            "cavity_freq_Hz": self.cavity_freq_Hz,
            "input_amplitude_noise_rel_sigma": self.input_amplitude_noise_rel_sigma,
            "input_phase_noise_std_rad": self.input_phase_noise_std_rad,
            "input_additive_noise_sigma": self.input_additive_noise_sigma,
            "feedback_success_prob": self.feedback_success_prob,
            "cavity_equation": self.cavity_equation,
            "output_equation": self.output_equation,
        }
        data.update(dict(self.extras))
        return data

    @property
    def is_empty(self) -> bool:
        return (
            self.kappa_int_Hz == 0.0
            and self.kappa_ext_Hz == 0.0
            and (self.chi_Hz == [] or self.chi_Hz == 0.0)
            and self.eta_chain == 1.0
            and self.gain_dB == 0.0
            and self.added_noise_photons == 0.0
            and self.center_freq_Hz == 0.0
            and self.bandwidth_Hz == 0.0
            and self.cavity_freq_Hz == 0.0
            and self.input_amplitude_noise_rel_sigma == 0.0
            and self.input_phase_noise_std_rad == 0.0
            and self.input_additive_noise_sigma == 0.0
            and self.feedback_success_prob == 1.0
            and not self.cavity_equation
            and not self.output_equation
            and not self.extras
        )


@dataclass
class ReadoutSpec:
    """Engine-neutral readout request and chain description."""

    protocol: str = "dispersive_reflectometry"
    chain: ReadoutChainSpec = field(default_factory=ReadoutChainSpec)
    controls: list[ReadoutControlSpec] = field(default_factory=list)
    lines: list[ReadoutLineSpec] = field(default_factory=list)
    reset_events: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chain, ReadoutChainSpec):
            self.chain = ReadoutChainSpec.from_dict(self.chain)
        self.controls = [
            ctrl if isinstance(ctrl, ReadoutControlSpec) else ReadoutControlSpec.from_dict(ctrl)
            for ctrl in list(self.controls or [])
        ]
        self.lines = [
            line if isinstance(line, ReadoutLineSpec) else ReadoutLineSpec.from_dict(line)
            for line in list(self.lines or [])
        ]


@dataclass
class AnalysisRequestSpec:
    """Trajectory data requested by analyser configuration."""

    trajectory: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class StudySpec:
    """Study metadata selected for this model build."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    primary_step: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


def model_spec_from_runtime_dict(
    *,
    solver: str = "se",
    dimension: int = 2,
    t_end: float = 0.0,
    dt: float = 1.0,
    engine: str = "qutip",
    model: dict[str, Any] | None = None,
) -> ModelSpec:
    """Build structured ``ModelSpec`` from plain model data during migration/tests."""
    data = dict(model or {})

    noise_summary = dict(data.get("noise_summary", {}) or {})
    frame_data = dict(data.get("frame", {}) or {})
    primary_step = dict(data.get("primary_step", {}) or {})
    options = dict(primary_step.get("options", {}) or {})
    circuit_data = data.get("circuit")
    return ModelSpec(
        engine=engine,
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
            num_qubits=int(data.get("num_qubits", 1) or 0),
            dimension=int(dimension),
            transmon_levels=int(data.get("transmon_levels", 2) or 2),
            cavity_nmax=int(data.get("cavity_nmax", 0) or 0),
            qubit_freqs_Hz=[float(x) for x in data.get("qubit_freqs_Hz", [])],
            qubit_omega_rad_s=[float(x) for x in data.get("qubit_omega_rad_s", [])],
            lab_frame_qubit_freqs_Hz=[float(x) for x in data.get("lab_frame_qubit_freqs_Hz", [])],
            lab_frame_qubit_omega_rad_s=[float(x) for x in data.get("lab_frame_qubit_omega_rad_s", [])],
            anharmonicity_Hz=[float(x) for x in data.get("anharmonicity_Hz", [])],
            anharmonicity_rad_s=[float(x) for x in data.get("anharmonicity_rad_s", [])],
            cavity_freq_Hz=float(data.get("cavity_freq_Hz", 0.0) or 0.0),
            cavity_omega_rad_s=float(data.get("cavity_omega_rad_s", 0.0) or 0.0),
            g_cavity_Hz=[float(x) for x in data.get("g_cavity_Hz", [])],
            g_cavity_rad_s=[float(x) for x in data.get("g_cavity_rad_s", [])],
            components=list(data.get("components", []) or []),
            connections=list(data.get("connections", []) or []),
            component_summary=dict(data.get("component_summary", {}) or {}),
            structure=dict(data.get("model_structure", {}) or {}),
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
            raw_terms=list(data.get("h_terms", []) or []),
        ),
        noise=NoiseSpec(
            selected_model=str(noise_summary.get("selected_model", "markovian_lindblad")),
            collapse_channels=list(data.get("collapse_operators", []) or []),
            stochastic_channels=list(noise_summary.get("stochastic", []) or []),
            per_qubit_rates=list(noise_summary.get("per_qubit_rates", []) or []),
            supported=list(noise_summary.get("supported", []) or []),
            unsupported=list(noise_summary.get("unsupported", []) or []),
            warnings=list(noise_summary.get("warnings", []) or []),
            config=dict(data.get("noise_cfg", {}) or {}),
        ),
        readout=ReadoutSpec(
            protocol=canonical_readout_protocol(data),
            chain=dict(data.get("readout_chain", {}) or {}),
            controls=list(data.get("readout_controls", []) or []),
            lines=list(data.get("readout_lines", []) or []),
            reset_events=list(data.get("reset_events", []) or []),
            options=options,
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
        metadata={"noise_terms": list(data.get("noise_terms", []) or [])},
    )


@dataclass
class Trajectory:
    """Normalized simulation output trajectory."""

    schema_version: str = SCHEMA_VERSION
    engine: str = "mock"
    times: list[float] = field(default_factory=list)
    wave_function: dict[str, Any] | None = None
    density_matrix: dict[str, Any] | None = None
    classical: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a compact payload containing only populated trajectory fields."""
        payload: dict[str, Any] = {
            "schema_version": str(self.schema_version),
            "engine": str(self.engine),
            "times": list(self.times or []),
        }
        if self.wave_function:
            payload["wave_function"] = dict(self.wave_function)
        if self.density_matrix:
            payload["density_matrix"] = dict(self.density_matrix)
        if self.classical:
            payload["classical"] = dict(self.classical)
        if self.measurements:
            payload["measurements"] = dict(self.measurements)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def __getattribute__(self, name: str):
        if name == "__annotations__":
            cls_annotations = type(self).__dict__.get("__annotations__", {})
            payload_keys = set(object.__getattribute__(self, "to_payload")().keys())
            return {key: value for key, value in cls_annotations.items() if key in payload_keys}
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        return f"Trajectory({self.to_payload()!r})"


@dataclass
class Observables:
    """Computed analysis observables from a trajectory."""

    schema_version: str = SCHEMA_VERSION
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Report:
    """High-level analysis report and error budget summary."""

    schema_version: str = SCHEMA_VERSION
    summary: dict[str, Any] = field(default_factory=dict)
    error_budget: dict[str, float] = field(default_factory=dict)


@dataclass
class SyndromeFrame:
    """QEC syndrome data frame for one decoding task."""

    schema_version: str = SCHEMA_VERSION
    rounds: int = 0
    detectors: list[list[int]] = field(default_factory=list)
    observables: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriorModel:
    """QEC prior model with graph/hypergraph style weighted terms."""

    schema_version: str = SCHEMA_VERSION
    builder_name: str = "mock_prior"
    builder_rev: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecoderInput:
    """Decoder input payload combining syndrome and prior model."""

    schema_version: str = SCHEMA_VERSION
    syndrome: SyndromeFrame = field(default_factory=SyndromeFrame)
    prior: PriorModel = field(default_factory=PriorModel)
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecoderOutput:
    """Normalized decoder output with correction hints and confidence."""

    schema_version: str = SCHEMA_VERSION
    decoder_name: str = "mock_decoder"
    decoder_rev: str = ""
    status: str = "ok"
    corrections: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogicalErrorSummary:
    """Logical error summary derived from decoder output."""

    schema_version: str = SCHEMA_VERSION
    logical_x: float = 0.0
    logical_z: float = 0.0
    shots: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunManifest:
    """Run-level manifest linking inputs, outputs, and digests."""

    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    random_seed: int = 0
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    dependency_fingerprint: str = ""
    digests: dict[str, str] = field(default_factory=dict)

    def finalize_digests(self, out_dir: str | Path) -> None:
        """Compute file digests for all declared outputs."""
        base = Path(out_dir)
        for rel in self.outputs.values():
            p = base / rel
            if p.exists() and p.is_file():
                self.digests[str(rel)] = sha256_file(p)

    def finalize_dependency_fingerprint(self) -> None:
        """Compute deterministic fingerprint from dependency versions."""
        canonical = json.dumps(self.dependencies, sort_keys=True, separators=(",", ":"))
        self.dependency_fingerprint = _sha256_text(canonical)
