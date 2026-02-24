from __future__ import annotations

from qsim.common.schemas import CircuitGate, CircuitIR


def normalize_circuit(circuit: CircuitIR) -> CircuitIR:
    """Normalize gate names and copy circuit into canonical representation."""
    gates = [CircuitGate(name=g.name.lower(), qubits=list(g.qubits), params=list(g.params), clbits=list(g.clbits)) for g in circuit.gates]
    return CircuitIR(
        schema_version=circuit.schema_version,
        format=circuit.format,
        num_qubits=circuit.num_qubits,
        num_clbits=circuit.num_clbits,
        gates=gates,
        source_qasm=circuit.source_qasm,
    )
