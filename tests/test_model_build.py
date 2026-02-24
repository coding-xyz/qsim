from qsim.backend.model_build import DefaultModelBuilder
from qsim.common.schemas import ExecutableModel


def test_model_builder_generates_qubit_network_payload():
    executable = ExecutableModel(
        solver="me",
        metadata={"num_qubits": 2},
        h_terms=[{"type": "drive", "source": "pulse_ir"}],
        noise_terms=[{"type": "lindblad"}],
    )
    pulse_samples = {
        "XY0": {"t": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.0]},
        "Z1": {"t": [0.0, 1.0, 2.0], "y": [0.1, 0.2, 0.1]},
        "RO0": {"t": [0.0, 1.0, 2.0], "y": [0.0, 0.0, 0.0]},
    }
    hw = {"qubit_freqs_hz": [5.0e9, 5.1e9], "couplings": [{"i": 0, "j": 1, "g": 0.02}]}
    noise = {"gamma1": 0.001, "gamma_phi": 0.0005}

    spec = DefaultModelBuilder().build(executable, hw=hw, noise=noise, pulse_samples=pulse_samples)
    assert spec.payload["model_type"] == "qubit_network"
    assert spec.payload["num_qubits"] == 2
    assert len(spec.payload["controls"]) >= 2
    assert len(spec.payload["collapse_operators"]) == 4