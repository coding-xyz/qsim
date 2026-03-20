import pytest
import math

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
        "XY_0": {"t": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.0]},
        "Z_1": {"t": [0.0, 1.0, 2.0], "y": [0.1, 0.2, 0.1]},
        "RO_0": {"t": [0.0, 1.0, 2.0], "y": [0.0, 0.0, 0.0]},
    }
    hw = {"qubit_freqs_Hz": [5.0e9, 5.1e9], "couplings": [{"i": 0, "j": 1, "g_Hz": 0.02}]}
    noise = {"gamma1_Hz": 0.001, "gamma_phi_Hz": 0.0005}

    spec = DefaultModelBuilder().build(executable, hw=hw, noise=noise, pulse_samples=pulse_samples)
    assert spec.payload["model_type"] == "qubit_network"
    assert spec.payload["num_qubits"] == 2
    assert len(spec.payload["controls"]) >= 2
    assert len(spec.payload["collapse_operators"]) == 4


def test_model_builder_rejects_unknown_device_unit_keys():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    with pytest.raises(ValueError, match="Unsupported keys in device"):
        DefaultModelBuilder().build(
            executable,
            hw={"gate_duration": 20.0},
            noise={},
            pulse_samples={},
        )


def test_model_builder_rejects_unknown_noise_unit_keys():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    with pytest.raises(ValueError, match="Unsupported keys in noise"):
        DefaultModelBuilder().build(
            executable,
            hw={},
            noise={"T1_ms": 1.0},
            pulse_samples={},
        )


def test_model_builder_supports_explicit_frame_reference():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})
    pulse_samples = {
        "XY_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 1.0, 0.0],
            "carrier_freq_Hz": [5.05e9],
            "carrier_phase_rad": [0.0],
        }
    }
    hw = {"qubit_freqs_Hz": [5.1e9]}

    spec = DefaultModelBuilder().build(
        executable,
        hw=hw,
        noise={},
        pulse_samples=pulse_samples,
        frame={"mode": "rotating", "reference": "explicit", "qubit_reference_freqs_Hz": [5.0e9], "rwa": True},
    )

    assert spec.payload["frame"]["reference"] == "explicit"
    assert spec.payload["reference_freqs_Hz"] == [5.0e9]
    assert spec.payload["pulse_carrier_reference_freqs_Hz"] == [5.05e9]
    assert spec.payload["qubit_freqs_Hz"] == [1.0e8]
    assert spec.payload["qubit_omega_rad_s"] == pytest.approx([2.0 * math.pi * 1.0e8])
    assert spec.payload["controls"][0]["drive_detuning_Hz"] == 5.0e7
    assert spec.payload["controls"][0]["drive_delta_rad_s"] == pytest.approx(2.0 * math.pi * 5.0e7)


def test_model_builder_accepts_device_qubits_layout():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    spec = DefaultModelBuilder().build(
        executable,
        hw={"qubits": [{"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8, "T1_s": 1.2e-4, "T2_s": 9.0e-5}]},
        noise={},
        pulse_samples={},
    )

    assert spec.payload["lab_frame_qubit_freqs_Hz"] == [5.0e9]
    assert spec.payload["lab_frame_qubit_omega_rad_s"] == pytest.approx([2.0 * math.pi * 5.0e9])
    assert spec.payload["anharmonicity_Hz"] == [-2.0e8]
    assert spec.payload["anharmonicity_rad_s"] == pytest.approx([-2.0 * math.pi * 2.0e8])
    assert len(spec.payload["collapse_operators"]) == 2
    assert spec.payload["collapse_operators"][0]["rate_rad_s"] == pytest.approx(
        2.0 * math.pi * spec.payload["collapse_operators"][0]["rate_Hz"]
    )


def test_model_builder_uses_solver_timing_controls():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})
    pulse_samples = {
        "XY_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 1.0, 0.0],
        }
    }

    padded = DefaultModelBuilder().build(
        executable,
        hw={},
        noise={},
        pulse_samples=pulse_samples,
        solver_run={"dt_s": 5.0e-10, "t_padding_s": 1.0e-9},
    )
    assert padded.dt == pytest.approx(5.0e-10)
    assert padded.t_end == pytest.approx(3.0e-9)

    overridden = DefaultModelBuilder().build(
        executable,
        hw={},
        noise={},
        pulse_samples=pulse_samples,
        solver_run={"dt_s": 2.5e-10, "t_end_s": 4.0e-9},
    )
    assert overridden.dt == pytest.approx(2.5e-10)
    assert overridden.t_end == pytest.approx(4.0e-9)
