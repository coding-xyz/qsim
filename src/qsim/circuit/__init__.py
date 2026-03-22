"""Circuit public API.

The circuit package currently exposes helpers for importing, exporting, and
normalizing OpenQASM-based circuit descriptions. The primary public entrypoint
is ``CircuitAdapter``.
"""

from qsim.circuit.import_qasm import CircuitAdapter

__all__ = ["CircuitAdapter"]
