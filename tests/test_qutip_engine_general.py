import math

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
            "qubit_omega_rad_s": [0.0, 0.0],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "couplings": [{"i": 0, "j": 1, "g_rad_s": 0.01, "kind": "xx+yy"}],
            "controls": [
                {
                    "target": 0,
                    "axis": "x",
                    "times": [0.0, 5.0, 10.0],
                    "values": [0.0, 1.0, 0.0],
                    "scale": 1.0,
                    "carrier_omega_rad_s": 2.0 * math.pi * 5.0,
                    "carrier_phase_rad": 0.0,
                    "reference_omega_rad_s": 2.0 * math.pi * 5.0,
                    "drive_delta_rad_s": 0.0,
                },
                {"target": 1, "axis": "z", "times": [0.0, 10.0], "values": [0.0, 0.0], "scale": 1.0},
            ],
            "collapse_operators": [],
        },
    )
    trace = QuTiPEngine().run(spec)
    assert len(trace.times) > 0
    assert len(trace.states) == len(trace.times)
    assert len(trace.states[0]) >= 1


def test_qutip_engine_dephasing_prefactor_matches_model_convention():
    engine = QuTiPEngine()

    assert engine._dephasing_collapse_prefactor(8.0, "qubit_network") == 2.0
    assert engine._dephasing_collapse_prefactor(8.0, "transmon_nlevel") == 4.0


def test_qutip_relaxation_does_not_excite_ground_state():
    spec = ModelSpec(
        solver="me",
        dimension=2,
        t_end=2.0,
        dt=0.05,
        payload={
            "model_type": "qubit_network",
            "num_qubits": 1,
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [0.0],
            "controls": [],
            "collapse_operators": [{"target": 0, "kind": "relaxation", "rate_rad_s": 1.0}],
        },
    )
    trace = QuTiPEngine().run(spec)
    excited = [row[0] for row in trace.states]
    assert max(excited) < 1e-6
