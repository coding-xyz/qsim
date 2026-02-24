from qsim.common.schemas import ModelSpec
from qsim.engines.qutip_engine import QuTiPEngine


def test_qutip_engine_handles_general_payload():
    spec = ModelSpec(
        solver="se",
        dimension=4,
        t_end=10.0,
        dt=1.0,
        payload={
            "model_type": "qubit_network",
            "num_qubits": 2,
            "qubit_freqs_hz": [0.0, 0.0],
            "couplings": [{"i": 0, "j": 1, "g": 0.01, "kind": "xx+yy"}],
            "controls": [
                {"target": 0, "axis": "x", "times": [0.0, 5.0, 10.0], "values": [0.0, 1.0, 0.0], "scale": 1.0},
                {"target": 1, "axis": "z", "times": [0.0, 10.0], "values": [0.0, 0.0], "scale": 1.0},
            ],
            "collapse_operators": [],
        },
    )
    trace = QuTiPEngine().run(spec)
    assert len(trace.times) > 0
    assert len(trace.states) == len(trace.times)
    assert len(trace.states[0]) >= 1