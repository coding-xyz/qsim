"""System summary schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import Any

from qsim.schemas.components import (
    ReadoutLineComponentSpec,
    ResonatorComponentSpec,
    SystemComponentSpec,
    TransmonComponentSpec,
    system_component_from_dict,
)
from qsim.schemas.connections import (
    DispersiveConnectionSpec,
    JCConnectionSpec,
    ReadoutFeedlineConnectionSpec,
    SystemConnectionSpec,
    ZZConnectionSpec,
    system_connection_from_dict,
)
from qsim.schemas._factory_utils import _construct_dataclass


@dataclass
class ModelStructureSpec:
    """Subsystem structure selected from active components and connections."""

    qubit_representation: str = "quantum"
    cavity_representation: str = ""
    feedline_representation: str = ""
    qubit_cavity_coupling: str = ""
    cavity_feedline_coupling: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ModelStructureSpec":
        """Construct a structure summary from a plain dictionary."""
        raw = dict(data or {})
        return cls(
            qubit_representation=str(raw.get("qubit_representation", "quantum") or "quantum"),
            cavity_representation=str(raw.get("cavity_representation", "") or ""),
            feedline_representation=str(raw.get("feedline_representation", "") or ""),
            qubit_cavity_coupling=str(raw.get("qubit_cavity_coupling", "") or ""),
            cavity_feedline_coupling=str(raw.get("cavity_feedline_coupling", "") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe dictionary representation."""
        return {
            "qubit_representation": self.qubit_representation,
            "cavity_representation": self.cavity_representation,
            "feedline_representation": self.feedline_representation,
            "qubit_cavity_coupling": self.qubit_cavity_coupling,
            "cavity_feedline_coupling": self.cavity_feedline_coupling,
        }

    @property
    def has_structured_signature(self) -> bool:
        """Whether all key subsystem representation/coupling fields are set."""
        return bool(
            self.qubit_representation
            and self.cavity_representation
            and self.feedline_representation
            and self.qubit_cavity_coupling
            and self.cavity_feedline_coupling
        )


@dataclass
class SystemQubitSpec:
    """Compatibility input for constructing transmon components."""

    num_qubits: int = 1
    transmon_levels: int = 2
    qubit_freqs_Hz: list[float] = field(default_factory=list)
    qubit_omega_rad_s: list[float] = field(default_factory=list)
    lab_frame_qubit_freqs_Hz: list[float] = field(default_factory=list)
    lab_frame_qubit_omega_rad_s: list[float] = field(default_factory=list)
    anharmonicity_Hz: list[float] = field(default_factory=list)
    anharmonicity_rad_s: list[float] = field(default_factory=list)


@dataclass
class SystemCavitySpec:
    """Compatibility input for constructing a resonator component."""

    cavity_nmax: int = 0
    cavity_freq_Hz: float = 0.0
    cavity_omega_rad_s: float = 0.0


@dataclass
class SystemCouplingSummarySpec:
    """Compatibility input for constructing qubit-resonator couplings."""

    g_cavity_Hz: list[float] = field(default_factory=list)
    g_cavity_rad_s: list[float] = field(default_factory=list)


@dataclass
class SystemSpec:
    """Engine-neutral physical system description.

    The primary representation is ``components`` plus ``connections``. The
    qubit, cavity, and coupling init-only arguments are migration helpers that
    synthesize components when older code supplies compact summaries.
    """

    model_type: str = "qubit_network"
    simulation_level: str = "qubit"
    dimension: int = 2
    components: list[SystemComponentSpec] = field(default_factory=list)
    connections: list[SystemConnectionSpec] = field(default_factory=list)
    structure: ModelStructureSpec = field(default_factory=ModelStructureSpec)
    assumptions: dict[str, Any] = field(default_factory=dict)
    qubits: InitVar[SystemQubitSpec | dict[str, Any] | None] = None
    cavity: InitVar[SystemCavitySpec | dict[str, Any] | None] = None
    couplings: InitVar[SystemCouplingSummarySpec | dict[str, Any] | None] = None

    def __post_init__(
        self,
        qubits: SystemQubitSpec | dict[str, Any] | None,
        cavity: SystemCavitySpec | dict[str, Any] | None,
        couplings: SystemCouplingSummarySpec | dict[str, Any] | None,
    ) -> None:
        """Normalize component/connection dictionaries into typed specs."""
        self.components = [
            comp if isinstance(comp, SystemComponentSpec) else SystemComponentSpec.from_dict(comp)
            for comp in list(self.components or [])
        ]
        self.connections = [
            conn if isinstance(conn, SystemConnectionSpec) else SystemConnectionSpec.from_dict(conn)
            for conn in list(self.connections or [])
        ]
        if not isinstance(self.structure, ModelStructureSpec):
            self.structure = ModelStructureSpec.from_dict(self.structure)
        qubit_summary = _summary_obj(SystemQubitSpec, qubits)
        cavity_summary = _summary_obj(SystemCavitySpec, cavity)
        coupling_summary = _summary_obj(SystemCouplingSummarySpec, couplings)
        if not self.components:
            self.components.extend(_components_from_summaries(qubit_summary, cavity_summary))
        if not self.connections:
            self.connections.extend(_connections_from_summary(coupling_summary, len(_transmons(self.components))))

    @property
    def num_qubits(self) -> int:
        """Number of transmon components in the system."""
        return len(_transmons(self.components))

    @property
    def transmon_levels(self) -> int:
        """Maximum transmon truncation level across quantum components."""
        levels = [comp.levels for comp in _transmons(self.components)]
        return max(levels) if levels else 2

    @property
    def qubit_freqs_Hz(self) -> list[float]:
        """Per-transmon frequency list in Hz."""
        return [comp.freq_Hz for comp in _transmons(self.components)]

    @property
    def qubit_omega_rad_s(self) -> list[float]:
        """Per-transmon angular frequency list in rad/s."""
        return [comp.omega_rad_s for comp in _transmons(self.components)]

    @property
    def lab_frame_qubit_freqs_Hz(self) -> list[float]:
        """Compatibility alias for the component qubit frequencies in Hz."""
        return self.qubit_freqs_Hz

    @property
    def lab_frame_qubit_omega_rad_s(self) -> list[float]:
        """Compatibility alias for component qubit angular frequencies."""
        return self.qubit_omega_rad_s

    @property
    def anharmonicity_Hz(self) -> list[float]:
        """Per-transmon anharmonicity list in Hz."""
        return [comp.anharmonicity_Hz for comp in _transmons(self.components)]

    @property
    def anharmonicity_rad_s(self) -> list[float]:
        """Per-transmon anharmonicity list in rad/s."""
        return [comp.anharmonicity_rad_s for comp in _transmons(self.components)]

    @property
    def cavity_nmax(self) -> int:
        """Fock truncation for the first resonator component, if present."""
        cavity = _first_resonator(self.components)
        return cavity.nmax if cavity is not None else 0

    @property
    def cavity_freq_Hz(self) -> float:
        """Frequency of the first resonator component in Hz, if present."""
        cavity = _first_resonator(self.components)
        return cavity.freq_Hz if cavity is not None else 0.0

    @property
    def cavity_omega_rad_s(self) -> float:
        """Angular frequency of the first resonator component in rad/s."""
        cavity = _first_resonator(self.components)
        return cavity.omega_rad_s if cavity is not None else 0.0

    @property
    def g_cavity_Hz(self) -> list[float]:
        """Coupling strengths in Hz for supported coupling connections."""
        return [conn.g_Hz for conn in self.connections if isinstance(conn, (JCConnectionSpec, DispersiveConnectionSpec, ZZConnectionSpec))]

    @property
    def g_cavity_rad_s(self) -> list[float]:
        """Coupling strengths in rad/s for supported coupling connections."""
        return [conn.g_rad_s for conn in self.connections if isinstance(conn, (JCConnectionSpec, DispersiveConnectionSpec, ZZConnectionSpec))]


def _summary_obj(cls: type[Any], raw: Any) -> Any:
    if raw is None:
        return cls()
    return raw if isinstance(raw, cls) else _construct_dataclass(cls, dict(raw or {}))


def _transmons(components: list[SystemComponentSpec]) -> list[TransmonComponentSpec]:
    return [comp for comp in components if isinstance(comp, TransmonComponentSpec)]


def _first_resonator(components: list[SystemComponentSpec]) -> ResonatorComponentSpec | None:
    for comp in components:
        if isinstance(comp, ResonatorComponentSpec):
            return comp
    return None


def _components_from_summaries(qubits: SystemQubitSpec, cavity: SystemCavitySpec) -> list[SystemComponentSpec]:
    components: list[SystemComponentSpec] = []
    n = int(qubits.num_qubits or len(qubits.qubit_freqs_Hz) or 0)
    for idx in range(n):
        components.append(
            TransmonComponentSpec(
                id=f"q{idx}",
                levels=qubits.transmon_levels,
                freq_Hz=_list_value(qubits.qubit_freqs_Hz, idx),
                omega_rad_s=_list_value(qubits.qubit_omega_rad_s, idx),
                anharmonicity_Hz=_list_value(qubits.anharmonicity_Hz, idx),
                anharmonicity_rad_s=_list_value(qubits.anharmonicity_rad_s, idx),
            )
        )
    if cavity.cavity_nmax or cavity.cavity_freq_Hz or cavity.cavity_omega_rad_s:
        components.append(
            ResonatorComponentSpec(
                id="r0",
                type="resonator",
                nmax=cavity.cavity_nmax,
                freq_Hz=cavity.cavity_freq_Hz,
                omega_rad_s=cavity.cavity_omega_rad_s,
            )
        )
    return components


def _connections_from_summary(couplings: SystemCouplingSummarySpec, num_qubits: int) -> list[SystemConnectionSpec]:
    connections: list[SystemConnectionSpec] = []
    for idx, g_hz in enumerate(list(couplings.g_cavity_Hz or [])):
        if idx >= num_qubits:
            break
        connections.append(
            JCConnectionSpec(
                id=f"q{idx}_r0",
                a=f"q{idx}",
                b="r0",
                g_Hz=float(g_hz),
                g_rad_s=_list_value(couplings.g_cavity_rad_s, idx),
            )
        )
    return connections


def _list_value(values: list[float], idx: int) -> float:
    return float(values[idx]) if idx < len(values) else 0.0


__all__ = [
    "DispersiveConnectionSpec",
    "JCConnectionSpec",
    "ModelStructureSpec",
    "ReadoutFeedlineConnectionSpec",
    "ReadoutLineComponentSpec",
    "ResonatorComponentSpec",
    "SystemCavitySpec",
    "SystemComponentSpec",
    "SystemConnectionSpec",
    "SystemCouplingSummarySpec",
    "SystemQubitSpec",
    "SystemSpec",
    "TransmonComponentSpec",
    "ZZConnectionSpec",
    "system_component_from_dict",
    "system_connection_from_dict",
]
