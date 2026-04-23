import pytest
import math

from qsim.backend.model_build import DefaultModelBuilder
from qsim.common.schemas import ExecutableModel
from qsim.workflow.contracts import apply_composite_device_step_overrides, normalize_device_payload


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


def test_model_builder_collects_readout_controls():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})
    pulse_samples = {
        "RO_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 0.8, 0.0],
            "carrier_freq_Hz": [6.45e9],
            "carrier_phase_rad": [0.0],
        }
    }
    hw = {
        "components": [
            {
                "id": "q0",
                "type": "transmon",
                "representation": "quantum",
                "basis": {"kind": "nlevel", "levels": 3},
                "parameters": {"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8},
            },
            {
                "id": "r0",
                "type": "resonator",
                "representation": "quantum",
                "basis": {"kind": "fock", "nmax": 4},
                "parameters": {"freq_Hz": 6.45e9},
            },
        ],
        "connections": [{"id": "c0", "type": "jc", "a": "q0", "b": "r0", "parameters": {"g_Hz": 1.0e7}}],
        "simulation_level": "cqed",
    }

    spec = DefaultModelBuilder().build(executable, hw=hw, noise={}, pulse_samples=pulse_samples)

    assert spec.payload["model_type"] == "cqed_jc"
    assert len(spec.payload["readout_controls"]) == 1
    assert spec.payload["readout_controls"][0]["channel"] == "RO_0"
    assert spec.payload["readout_controls"][0]["carrier_freq_Hz"] == pytest.approx(6.45e9)


def test_model_builder_selects_cqed_dispersive_from_selected_step_structure():
    executable = ExecutableModel(solver="mcwf", metadata={"num_qubits": 1})
    pulse_samples = {
        "RO_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 0.6, 0.0],
            "carrier_freq_Hz": [6.45e9],
            "carrier_phase_rad": [0.0],
        }
    }
    hw = {
        "components": [
            {
                "id": "q0",
                "type": "transmon",
                "parameters": {"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8},
            },
            {
                "id": "r0",
                "type": "resonator",
                "parameters": {"freq_Hz": 6.45e9, "chi_Hz": -1.0e6},
            },
            {
                "id": "ro0",
                "type": "readout_line",
                "parameters": {"bandwidth_Hz": 8.0e6},
            },
        ],
        "connections": [
            {"id": "jc", "type": "jc", "a": "q0", "b": "r0", "parameters": {"g_Hz": 1.0e7}},
            {"id": "disp", "type": "dispersive", "a": "q0", "b": "r0", "parameters": {"g_Hz": 1.0e7, "chi_Hz": -1.0e6}},
            {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6}},
        ],
        "simulation_level": "cqed",
    }
    primary_step = {
        "name": "qqc_disp",
        "active_components": ["q0", "r0", "ro0"],
        "active_connections": ["disp", "feed"],
        "representations": {
            "q0": "quantum",
            "r0": "quantum",
            "ro0": "classical",
        },
        "bases": {
            "q0": {"kind": "nlevel", "levels": 3},
            "r0": {"kind": "fock", "nmax": 4},
        },
    }
    hw = normalize_device_payload(apply_composite_device_step_overrides(hw, primary_step))

    spec = DefaultModelBuilder().build(
        executable,
        hw=hw,
        noise={},
        pulse_samples=pulse_samples,
        study=[primary_step],
        primary_step=primary_step,
    )

    assert spec.payload["model_type"] == "cqed_dispersive"
    assert spec.payload["model_structure"]["qubit_cavity_coupling"] == "dispersive"
    assert spec.payload["model_structure"]["cavity_feedline_coupling"] == "input_output"


def test_model_builder_supports_cavity_classical_readout_with_zero_qubits():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 0})
    pulse_samples = {
        "RO_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 1.0, 0.0],
            "carrier_freq_Hz": [6.45e9],
            "carrier_phase_rad": [0.0],
        }
    }
    primary_step = {
        "name": "classical_readout",
        "active_components": ["r0", "ro0"],
        "active_connections": ["feed"],
        "representations": {"r0": "classical", "ro0": "classical"},
        "options": {"subsystem_model": "cavity_classical_readout"},
        "prep_state": {"label": "1", "sequence": []},
    }
    hw = {
        "components": [
            {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6, "kappa_ext_Hz": 4.5e6, "chi_Hz": -5.5e6}},
            {"id": "ro0", "type": "readout_line", "parameters": {"gain_dB": 42.0, "eta_chain": 0.8, "added_noise_photons": 2.0}},
        ],
        "connections": [{"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 4.5e6}}],
        "simulation_level": "cqed",
    }

    spec = DefaultModelBuilder().build(
        executable,
        hw=hw,
        noise={},
        pulse_samples=pulse_samples,
        study=[primary_step],
        primary_step=primary_step,
    )

    assert spec.payload["model_type"] == "cavity_classical_readout"
    assert spec.payload["num_qubits"] == 0
    assert spec.dimension == 1
    assert len(spec.payload["readout_controls"]) == 1
