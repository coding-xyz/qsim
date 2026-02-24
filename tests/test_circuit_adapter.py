import pytest

from qsim.circuit.import_qasm import CircuitAdapter


def test_qasm3_parse_and_serialize_roundtrip():
    qasm = """
OPENQASM 3;
qubit[2] q;
bit[2] c;
h q[0];
rz(1.5708) q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""
    ir = CircuitAdapter.from_qasm(qasm)
    assert ir.num_qubits == 2
    assert ir.num_clbits == 2
    assert [g.name for g in ir.gates[:3]] == ["h", "rz", "cx"]

    qasm2 = CircuitAdapter.to_qasm(ir)
    ir2 = CircuitAdapter.from_qasm(qasm2)
    assert len(ir2.gates) == len(ir.gates)


def test_qasm3_requires_header():
    with pytest.raises(ValueError):
        CircuitAdapter.from_qasm("qubit[1] q; x q[0];")


def test_to_qiskit_if_available():
    qasm = """
OPENQASM 3;
qubit[1] q;
bit[1] c;
x q[0];
measure q[0] -> c[0];
"""
    ir = CircuitAdapter.from_qasm(qasm)
    try:
        qc = CircuitAdapter.to_qiskit(ir)
    except RuntimeError:
        pytest.skip("qiskit not installed")
    assert getattr(qc, "num_qubits") == 1
    assert getattr(qc, "num_clbits") == 1