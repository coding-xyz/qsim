"""Hamiltonian and operator schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qsim.schemas.components import _dataclass_public_dict
@dataclass
class OperatorRef:
    """Symbolic operator reference before backend-specific lowering.

    Attributes:
        name: Name of the operator (e.g., "sigma_x", "a_plus").
        target: Integer index of the target qubit/subsystem.
        target_pair: List of indices for two-body operators.
        scope: Domain of the operator (e.g., "system", "drive"). Defaults to "system".
    """

    name: str
    target: int | None = None
    target_pair: list[int] | None = None
    scope: str = "system"


@dataclass
class CarrierSpec:
    """Carrier metadata attached to a sampled signal.

    Attributes:
        freq_Hz: Carrier frequency in Hz. Defaults to 0.0.
        omega_rad_s: Carrier angular frequency in rad/s. Defaults to 0.0.
        phase_rad: Carrier phase in radians. Defaults to 0.0.
    """

    freq_Hz: float = 0.0
    omega_rad_s: float = 0.0
    phase_rad: float = 0.0


@dataclass
class SignalSpec:
    """Sampled or analytic coefficient signal for time-dependent terms.

    Attributes:
        kind: Type of signal (e.g., "sampled", "analytic"). Defaults to "sampled".
        unit: Unit of the signal values. Defaults to "".
        times_s: Time grid for the signal in seconds.
        values: Numerical coefficients at each time point.
        interpolation: Interpolation method (e.g., "linear", "cubic"). Defaults to "linear".
        scale: Global scaling factor for the signal. Defaults to 1.0.
        carrier: Optional carrier metadata for modulated signals.
        metadata: Non-primary technical annotations.
    """

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
    """Static Hamiltonian term.

    Attributes:
        operator: The operator associated with this term.
        coefficient: Numerical strength of the term. Defaults to 1.0.
        unit: Unit of the coefficient (e.g., "rad_per_s"). Defaults to "rad_per_s".
        kind: Category of the term (e.g., "static"). Defaults to "static".
        metadata: Non-primary technical annotations.
    """

    operator: OperatorRef
    coefficient: float = 1.0
    unit: str = "rad_per_s"
    kind: str = "static"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeDependentHamiltonianTerm:
    """Time-dependent Hamiltonian term driven by a signal.

    Attributes:
        operator: The operator associated with this term.
        coefficient: The time-varying signal coefficient.
        kind: Category of the term (e.g., "control", "readout"). Defaults to "control".
        metadata: Non-primary technical annotations.
    """

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
    """Convert a sampled control/readout-drive dictionary into a Hamiltonian term.

    Args:
        ctrl (dict[str, Any]): Input dictionary containing control parameters.
        kind (str): Category of the resulting term (e.g., "control", "readout_drive").

    Returns:
        TimeDependentHamiltonianTerm: A typed Hamiltonian term with signal coefficients.
    """
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
class CouplingTermSpec:
    """Static coupling term in the engine-neutral Hamiltonian.

    Attributes:
        id: Unique identifier for the coupling. Defaults to "".
        kind: Type of coupling (e.g., "xx+yy", "zz"). Defaults to "xx+yy".
        i: Index of the first connected subsystem. Defaults to 0.
        j: Index of the second connected subsystem. Defaults to 1.
        a: Identifier of the first component. Defaults to "".
        b: Identifier of the second component. Defaults to "".
        via: Identifier of the mediator component (if any). Defaults to "".
        operator: Symbolic operator reference.
        coefficient_Hz: Coupling strength in Hz. Defaults to 0.0.
        coefficient_rad_s: Coupling strength in rad/s. Defaults to 0.0.
    """

    id: str = ""
    kind: str = "xx+yy"
    i: int = 0
    j: int = 1
    a: str = ""
    b: str = ""
    via: str = ""
    operator: OperatorRef | None = None
    coefficient_Hz: float = 0.0
    coefficient_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CouplingTermSpec":
        """Create a coupling term from current or legacy coupling keys.

        Args:
            data (dict[str, Any] | None): Input dictionary.

        Returns:
            CouplingTermSpec: A typed coupling term specification.
        """
        raw = dict(data or {})
        g_hz = float(raw.get("coefficient_Hz", raw.get("g_Hz", 0.0)) or 0.0)
        g_rad_s = float(raw.get("coefficient_rad_s", raw.get("g_rad_s", raw.get("g", 0.0))) or 0.0)
        operator_raw = raw.get("operator")
        operator = None
        if isinstance(operator_raw, OperatorRef):
            operator = operator_raw
        elif isinstance(operator_raw, dict):
            operator = OperatorRef(
                name=str(operator_raw.get("name", "") or ""),
                target=operator_raw.get("target"),
                target_pair=list(operator_raw.get("target_pair", []) or []) or None,
                scope=str(operator_raw.get("scope", "system") or "system"),
            )
        return cls(
            id=str(raw.get("id", "") or ""),
            kind=str(raw.get("kind", "xx+yy") or "xx+yy"),
            i=int(raw.get("i", 0) or 0),
            j=int(raw.get("j", 1) or 1),
            a=str(raw.get("a", "") or ""),
            b=str(raw.get("b", "") or ""),
            via=str(raw.get("via", "") or ""),
            operator=operator,
            coefficient_Hz=g_hz,
            coefficient_rad_s=g_rad_s,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the coupling term to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A JSON-serializable representation of the coupling.
        """
        data = _dataclass_public_dict(self)
        if self.operator is not None:
            data["operator"] = asdict(self.operator)
        return data


@dataclass
class HamiltonianSpec:
    """Engine-neutral Hamiltonian terms.

    The `HamiltonianSpec` aggregates all terms that define the system's 
    energy landscape, including static internal terms, couplings, and 
    time-dependent external drives.

    Attributes:
        static_terms: List of constant energy terms.
        coupling_terms: List of fixed interactions between subsystems.
        control_terms: List of time-dependent terms for system control.
        readout_drive_terms: List of time-dependent terms for readout.
    """

    static_terms: list[HamiltonianTerm] = field(default_factory=list)
    coupling_terms: list[CouplingTermSpec] = field(default_factory=list)
    control_terms: list[TimeDependentHamiltonianTerm] = field(default_factory=list)
    readout_drive_terms: list[TimeDependentHamiltonianTerm] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize coupling dictionaries into ``CouplingTermSpec`` objects."""
        self.coupling_terms = [
            term if isinstance(term, CouplingTermSpec) else CouplingTermSpec.from_dict(term)
            for term in list(self.coupling_terms or [])
        ]


