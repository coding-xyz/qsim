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
    """Subsystem structure selected from active components and connections.

    This spec defines how different physical subsystems are represented 
    (e.g., quantum vs classical) and how they are coupled.

    Attributes:
        qubit_representation: Representation mode for qubits. Defaults to "quantum".
        cavity_representation: Representation mode for resonators.
        feedline_representation: Representation mode for feedlines.
        qubit_cavity_coupling: Coupling model for qubit-cavity interaction.
        cavity_feedline_coupling: Coupling model for cavity-feedline interaction.
    """

    qubit_representation: str = "quantum"
    cavity_representation: str = ""
    feedline_representation: str = ""
    qubit_cavity_coupling: str = ""
    cavity_feedline_coupling: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ModelStructureSpec":
        """Construct a structure summary from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing structure fields.

        Returns:
            ModelStructureSpec: A typed structure specification.
        """
        raw = dict(data or {})
        return cls(
            qubit_representation=str(raw.get("qubit_representation", "quantum") or "quantum"),
            cavity_representation=str(raw.get("cavity_representation", "") or ""),
            feedline_representation=str(raw.get("feedline_representation", "") or ""),
            qubit_cavity_coupling=str(raw.get("qubit_cavity_coupling", "") or ""),
            cavity_feedline_coupling=str(raw.get("cavity_feedline_coupling", "") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe dictionary representation.

        Returns:
            dict[str, str]: A dictionary containing the structure fields.
        """
        return {
            "qubit_representation": self.qubit_representation,
            "cavity_representation": self.cavity_representation,
            "feedline_representation": self.feedline_representation,
            "qubit_cavity_coupling": self.qubit_cavity_coupling,
            "cavity_feedline_coupling": self.cavity_feedline_coupling,
        }

    @property
    def has_structured_signature(self) -> bool:
        """Whether all key subsystem representation/coupling fields are set.

        Returns:
            bool: True if all representation and coupling fields are non-empty.
        """
        return bool(
            self.qubit_representation
            and self.cavity_representation
            and self.feedline_representation
            and self.qubit_cavity_coupling
            and self.cavity_feedline_coupling
        )


@dataclass
class SystemQubitSpec:
    """Compatibility input for constructing transmon components.

    Used as a shorthand to synthesize multiple `TransmonComponentSpec` objects.

    Attributes:
        num_qubits: Total number of qubits to create. Defaults to 1.
        transmon_levels: Number of energy levels for each transmon. Defaults to 2.
        qubit_freqs_Hz: List of qubit frequencies in Hz.
        qubit_omega_rad_s: List of qubit angular frequencies in rad/s.
        lab_frame_qubit_freqs_Hz: Frequencies in the lab frame (Hz).
        lab_frame_qubit_omega_rad_s: Angular frequencies in the lab frame (rad/s).
        anharmonicity_Hz: List of anharmonicities in Hz.
        anharmonicity_rad_s: List of anharmonicities in rad/s.
    """

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
    """Compatibility input for constructing a resonator component.

    Attributes:
        cavity_nmax: Fock space truncation limit. Defaults to 0.
        cavity_freq_Hz: Resonator frequency in Hz. Defaults to 0.0.
        cavity_omega_rad_s: Resonator angular frequency in rad/s. Defaults to 0.0.
    """

    cavity_nmax: int = 0
    cavity_freq_Hz: float = 0.0
    cavity_omega_rad_s: float = 0.0


@dataclass
class SystemCouplingSummarySpec:
    """Compatibility input for constructing qubit-resonator couplings.

    Attributes:
        g_cavity_Hz: Coupling strengths in Hz.
        g_cavity_rad_s: Coupling strengths in rad/s.
    """

    g_cavity_Hz: list[float] = field(default_factory=list)
    g_cavity_rad_s: list[float] = field(default_factory=list)


@dataclass
class SystemSpec:
    """Engine-neutral physical system description.

    The primary representation is ``components`` plus ``connections``. The
    qubit, cavity, and coupling init-only arguments are migration helpers that
    synthesize components when older code supplies compact summaries.

    Attributes:
        model_type: Type of the physical model (e.g., "qubit_network"). Defaults to "qubit_network".
        simulation_level: Level of simulation (e.g., "qubit", "transmon"). Defaults to "qubit".
        dimension: Total Hilbert space dimension. Defaults to 2.
        components: List of all physical components (qubits, resonators, etc.).
        connections: List of all couplings/connections between components.
        structure: Metadata about the subsystem representation and coupling modes.
        assumptions: Map of physical assumptions used in the model.
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
        """Normalize component/connection dictionaries into typed specs.

        This method handles the conversion of shorthand summaries (qubits, cavity, couplings)
        into the canonical `components` and `connections` lists.
        """
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
        """Number of transmon components in the system.

        Returns:
            int: Count of `TransmonComponentSpec` objects.
        """
        return len(_transmons(self.components))

    @property
    def transmon_levels(self) -> int:
        """Maximum transmon truncation level across quantum components.

        Returns:
            int: The highest `levels` value among all transmons. Defaults to 2.
        """
        levels = [comp.levels for comp in _transmons(self.components)]
        return max(levels) if levels else 2

    @property
    def qubit_freqs_Hz(self) -> list[float]:
        """Per-transmon frequency list in Hz.

        Returns:
            list[float]: Frequencies of all transmon components.
        """
        return [comp.freq_Hz for comp in _transmons(self.components)]

    @property
    def qubit_omega_rad_s(self) -> list[float]:
        """Per-transmon angular frequency list in rad/s.

        Returns:
            list[float]: Angular frequencies of all transmon components.
        """
        return [comp.omega_rad_s for comp in _transmons(self.components)]

    @property
    def lab_frame_qubit_freqs_Hz(self) -> list[float]:
        """Compatibility alias for the component qubit frequencies in Hz.

        Returns:
            list[float]: The same list as `qubit_freqs_Hz`.
        """
        return self.qubit_freqs_Hz

    @property
    def lab_frame_qubit_omega_rad_s(self) -> list[float]:
        """Compatibility alias for component qubit angular frequencies.

        Returns:
            list[float]: The same list as `qubit_omega_rad_s`.
        """
        return self.qubit_omega_rad_s

    @property
    def anharmonicity_Hz(self) -> list[float]:
        """Per-transmon anharmonicity list in Hz.

        Returns:
            list[float]: Anharmonicities of all transmon components.
        """
        return [comp.anharmonicity_Hz for comp in _transmons(self.components)]

    @property
    def anharmonicity_rad_s(self) -> list[float]:
        """Per-transmon anharmonicity list in rad/s.

        Returns:
            list[float]: Angular anharmonicities of all transmon components.
        """
        return [comp.anharmonicity_rad_s for comp in _transmons(self.components)]

    @property
    def cavity_nmax(self) -> int:
        """Fock truncation for the first resonator component, if present.

        Returns:
            int: The `nmax` of the first `ResonatorComponentSpec` found. Defaults to 0.
        """
        cavity = _first_resonator(self.components)
        return cavity.nmax if cavity is not None else 0

    @property
    def cavity_freq_Hz(self) -> float:
        """Frequency of the first resonator component in Hz, if present.

        Returns:
            float: The `freq_Hz` of the first `ResonatorComponentSpec` found. Defaults to 0.0.
        """
        cavity = _first_resonator(self.components)
        return cavity.freq_Hz if cavity is not None else 0.0

    @property
    def cavity_omega_rad_s(self) -> float:
        """Angular frequency of the first resonator component in rad/s.

        Returns:
            float: The `omega_rad_s` of the first `ResonatorComponentSpec` found. Defaults to 0.0.
        """
        cavity = _first_resonator(self.components)
        return cavity.omega_rad_s if cavity is not None else 0.0

    @property
    def g_cavity_Hz(self) -> list[float]:
        """Coupling strengths in Hz for supported coupling connections.

        Returns:
            list[float]: Coupling strengths (g) for JC, Dispersive, and ZZ connections.
        """
        return [conn.g_Hz for conn in self.connections if isinstance(conn, (JCConnectionSpec, DispersiveConnectionSpec, ZZConnectionSpec))]

    @property
    def g_cavity_rad_s(self) -> list[float]:
        """Coupling strengths in rad/s for supported coupling connections.

        Returns:
            list[float]: Angular coupling strengths (g) for JC, Dispersive, and ZZ connections.
        """
        return [conn.g_rad_s for conn in self.connections if isinstance(conn, (JCConnectionSpec, DispersiveConnectionSpec, ZZConnectionSpec))]


def _summary_obj(cls: type[Any], raw: Any) -> Any:
    """Helper to ensure a value is a specific dataclass instance.

    Args:
        cls (type[Any]): The target dataclass type.
        raw (Any): The input value (None, dict, or instance).

    Returns:
        Any: An instance of `cls`.
    """
    if raw is None:
        return cls()
    return raw if isinstance(raw, cls) else _construct_dataclass(cls, dict(raw or {}))


def _transmons(components: list[SystemComponentSpec]) -> list[TransmonComponentSpec]:
    """Filter components to find only transmons.

    Args:
        components (list[SystemComponentSpec]): List of all system components.

    Returns:
        list[TransmonComponentSpec]: A list of all transmon components.
    """
    return [comp for comp in components if isinstance(comp, TransmonComponentSpec)]


def _first_resonator(components: list[SystemComponentSpec]) -> ResonatorComponentSpec | None:
    """Find the first resonator component in the list.

    Args:
        components (list[SystemComponentSpec]): List of all system components.

    Returns:
        ResonatorComponentSpec | None: The first found resonator or None.
    """
    for comp in components:
        if isinstance(comp, ResonatorComponentSpec):
            return comp
    return None


def _components_from_summaries(qubits: SystemQubitSpec, cavity: SystemCavitySpec) -> list[SystemComponentSpec]:
    """Synthesize a list of components from compact summary objects.

    Args:
        qubits (SystemQubitSpec): Qubit summary data.
        cavity (SystemCavitySpec): Cavity summary data.

    Returns:
        list[SystemComponentSpec]: A list of generated `TransmonComponentSpec` 
            and `ResonatorComponentSpec` objects.
    """
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
    """Synthesize a list of connections from a coupling summary.

    Args:
        couplings (SystemCouplingSummarySpec): Coupling summary data.
        num_qubits (int): Number of qubits to associate with couplings.

    Returns:
        list[SystemConnectionSpec]: A list of generated `JCConnectionSpec` objects.
    """
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
    """Safely retrieve a value from a list by index, defaulting to 0.0.

    Args:
        values (list[float]): The list of values.
        idx (int): The index to retrieve.

    Returns:
        float: The value at `idx` or 0.0 if index is out of bounds.
    """
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
