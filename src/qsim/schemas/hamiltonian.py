"""Hamiltonian and operator schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qsim.schemas.components import _dataclass_public_dict
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
class CouplingTermSpec:
    """Static coupling term in the engine-neutral Hamiltonian."""

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
        """Create a coupling term from current or legacy coupling keys."""
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
        """Serialize the coupling term to a JSON-safe dictionary."""
        data = _dataclass_public_dict(self)
        if self.operator is not None:
            data["operator"] = asdict(self.operator)
        return data


@dataclass
class HamiltonianSpec:
    """Engine-neutral Hamiltonian terms."""

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


