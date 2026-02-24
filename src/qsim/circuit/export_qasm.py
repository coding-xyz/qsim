from __future__ import annotations

from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import CircuitIR


def to_qasm(circuit: CircuitIR) -> str:
    """Export ``CircuitIR`` into OpenQASM 3 text."""
    return CircuitAdapter.to_qasm(circuit)
