"""Engine-neutral lowering helpers used to assemble ``ModelSpec``."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
from typing import Any

from qsim.backend.config import ComponentConfig, ConnectionConfig, DeviceConfig, FrameConfig, SolverConfig, StudyConfig
from qsim.backend.model.common import TWO_PI, expand_value, qubit_field, to_float_list
from qsim.backend.model.noise import lower_noise
from qsim.common.channels import canonical_readout_protocol, safe_float
from qsim.common.schemas import (
    ExecutableModel,
    FrameSpec,
    HamiltonianSpec,
    ComponentSummarySpec,
    ModelStructureSpec,
    ReadoutSpec,
    ReadoutChainSpec,
    ReadoutControlSpec,
    ReadoutLineSpec,
    StudySpec,
    SystemComponentSpec,
    SystemConnectionSpec,
    SystemSpec,
    TimeSpec,
    control_dict_to_hamiltonian_term,
)
from qsim.common.unit_schema import NS_TO_S


SUPPORTED_SUBSYSTEM_MODELS = {
    "qubit_network",
    "transmon_nlevel",
    "cqed_jc",
    "cqed_dispersive",
    "cavity_classical_readout",
}
REPRESENTATION_ALIASES = {"q": "quantum", "quantum": "quantum", "c": "classical", "classical": "classical"}
XY_RE = re.compile(r"^XY_(\d+)$", re.IGNORECASE)
Z_RE = re.compile(r"^Z_(\d+)$", re.IGNORECASE)
RO_RE = re.compile(r"^RO_(\d+)$", re.IGNORECASE)
TC_RE = re.compile(r"^TC_(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ComponentSummary:
    """Compact component inventory for the final system schema."""

    count: int
    ids: list[str]
    types: list[str]
    representations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "ids": list(self.ids),
            "types": list(self.types),
            "representations": list(self.representations),
        }


@dataclass(frozen=True)
class ReadoutLineInfo:
    """Readout line metadata preserved in the engine-neutral schema."""

    id: str
    representation: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "representation": self.representation,
            "description": self.description,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class CompositeMetadata:
    """Structured metadata projected from the device config."""

    components: list[ComponentConfig]
    connections: list[ConnectionConfig]
    component_summary: ComponentSummary
    readout_lines: list[ReadoutLineInfo]

    @property
    def component_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.components]

    @property
    def connection_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.connections]

    @property
    def readout_line_dicts(self) -> list[dict[str, Any]]:
        return [line.to_dict() for line in self.readout_lines]


@dataclass(frozen=True)
class QuantumProjection:
    """Quantum-only projection used to derive dimensions and qubit defaults."""

    qubits: list[dict[str, Any]]
    cavity_freq_Hz: float
    cavity_nmax: int
    transmon_levels: int


@dataclass(frozen=True)
class ModelStructure:
    """Resolved subsystem structure after study selection is applied."""

    qubit_representation: str = "quantum"
    cavity_representation: str = ""
    feedline_representation: str = ""
    qubit_cavity_coupling: str = ""
    cavity_feedline_coupling: str = ""

    @property
    def has_structured_signature(self) -> bool:
        return all(
            (
                self.qubit_representation,
                self.cavity_representation,
                self.feedline_representation,
                self.qubit_cavity_coupling,
                self.cavity_feedline_coupling,
            )
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "qubit_representation": self.qubit_representation,
            "cavity_representation": self.cavity_representation,
            "feedline_representation": self.feedline_representation,
            "qubit_cavity_coupling": self.qubit_cavity_coupling,
            "cavity_feedline_coupling": self.cavity_feedline_coupling,
        }


@dataclass(frozen=True)
class StructureScope:
    """Component/connection subset selected by a study step."""

    components: list[ComponentConfig]
    connections: list[ConnectionConfig]


@dataclass(frozen=True)
class DispersiveReadoutLink:
    """Dispersive qubit-cavity relation used by readout-chain inference."""

    a: str
    b: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ReadoutTopology:
    """Readout-relevant topology projected from components and connections."""

    components: list[ComponentConfig]
    connections: list[ConnectionConfig]
    qubit_index: dict[str, int]
    cavity_params: dict[str, Any]
    line_params: dict[str, Any]
    io_params: dict[str, Any]
    dispersive_links: list[DispersiveReadoutLink]


@dataclass(frozen=True)
class SystemContext:
    """Resolved system identity before field/frame-dependent values are filled."""

    raw_num_qubits: int
    num_qubits: int
    simulation_level: str
    model_type: str
    structure: ModelStructure
    composite_meta: CompositeMetadata
    composite_quantum: QuantumProjection
    raw_qubits: list[dict[str, Any]]
    transmon_levels: int
    cavity_nmax: int


@dataclass(frozen=True)
class SampledChannelsIR:
    """Lowered sampled channels split by Hamiltonian role."""

    controls: list[dict[str, Any]]
    readout_controls: list[dict[str, Any]]
    pulse_carrier_reference_freqs_Hz: list[float]


@dataclass(frozen=True)
class FrameResolution:
    """Frame spec plus frequency arrays needed by system lowering."""

    spec: FrameSpec
    lab_frame_qubit_freqs_Hz: list[float]
    qubit_freqs_Hz: list[float]


@dataclass(frozen=True)
class ReadoutTopologyInput:
    """Typed readout topology bundle used by readout spec builders."""

    components: list[ComponentConfig]
    connections: list[ConnectionConfig]
    primary_step: dict[str, Any]
    readout_chain: dict[str, Any] | None = None


def _device_value(hw: DeviceConfig, key: str, default: Any = None) -> Any:
    value = getattr(hw, key, None)
    return default if value is None else value


def lower_study(study: StudyConfig) -> StudySpec:
    steps = [dict(step) for step in study.steps]
    selected = dict(study.primary_step)
    summary = {
        "count": len(steps),
        "names": [str(step.get("name", "")) for step in steps],
        "solver_modes": [str(step.get("solver_mode", "")) for step in steps],
        "primary_name": str(selected.get("name", "")),
        "active_components": list(selected.get("active_components", []) or []),
        "active_connections": list(selected.get("active_connections", []) or []),
    }
    return StudySpec(steps=steps, primary_step=selected, summary=summary)


def composite_metadata(hw: DeviceConfig) -> CompositeMetadata:
    component_summary = ComponentSummary(
        count=len(hw.components),
        ids=[comp.id for comp in hw.components],
        types=[comp.type for comp in hw.components],
        representations=[comp.representation for comp in hw.components],
    )
    readout_lines = [
        ReadoutLineInfo(
            id=comp.id,
            representation=comp.representation,
            description=comp.description,
            parameters=dict(comp.parameters),
        )
        for comp in hw.components
        if comp.type.strip().lower() == "readout_line"
    ]
    return CompositeMetadata(
        components=list(hw.components),
        connections=list(hw.connections),
        component_summary=component_summary,
        readout_lines=readout_lines,
    )


def composite_quantum_projection(hw: DeviceConfig) -> QuantumProjection:
    qubits: list[dict[str, Any]] = []
    cavity_freq_hz = 0.0
    cavity_nmax = 0
    transmon_levels = 2
    for comp in hw.components:
        if comp.representation.strip().lower() == "disabled":
            continue
        comp_type = comp.type.strip().lower()
        basis = dict(comp.basis)
        parameters = dict(comp.parameters)
        local_noise = dict(comp.noise)
        if comp_type == "transmon":
            q_payload: dict[str, Any] = {
                "freq_Hz": float(parameters.get("freq_Hz", 0.0)),
                "anharmonicity_Hz": float(parameters.get("anharmonicity_Hz", -2.0e8)),
            }
            for key in ("T1_s", "T2_s", "Tphi_s", "Tup_s", "gamma1_Hz", "gamma_phi_Hz", "gamma_up_Hz"):
                if key in local_noise:
                    q_payload[key] = local_noise[key]
            qubits.append(q_payload)
            if str(basis.get("kind", "")).strip().lower() == "nlevel":
                transmon_levels = max(transmon_levels, int(basis.get("levels", 2) or 2))
        elif comp_type == "resonator" and comp.representation.strip().lower() == "quantum":
            if cavity_freq_hz == 0.0:
                cavity_freq_hz = float(parameters.get("freq_Hz", 0.0))
                cavity_nmax = int(basis.get("nmax", 0) or 0)
    return QuantumProjection(
        qubits=qubits,
        cavity_freq_Hz=cavity_freq_hz,
        cavity_nmax=cavity_nmax,
        transmon_levels=transmon_levels,
    )


def _normalize_representation(value: Any, *, default: str = "") -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return REPRESENTATION_ALIASES.get(raw, raw)


def _connection_endpoints(conn: ConnectionConfig) -> set[str]:
    return {endpoint for endpoint in (conn.a.strip(), conn.b.strip(), conn.via.strip()) if endpoint}


def _selected_structure_scope(
    hw: DeviceConfig, primary_step: dict[str, Any] | None
) -> StructureScope:
    selected = dict(primary_step or {})
    components = list(hw.components)
    connections = list(hw.connections)
    active_components = {str(item).strip() for item in list(selected.get("active_components", []) or []) if str(item).strip()}
    active_connections = {
        str(item).strip() for item in list(selected.get("active_connections", []) or []) if str(item).strip()
    }
    if active_connections:
        connections = [conn for conn in connections if conn.id.strip() in active_connections]
        implied_components: set[str] = set()
        for conn in connections:
            implied_components.update(_connection_endpoints(conn))
        active_components |= implied_components
    if active_components:
        components = [comp for comp in components if comp.id.strip() in active_components]
        kept_component_ids = {comp.id.strip() for comp in components}
        connections = [
            conn
            for conn in connections
            if _connection_endpoints(conn).issubset(kept_component_ids)
        ]

    representation_overrides = dict(selected.get("representations", {}) or {})
    basis_overrides = dict(selected.get("bases", {}) or {})
    scoped_components: list[ComponentConfig] = []
    for comp in components:
        comp_id = comp.id.strip()
        updated = comp
        if comp_id in representation_overrides:
            updated = replace(
                updated,
                representation=_normalize_representation(
                    representation_overrides.get(comp_id, ""),
                    default=comp.representation,
                ),
            )
        if comp_id in basis_overrides and isinstance(basis_overrides[comp_id], dict):
            updated = replace(updated, basis=dict(basis_overrides[comp_id]))
        scoped_components.append(updated)
    return StructureScope(components=scoped_components, connections=connections)


def resolve_model_structure(hw: DeviceConfig, primary_step: dict[str, Any] | None = None) -> ModelStructure:
    scope = _selected_structure_scope(hw, primary_step)

    def component_rep(comp_type: str) -> str:
        for comp in scope.components:
            if comp.type.strip().lower() == comp_type:
                return _normalize_representation(comp.representation)
        return ""

    qc_couplings: set[str] = set()
    cf_couplings: set[str] = set()
    for conn in scope.connections:
        conn_type = conn.type.strip().lower()
        if conn_type in {"dispersive", "jc"}:
            qc_couplings.add("dispersive" if conn_type == "dispersive" else "jc")
        if conn_type == "readout_feedline":
            cf_couplings.add("input_output")

    return ModelStructure(
        qubit_representation=component_rep("transmon") or "quantum",
        cavity_representation=component_rep("resonator"),
        feedline_representation=component_rep("readout_line"),
        qubit_cavity_coupling=next(iter(qc_couplings)) if len(qc_couplings) == 1 else "",
        cavity_feedline_coupling=next(iter(cf_couplings)) if len(cf_couplings) == 1 else "",
    )


def resolve_model_type(req_level: str, hw: DeviceConfig, primary_step: dict[str, Any] | None = None) -> tuple[str, ModelStructure]:
    structure = resolve_model_structure(hw, primary_step)
    options = dict((primary_step or {}).get("options", {}) or {})
    explicit_model = str(options.get("subsystem_model", "") or "").strip().lower()
    if explicit_model in SUPPORTED_SUBSYSTEM_MODELS:
        return explicit_model, structure

    model_type = "qubit_network"
    if req_level == "nlevel":
        model_type = "transmon_nlevel"
    elif req_level == "cqed":
        model_type = "cqed_jc"
        if (
            structure.has_structured_signature
            and structure.qubit_representation == "quantum"
            and structure.cavity_representation == "quantum"
            and structure.feedline_representation == "classical"
            and structure.qubit_cavity_coupling == "dispersive"
            and structure.cavity_feedline_coupling == "input_output"
        ):
            model_type = "cqed_dispersive"
    return model_type, structure


def lower_time(executable: ExecutableModel, pulse_samples: dict[str, dict[str, Any]], solver_run: SolverConfig) -> TimeSpec:
    inferred_t_end_s = float(executable.metadata.get("t_end_s", 0.0))
    inferred_dt_s = 1.0 * NS_TO_S
    for ch_payload in pulse_samples.values():
        times = ch_payload.get("t")
        if times is None:
            continue
        t_list = to_float_list(times)
        if not t_list:
            continue
        inferred_t_end_s = max(inferred_t_end_s, t_list[-1])
        if len(t_list) > 1:
            inferred_dt_s = min(inferred_dt_s, max(1e-15, t_list[1] - t_list[0]))
    if inferred_t_end_s <= 0.0:
        inferred_t_end_s = 1000.0 * NS_TO_S

    dt = inferred_dt_s if solver_run.dt_s is None else float(solver_run.dt_s)
    t_padding_raw = solver_run.t_padding_s
    t_padding_s = max(0.0, 0.0 if t_padding_raw is None else float(t_padding_raw))
    t_end = inferred_t_end_s + t_padding_s if solver_run.t_end_s is None else float(solver_run.t_end_s)
    return TimeSpec(dt_s=dt, t_end_s=t_end, t_padding_s=t_padding_s)


def lower_system_context(executable: ExecutableModel, hw: DeviceConfig, study: StudySpec) -> SystemContext:
    raw_num_qubits = int(max(0, executable.metadata.get("num_qubits", 0)))
    composite_quantum = composite_quantum_projection(hw)
    transmon_levels = int(_device_value(hw, "transmon_levels", composite_quantum.transmon_levels))
    cavity_nmax = int(_device_value(hw, "cavity_nmax", composite_quantum.cavity_nmax))

    req_level = str(_device_value(hw, "simulation_level", executable.level)).strip().lower()
    if req_level not in {"qubit", "nlevel", "cqed"}:
        req_level = "qubit"
    if req_level == "nlevel" and transmon_levels <= 2:
        req_level = "qubit"
    if req_level == "cqed" and cavity_nmax <= 0:
        req_level = "nlevel" if transmon_levels > 2 else "qubit"

    model_type, structure = resolve_model_type(req_level, hw, study.primary_step)
    num_qubits = 0 if model_type == "cavity_classical_readout" else int(max(1, raw_num_qubits))
    raw_qubits = list(hw.qubit_dicts or composite_quantum.qubits or [])
    return SystemContext(
        raw_num_qubits=raw_num_qubits,
        num_qubits=num_qubits,
        simulation_level=req_level,
        model_type=model_type,
        structure=structure,
        composite_meta=composite_metadata(hw),
        composite_quantum=composite_quantum,
        raw_qubits=[dict(q) for q in raw_qubits if isinstance(q, dict)],
        transmon_levels=transmon_levels,
        cavity_nmax=cavity_nmax,
    )


def lower_system(
    executable: ExecutableModel,
    hw: DeviceConfig,
    study: StudySpec,
    context: SystemContext,
    frame: FrameResolution,
) -> SystemSpec:
    num_qubits = context.num_qubits
    anharmonicity_Hz = expand_value(
        _device_value(hw, "anharmonicity_Hz", qubit_field(context.raw_qubits, "anharmonicity_Hz", -0.2) if context.raw_qubits else -0.2),
        num_qubits,
        -0.2,
    )
    g_cavity_Hz = expand_value(_device_value(hw, "g_cavity_Hz", 0.0), num_qubits, 0.0)
    if context.simulation_level == "qubit":
        dim = int(_device_value(hw, "dimension", 1 if num_qubits == 0 else 2**num_qubits))
    elif context.simulation_level == "nlevel":
        dim = int(_device_value(hw, "dimension", 1 if num_qubits == 0 else context.transmon_levels**num_qubits))
    elif context.model_type == "cavity_classical_readout":
        dim = int(_device_value(hw, "dimension", 1))
    else:
        dim = int(_device_value(hw, "dimension", (context.cavity_nmax + 1) * (context.transmon_levels**num_qubits)))

    cavity_freq_hz = float(_device_value(hw, "cavity_freq_Hz", context.composite_quantum.cavity_freq_Hz))
    return SystemSpec(
        model_type=context.model_type,
        simulation_level=context.simulation_level,
        num_qubits=num_qubits,
        dimension=dim,
        transmon_levels=context.transmon_levels,
        cavity_nmax=context.cavity_nmax,
        qubit_freqs_Hz=frame.qubit_freqs_Hz,
        qubit_omega_rad_s=[TWO_PI * float(x) for x in frame.qubit_freqs_Hz],
        lab_frame_qubit_freqs_Hz=frame.lab_frame_qubit_freqs_Hz,
        lab_frame_qubit_omega_rad_s=[TWO_PI * float(x) for x in frame.lab_frame_qubit_freqs_Hz],
        anharmonicity_Hz=anharmonicity_Hz,
        anharmonicity_rad_s=[TWO_PI * float(x) for x in anharmonicity_Hz],
        cavity_freq_Hz=cavity_freq_hz,
        cavity_omega_rad_s=TWO_PI * cavity_freq_hz,
        g_cavity_Hz=g_cavity_Hz,
        g_cavity_rad_s=[TWO_PI * float(x) for x in g_cavity_Hz],
        components=[SystemComponentSpec.from_dict(item) for item in context.composite_meta.component_dicts],
        connections=[SystemConnectionSpec.from_dict(item) for item in context.composite_meta.connection_dicts],
        component_summary=ComponentSummarySpec.from_dict(context.composite_meta.component_summary.to_dict()),
        structure=ModelStructureSpec.from_dict(context.structure.to_dict()),
        assumptions={
            "qubit_representation": "two_level_pauli (qubit) or truncated_oscillator (nlevel/cqed)",
            "subsystem_model": "qubit_network | transmon_nlevel | cqed_jc | cqed_dispersive | cavity_classical_readout",
            "truncation_cfg_from_backend": executable.metadata.get("truncation", {}),
            "study_selection": study.summary,
            "requested_subsystem_model": str((study.primary_step.get("options", {}) or {}).get("subsystem_model", "") or "").strip().lower(),
        },
    )


def _sampled_control_record(
    *,
    channel: str,
    times: list[float],
    values: list[float],
    scale: float,
    axis: str | None = None,
    target: int | None = None,
    target_pair: list[int] | None = None,
    kind: str | None = None,
    carrier_freq_Hz: float = 0.0,
    carrier_phase_rad: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "channel": str(channel),
        "times": list(times),
        "values": list(values),
        "scale": float(scale),
        "carrier_freq_Hz": float(carrier_freq_Hz),
        "carrier_omega_rad_s": TWO_PI * float(carrier_freq_Hz),
        "carrier_phase_rad": float(carrier_phase_rad),
    }
    if kind is not None:
        record["kind"] = str(kind)
    if axis is not None:
        record["axis"] = str(axis)
    if target is not None:
        record["target"] = int(target)
    if target_pair is not None:
        record["target_pair"] = [int(x) for x in target_pair]
    record.update(dict(metadata or {}))
    return record


def lower_sampled_channels(hw: DeviceConfig, pulse_samples: dict[str, dict[str, Any]], num_qubits: int) -> SampledChannelsIR:
    controls: list[dict[str, Any]] = []
    readout_controls: list[dict[str, Any]] = []
    pulse_refs = [0.0 for _ in range(num_qubits)]
    control_scale = float(_device_value(hw, "control_scale", 1.0))
    raw_couplings = list(hw.couplings)

    for ch_name, ch_payload in pulse_samples.items():
        times = to_float_list(ch_payload.get("t", []))
        values = to_float_list(ch_payload.get("y", []))
        quadrature_values = to_float_list(ch_payload.get("y_quadrature", [])) if "y_quadrature" in ch_payload else []
        if not times or not values:
            continue
        carrier_freq_Hz = float(to_float_list(ch_payload.get("carrier_freq_Hz", [0.0]))[0])
        carrier_phase_rad = float(to_float_list(ch_payload.get("carrier_phase_rad", [0.0]))[0])

        mxy = XY_RE.match(ch_name)
        mz = Z_RE.match(ch_name)
        mro = RO_RE.match(ch_name)
        mtc = TC_RE.match(ch_name)
        if mro:
            readout_controls.append(
                _sampled_control_record(
                    channel=ch_name,
                    kind="readout",
                    target=int(mro.group(1)),
                    times=times,
                    values=values,
                    scale=control_scale,
                    carrier_freq_Hz=carrier_freq_Hz,
                    carrier_phase_rad=carrier_phase_rad,
                )
            )
            continue
        if mtc:
            pair_index = int(mtc.group(1))
            coupling = raw_couplings[pair_index] if 0 <= pair_index < len(raw_couplings) else None
            i = int(coupling.i) if coupling is not None else 0
            j = int(coupling.j) if coupling is not None else 1
            if 0 <= i < num_qubits and 0 <= j < num_qubits and i != j:
                controls.append(
                    _sampled_control_record(
                        channel=ch_name,
                        axis="zz",
                        target_pair=[i, j],
                        times=times,
                        values=values,
                        scale=1.0,
                        metadata={"pair_index": pair_index},
                    )
                )
            continue

        target = int(mxy.group(1)) if mxy else int(mz.group(1)) if mz else None
        axis = "x" if mxy else "z" if mz else None
        if axis is None or target is None or target >= num_qubits:
            continue
        if axis == "x" and carrier_freq_Hz != 0.0 and pulse_refs[target] == 0.0:
            pulse_refs[target] = carrier_freq_Hz
        if axis == "x" and quadrature_values and any(abs(float(v)) > 1e-15 for v in quadrature_values):
            cos_phase = math.cos(carrier_phase_rad)
            sin_phase = math.sin(carrier_phase_rad)
            controls.append(
                _sampled_control_record(
                    channel=ch_name,
                    target=target,
                    axis="x",
                    times=times,
                    values=[float(i_val) * cos_phase - float(q_val) * sin_phase for i_val, q_val in zip(values, quadrature_values, strict=False)],
                    scale=control_scale,
                    carrier_freq_Hz=carrier_freq_Hz,
                    carrier_phase_rad=0.0,
                )
            )
            controls.append(
                _sampled_control_record(
                    channel=f"{ch_name}:drag_q",
                    target=target,
                    axis="y",
                    times=times,
                    values=[float(i_val) * sin_phase + float(q_val) * cos_phase for i_val, q_val in zip(values, quadrature_values, strict=False)],
                    scale=control_scale,
                    carrier_freq_Hz=carrier_freq_Hz,
                    carrier_phase_rad=0.0,
                )
            )
            continue

        controls.append(
            _sampled_control_record(
                channel=ch_name,
                target=target,
                axis=axis,
                times=times,
                values=values,
                scale=control_scale,
                carrier_freq_Hz=carrier_freq_Hz,
                carrier_phase_rad=carrier_phase_rad,
            )
        )

    return SampledChannelsIR(controls=controls, readout_controls=readout_controls, pulse_carrier_reference_freqs_Hz=pulse_refs)


def lower_frame(
    frame: FrameConfig,
    hw: DeviceConfig,
    raw_qubits: list[dict[str, Any]],
    channels: SampledChannelsIR,
    num_qubits: int,
) -> FrameResolution:
    mode = str(frame.mode).strip().lower()
    if mode not in {"rotating", "lab"}:
        mode = "rotating"
    reference = str(frame.reference).strip().lower()
    if reference not in {"pulse_carrier", "explicit", "none"}:
        reference = "pulse_carrier"
    rwa = bool(frame.rwa)

    raw_explicit_refs = frame.qubit_reference_freqs_Hz
    explicit_refs = expand_value(raw_explicit_refs, num_qubits, 0.0)
    if mode == "lab" or reference == "none":
        reference_freqs = [0.0 for _ in range(num_qubits)]
    elif reference == "explicit":
        reference_freqs = [float(x) for x in explicit_refs]
    else:
        reference_freqs = [float(x) for x in channels.pulse_carrier_reference_freqs_Hz]

    default_w = float(_device_value(hw, "qubit_freq_Hz", 0.0))
    raw_w = _device_value(hw, "qubit_freqs_Hz")
    if raw_w is None and raw_qubits:
        raw_w = qubit_field(raw_qubits, "freq_Hz", default_w)
    lab_freqs = [float(x) for x in (raw_w if raw_w is not None else [default_w for _ in range(num_qubits)])][:num_qubits]
    if len(lab_freqs) < num_qubits:
        lab_freqs.extend([default_w] * (num_qubits - len(lab_freqs)))

    for ctrl in channels.controls:
        if "target" not in ctrl:
            continue
        target = int(ctrl["target"])
        ref = float(reference_freqs[target]) if 0 <= target < num_qubits else 0.0
        ctrl["reference_freq_Hz"] = ref
        ctrl["reference_omega_rad_s"] = TWO_PI * ref
        ctrl["drive_detuning_Hz"] = float(ctrl.get("carrier_freq_Hz", 0.0)) - ref
        ctrl["drive_delta_rad_s"] = TWO_PI * float(ctrl["drive_detuning_Hz"])

    qubit_freqs = [float(lab_freqs[q]) - float(reference_freqs[q]) for q in range(num_qubits)]
    return FrameResolution(
        spec=FrameSpec(
            mode=mode,
            reference=reference,
            rwa=rwa,
            qubit_reference_freqs_Hz=reference_freqs,
            qubit_reference_omega_rad_s=[TWO_PI * float(x) for x in reference_freqs],
            pulse_carrier_reference_freqs_Hz=list(channels.pulse_carrier_reference_freqs_Hz),
            pulse_carrier_reference_omega_rad_s=[TWO_PI * float(x) for x in channels.pulse_carrier_reference_freqs_Hz],
        ),
        lab_frame_qubit_freqs_Hz=lab_freqs,
        qubit_freqs_Hz=qubit_freqs,
    )


def lower_couplings(hw: DeviceConfig, num_qubits: int) -> list[dict[str, Any]]:
    couplings = []
    for c in hw.couplings:
        i, j = int(c.i), int(c.j)
        if i == j or i < 0 or j < 0 or i >= num_qubits or j >= num_qubits:
            continue
        g_hz = float(c.g_Hz)
        couplings.append({"i": i, "j": j, "g_Hz": g_hz, "g_rad_s": TWO_PI * g_hz, "kind": c.kind})
    return couplings


def lower_hamiltonian(
    executable: ExecutableModel,
    channels: SampledChannelsIR,
    couplings: list[dict[str, Any]],
) -> HamiltonianSpec:
    return HamiltonianSpec(
        coupling_terms=couplings,
        control_terms=[control_dict_to_hamiltonian_term(ctrl, kind="control") for ctrl in channels.controls],
        readout_drive_terms=[
            control_dict_to_hamiltonian_term(ctrl, kind="readout_drive") for ctrl in channels.readout_controls
        ],
        raw_terms=list(executable.h_terms),
    )


def readout_topology_input(
    components: list[ComponentConfig],
    connections: list[ConnectionConfig],
    primary_step: dict[str, Any] | None = None,
    readout_chain: dict[str, Any] | None = None,
) -> ReadoutTopologyInput:
    return ReadoutTopologyInput(
        components=list(components),
        connections=list(connections),
        primary_step=dict(primary_step or {}),
        readout_chain=dict(readout_chain or {}) or None,
    )


def readout_coupling_prefactor(kappa_ext_hz: float) -> float:
    """Return the input-output coupling prefactor from external kappa in Hz."""
    return math.sqrt(max(0.0, TWO_PI * float(kappa_ext_hz)))


def readout_topology(model_data: ReadoutTopologyInput) -> ReadoutTopology:
    """Collect readout-relevant topology pieces from components/connections."""
    qubit_index: dict[str, int] = {}
    cavity_params: dict[str, Any] = {}
    line_params: dict[str, Any] = {}
    io_params: dict[str, Any] = {}
    dispersive_links: list[DispersiveReadoutLink] = []

    for comp in model_data.components:
        comp_type = comp.type.strip().lower()
        params = dict(comp.parameters)
        if comp_type == "transmon":
            qubit_index[comp.id or f"q{len(qubit_index)}"] = len(qubit_index)
        elif comp_type == "resonator" and not cavity_params:
            cavity_params = params
        elif comp_type == "readout_line" and not line_params:
            line_params = params

    for conn in model_data.connections:
        conn_type = conn.type.strip().lower()
        params = dict(conn.parameters)
        if conn_type == "dispersive":
            dispersive_links.append(DispersiveReadoutLink(a=conn.a, b=conn.b, parameters=params))
        elif conn_type == "readout_feedline" and not io_params:
            io_params = params

    return ReadoutTopology(
        components=list(model_data.components),
        connections=list(model_data.connections),
        qubit_index=qubit_index,
        cavity_params=cavity_params,
        line_params=line_params,
        io_params=io_params,
        dispersive_links=dispersive_links,
    )


def infer_cqed_readout_chain(model_data: ReadoutTopologyInput, n_qubits: int) -> dict[str, Any]:
    """Infer a CQED quantum-cavity/readout-line parameter bundle."""
    explicit = dict(model_data.readout_chain or {})
    if explicit:
        chain = dict(explicit)
        chi = chain.get("chi_Hz", [0.0 for _ in range(max(1, int(n_qubits)))])
        if not isinstance(chi, (list, tuple)):
            chi = [float(chi) for _ in range(max(1, int(n_qubits)))]
        chain["chi_Hz"] = [safe_float(x, 0.0) for x in list(chi)[: int(n_qubits)]]
        return chain

    topology = readout_topology(model_data)
    qubit_index = dict(topology.qubit_index)
    cavity_params = dict(topology.cavity_params)
    line_params = dict(topology.line_params)
    io_params = dict(topology.io_params)
    chi_hz = [0.0 for _ in range(max(1, int(n_qubits)))]

    for item in topology.dispersive_links:
        params = dict(item.parameters)
        qid = item.a if item.a in qubit_index else item.b
        q = qubit_index.get(qid)
        if q is not None and q < len(chi_hz):
            chi_hz[q] = safe_float(params.get("chi_Hz", cavity_params.get("chi_Hz", 0.0)), 0.0)
    if not any(abs(val) > 0.0 for val in chi_hz):
        fallback = safe_float(cavity_params.get("chi_Hz", 0.0), 0.0)
        chi_hz = [fallback for _ in range(max(1, int(n_qubits)))]

    return {
        "kappa_int_Hz": safe_float(cavity_params.get("kappa_int_Hz", 0.0), 0.0),
        "kappa_ext_Hz": safe_float(io_params.get("kappa_ext_Hz", cavity_params.get("kappa_ext_Hz", 0.0)), 0.0),
        "chi_Hz": chi_hz[: int(n_qubits)],
        "eta_chain": safe_float(io_params.get("eta_chain", line_params.get("eta_chain", 1.0)), 1.0),
        "gain_dB": safe_float(line_params.get("gain_dB", 0.0), 0.0),
        "added_noise_photons": safe_float(line_params.get("added_noise_photons", 0.0), 0.0),
        "center_freq_Hz": safe_float(line_params.get("center_freq_Hz", cavity_params.get("freq_Hz", 0.0)), 0.0),
        "bandwidth_Hz": safe_float(io_params.get("bandwidth_Hz", line_params.get("bandwidth_Hz", 0.0)), 0.0),
    }


def infer_classical_readout_chain(model_data: ReadoutTopologyInput) -> dict[str, Any]:
    """Infer a classical resonator/readout-line parameter bundle."""
    explicit = dict(model_data.readout_chain or {})
    if explicit:
        return explicit

    topology = readout_topology(model_data)
    cavity_params = dict(topology.cavity_params)
    line_params = dict(topology.line_params)
    io_params = dict(topology.io_params)
    chi_hz = 0.0
    for item in topology.dispersive_links:
        if chi_hz == 0.0:
            params = dict(item.parameters)
            chi_hz = safe_float(params.get("chi_Hz", cavity_params.get("chi_Hz", 0.0)), 0.0)
    if chi_hz == 0.0:
        chi_hz = safe_float(cavity_params.get("chi_Hz", 0.0), 0.0)

    io_equations = dict(io_params.get("input_output", {}) or {})
    return {
        "kappa_int_Hz": safe_float(cavity_params.get("kappa_int_Hz", 0.0), 0.0),
        "kappa_ext_Hz": safe_float(io_params.get("kappa_ext_Hz", cavity_params.get("kappa_ext_Hz", 0.0)), 0.0),
        "chi_Hz": float(chi_hz),
        "eta_chain": safe_float(io_params.get("eta_chain", line_params.get("eta_chain", 1.0)), 1.0),
        "gain_dB": safe_float(line_params.get("gain_dB", 0.0), 0.0),
        "added_noise_photons": safe_float(line_params.get("added_noise_photons", 0.0), 0.0),
        "center_freq_Hz": safe_float(line_params.get("center_freq_Hz", cavity_params.get("freq_Hz", 0.0)), 0.0),
        "bandwidth_Hz": safe_float(io_params.get("bandwidth_Hz", line_params.get("bandwidth_Hz", 0.0)), 0.0),
        "cavity_freq_Hz": safe_float(cavity_params.get("freq_Hz", 0.0), 0.0),
        "input_amplitude_noise_rel_sigma": safe_float(line_params.get("input_amplitude_noise_rel_sigma", io_params.get("input_amplitude_noise_rel_sigma", 0.0)), 0.0),
        "input_phase_noise_std_rad": safe_float(line_params.get("input_phase_noise_std_rad", io_params.get("input_phase_noise_std_rad", 0.0)), 0.0),
        "input_additive_noise_sigma": safe_float(line_params.get("input_additive_noise_sigma", io_params.get("input_additive_noise_sigma", 0.0)), 0.0),
        "feedback_success_prob": safe_float(line_params.get("feedback_success_prob", io_params.get("feedback_success_prob", 1.0)), 1.0),
        "cavity_equation": str(io_equations.get("cavity_equation", "")),
        "output_equation": str(io_equations.get("output_equation", "")),
    }


def has_classical_readout_line(model_data: ReadoutTopologyInput) -> bool:
    """Return whether the model has a classical readout-line component."""
    for comp in model_data.components:
        if comp.type.strip().lower() != "readout_line":
            continue
        if comp.representation.strip().lower() == "classical":
            return True
    return False


def resolve_hybrid_update_mode(model_data: ReadoutTopologyInput) -> str:
    """Resolve hybrid classical-readout update policy from model options."""
    options = dict(model_data.primary_step.get("options", {}) or {})
    raw = str(
        options.get(
            "hybrid_readout_update",
            options.get("classical_readout_update", options.get("hybrid_update_mode", "predictor_corrector")),
        )
        or "predictor_corrector"
    ).strip().lower()
    if raw in {"staggered", "interleaved", "explicit", "legacy"}:
        return "staggered"
    if raw in {"predictor_corrector", "predictor-corrector", "pc", "midpoint"}:
        return "predictor_corrector"
    return "predictor_corrector"


def resolve_readout_protocol(model_data: ReadoutTopologyInput) -> str:
    """Resolve readout/measurement protocol aliases to canonical tokens."""
    return canonical_readout_protocol({"primary_step": model_data.primary_step})


def lower_readout(
    executable: ExecutableModel,
    study: StudySpec,
    context: SystemContext,
    channels: SampledChannelsIR,
) -> ReadoutSpec:
    model_data = readout_topology_input(
        context.composite_meta.components,
        context.composite_meta.connections,
        primary_step=study.primary_step,
    )
    chain = (
        infer_classical_readout_chain(model_data)
        if context.model_type == "cavity_classical_readout"
        else infer_cqed_readout_chain(model_data, context.num_qubits)
    )
    return ReadoutSpec(
        protocol=resolve_readout_protocol(model_data),
        chain=ReadoutChainSpec.from_dict(chain),
        controls=[ReadoutControlSpec.from_dict(ctrl) for ctrl in channels.readout_controls],
        lines=[ReadoutLineSpec.from_dict(line) for line in context.composite_meta.readout_line_dicts],
        reset_events=list(executable.metadata.get("reset_events", [])),
        options=dict((study.primary_step.get("options", {}) or {})),
    )
