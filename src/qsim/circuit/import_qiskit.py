"""Qiskit bridge helpers for CircuitIR conversion."""

from __future__ import annotations

from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import CircuitIR


def from_qiskit(qc: object) -> CircuitIR:
    """Convert Qiskit ``QuantumCircuit`` to ``CircuitIR``."""
    return CircuitAdapter.from_qiskit(qc)


def to_qiskit(circuit: CircuitIR) -> object:
    """Convert ``CircuitIR`` to Qiskit ``QuantumCircuit``."""
    return CircuitAdapter.to_qiskit(circuit)
