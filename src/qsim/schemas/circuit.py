"""Circuit-level intermediate representations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION


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
        """Create a ``CircuitSpec`` snapshot from normalized ``CircuitIR``."""
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
        """Create a ``CircuitSpec`` from a JSON-style mapping."""
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
        """Serialize the circuit snapshot to a JSON-safe dictionary."""
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "num_qubits": self.num_qubits,
            "num_clbits": self.num_clbits,
            "gates": [asdict(gate) for gate in self.gates],
            "source_qasm": self.source_qasm,
            "stage": self.stage,
        }


