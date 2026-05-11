"""Circuit-level intermediate representations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION


@dataclass
class CircuitGate:
    """One logical gate operation in circuit IR.

    Attributes:
        name: Name of the gate operation (e.g., "rx", "cx").
        qubits: List of target/control qubit indices.
        params: Numerical parameters for the gate (e.g., rotation angle).
        clbits: List of classical bit indices involved.
    """

    name: str
    qubits: list[int] = field(default_factory=list)
    params: list[float] = field(default_factory=list)
    clbits: list[int] = field(default_factory=list)


@dataclass
class CircuitIR:
    """Normalized circuit representation used by compile pipeline.

    Attributes:
        schema_version: Version of the circuit IR schema.
        format: Format of the circuit (e.g., "openqasm3"). Defaults to "openqasm3".
        num_qubits: Number of qubits in the circuit. Defaults to 0.
        num_clbits: Number of classical bits in the circuit. Defaults to 0.
        gates: Ordered list of gate operations.
        source_qasm: Original QASM source code string.
    """

    schema_version: str = SCHEMA_VERSION
    format: str = "openqasm3"
    num_qubits: int = 0
    num_clbits: int = 0
    gates: list[CircuitGate] = field(default_factory=list)
    source_qasm: str = ""


@dataclass
class CircuitSpec:
    """Circuit snapshot kept with ``ModelSpec`` for engines that need gate context.

    Attributes:
        schema_version: Version of the circuit spec schema.
        format: Format of the circuit (e.g., "openqasm3"). Defaults to "openqasm3".
        num_qubits: Number of qubits in the circuit. Defaults to 0.
        num_clbits: Number of classical bits in the circuit. Defaults to 0.
        gates: Ordered list of gate operations.
        source_qasm: Original QASM source code string.
        stage: Compilation stage of the snapshot (e.g., "normalized"). Defaults to "normalized".
    """

    schema_version: str = SCHEMA_VERSION
    format: str = "openqasm3"
    num_qubits: int = 0
    num_clbits: int = 0
    gates: list[CircuitGate] = field(default_factory=list)
    source_qasm: str = ""
    stage: str = "normalized"

    @classmethod
    def from_circuit_ir(cls, circuit: CircuitIR, *, stage: str = "normalized") -> "CircuitSpec":
        """Create a ``CircuitSpec`` snapshot from normalized ``CircuitIR``.

        Args:
            circuit (CircuitIR): The source circuit intermediate representation.
            stage (str): The compilation stage name. Defaults to "normalized".

        Returns:
            CircuitSpec: A snapshot of the circuit for model specification.
        """
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
        """Create a ``CircuitSpec`` from a JSON-style mapping.

        Args:
            data (dict[str, Any] | None): Input dictionary containing circuit fields.

        Returns:
            CircuitSpec: A typed circuit specification.
        """
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
        """Serialize the circuit snapshot to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A JSON-serializable representation of the circuit spec.
        """
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "num_qubits": self.num_qubits,
            "num_clbits": self.num_clbits,
            "gates": [asdict(gate) for gate in self.gates],
            "source_qasm": self.source_qasm,
            "stage": self.stage,
        }


