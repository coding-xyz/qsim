import pytest
import math

from qsim.backend.config import normalize_model_build_config
from qsim.backend.model.build import DefaultModelBuilder
from qsim.common.schemas import CircuitGate, CircuitIR, ExecutableModel
from qsim.workflow.contracts import apply_composite_device_step_overrides, normalize_device_payload


def test_model_build_config_normalizes_raw_yaml_payloads():
    cfg = normalize_model_build_config(
        device={"simulation_level": "bad", "control_scale": "2.5", "couplings": [{"i": 0, "j": 1, "g_Hz": 1.0}]},
        noise={"model": "1/f"},
        solver_run={"dt_s": "1e-9", "t_padding_s": "-1e-9"},
        frame={"reference": "carrier", "qubit_reference_freqs_Hz": ["5e9"]},
        analyser={"trajectory": {"quantum": "density_matrix"}},
        study=[{"name": "s0"}],
        primary_step={"name": "s0", "options": {"readout_protocol": "homodyne"}},
    )

    assert cfg.device.simulation_level == "qubit"
    assert cfg.device.control_scale == pytest.approx(2.5)
    assert cfg.noise.model == "one_over_f"
    assert cfg.solver.dt_s == pytest.approx(1e-9)
    assert cfg.solver.t_padding_s == 0.0
    assert cfg.frame.reference == "pulse_carrier"
    assert cfg.frame.qubit_reference_freqs_Hz == [5.0e9]
    assert cfg.study.primary_step["name"] == "s0"
    assert cfg.analysis.trajectory["quantum"] == "density_matrix"


def test_model_builder_generates_qubit_network_model_spec():
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
    assert spec.system.model_type == "qubit_network"
    assert spec.system.num_qubits == 2
    assert len(spec.hamiltonian.control_terms) >= 2
    assert len(spec.noise.collapse_channels) == 4


def test_model_builder_preserves_normalized_circuit_snapshot():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})
    circuit = CircuitIR(
        num_qubits=1,
        num_clbits=1,
        gates=[CircuitGate(name="x", qubits=[0]), CircuitGate(name="measure", qubits=[0], clbits=[0])],
        source_qasm="OPENQASM 3.0;",
    )

    spec = DefaultModelBuilder().build(executable, hw={}, noise={}, pulse_samples={}, circuit=circuit)

    assert spec.circuit is not None
    assert spec.circuit.stage == "normalized"
    assert spec.circuit.num_qubits == 1
    assert [gate.name for gate in spec.circuit.gates] == ["x", "measure"]


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

    assert spec.frame.reference == "explicit"
    assert spec.frame.qubit_reference_freqs_Hz == [5.0e9]
    assert spec.frame.pulse_carrier_reference_freqs_Hz == [5.05e9]
    assert spec.system.qubit_freqs_Hz == [1.0e8]
    assert spec.system.qubit_omega_rad_s == pytest.approx([2.0 * math.pi * 1.0e8])
    assert spec.hamiltonian.control_terms[0].metadata["drive_detuning_Hz"] == 5.0e7
    assert spec.hamiltonian.control_terms[0].metadata["drive_delta_rad_s"] == pytest.approx(2.0 * math.pi * 5.0e7)


def test_model_builder_accepts_device_qubits_layout():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    spec = DefaultModelBuilder().build(
        executable,
        hw={"qubits": [{"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8, "T1_s": 1.2e-4, "T2_s": 9.0e-5}]},
        noise={},
        pulse_samples={},
    )

    assert spec.system.lab_frame_qubit_freqs_Hz == [5.0e9]
    assert spec.system.lab_frame_qubit_omega_rad_s == pytest.approx([2.0 * math.pi * 5.0e9])
    assert spec.system.anharmonicity_Hz == [-2.0e8]
    assert spec.system.anharmonicity_rad_s == pytest.approx([-2.0 * math.pi * 2.0e8])
    assert len(spec.noise.collapse_channels) == 2
    assert spec.noise.collapse_channels[0].rate_rad_s == pytest.approx(
        2.0 * math.pi * spec.noise.collapse_channels[0].rate_Hz
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


def test_model_builder_lowers_source_level_noise_and_crosstalk_schema():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 2})
    hw = {
        "components": [
            {
                "id": "q0",
                "type": "transmon",
                "parameters": {"freq_Hz": 5.0e9},
                "noise": [
                    {
                        "id": "q0_T1",
                        "kind": "markovian",
                        "operator": "lowering",
                        "rate": {"T1_s": 25.0e-6},
                    }
                ],
            },
            {"id": "q1", "type": "transmon", "parameters": {"freq_Hz": 5.1e9}},
        ],
        "shared_noise": [
            {
                "id": "shared_flux_bias",
                "kind": "one_over_f",
                "targets": ["q0", "q1"],
                "operator": "sigma_z_over_2",
                "amplitude": {"rms_Hz": 2.0e4, "definition": "integrated_rms_over_band"},
                "band_Hz": [10.0, 1.0e6],
                "exponent": 1.0,
                "psd_convention": "one_sided",
                "correlation": {"type": "shared"},
            }
        ],
        "control_crosstalk": [
            {
                "id": "drive_leakage_q0_to_q1",
                "kind": "deterministic_control_transfer",
                "source_channel": "XY_0",
                "target_channel": "XY_1",
                "transfer": {"amplitude": 0.02, "phase_rad": 0.1},
            }
        ],
        "readout_crosstalk": [
            {
                "id": "ro_q0_to_q1_assignment",
                "kind": "assignment_crosstalk",
                "source": "q0",
                "target": "q1",
                "probability": {"p_target_flip_when_source_excited": 0.03},
            }
        ],
    }
    noise = {"overrides": {"shared_flux_bias": {"amplitude": {"rms_Hz": 5.0e4}}}}

    pulse_samples = {
        "XY_0": {
            "t": [0.0, 1.0e-9, 2.0e-9],
            "y": [0.0, 1.0, 0.0],
            "carrier_freq_Hz": [5.0e9],
            "carrier_phase_rad": [0.0],
        }
    }

    spec = DefaultModelBuilder().build(executable, hw=hw, noise=noise, pulse_samples=pulse_samples)

    assert [source.id for source in spec.noise.sources] == ["q0_T1", "shared_flux_bias"]
    assert len(spec.noise.collapse_channels) == 1
    assert spec.noise.collapse_channels[0].kind == "relaxation"
    colored = [item for item in spec.noise.stochastic_channels if item.id == "shared_flux_bias"][0]
    assert colored.kind == "one_over_f"
    assert colored.targets == [0, 1]
    assert colored.one_over_f_amp_Hz == pytest.approx(5.0e4)
    assert colored.one_over_f_amp_rad_s == pytest.approx(2.0 * math.pi * 5.0e4)
    assert spec.noise.control_crosstalk[0].target_channel == "XY_1"
    assert spec.noise.readout_crosstalk[0].kind == "assignment_crosstalk"
    leaked = [term for term in spec.hamiltonian.control_terms if term.coefficient.metadata.get("channel") == "XY_1"][0]
    assert leaked.operator.target == 1
    assert leaked.coefficient.values == pytest.approx([0.0, 0.02, 0.0])
    assert leaked.coefficient.carrier.phase_rad == pytest.approx(0.1)
    assert any(item["kind"] == "control_crosstalk_transfers" for item in spec.noise.realizations)
    assert any(item["kind"] == "readout_crosstalk" for item in spec.noise.realizations)


def test_workflow_normalizes_composite_device_with_authored_component_noise_sources():
    hw = {
        "components": [
            {
                "id": "q0",
                "type": "transmon",
                "parameters": {"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8},
                "noise": [
                    {
                        "id": "q0_T1",
                        "kind": "markovian",
                        "operator": "lowering",
                        "rate": {"T1_s": 25.0e-6},
                    },
                    {
                        "id": "q0_flux_1overf",
                        "kind": "one_over_f",
                        "operator": "sigma_z_over_2",
                        "amplitude": {"rms_Hz": 4.0e4},
                        "band_Hz": [5.0e3, 8.0e5],
                    },
                ],
            }
        ],
        "connections": [],
        "simulation_level": "qubit",
    }

    normalized = normalize_device_payload(hw)

    assert normalized["qubits"][0]["freq_Hz"] == pytest.approx(5.0e9)
    assert normalized["components"][0]["noise"][1]["id"] == "q0_flux_1overf"


def test_model_builder_rejects_unknown_noise_source_override():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    with pytest.raises(ValueError, match="unknown source id"):
        DefaultModelBuilder().build(
            executable,
            hw={"components": [{"id": "q0", "type": "transmon", "parameters": {"freq_Hz": 5.0e9}}]},
            noise={"overrides": {"missing": {"amplitude": {"rms_Hz": 1.0}}}},
            pulse_samples={},
        )


def test_model_builder_accepts_top_level_noise_source_list_shorthand():
    executable = ExecutableModel(solver="me", metadata={"num_qubits": 1})

    spec = DefaultModelBuilder().build(
        executable,
        hw={"components": [{"id": "q0", "type": "transmon", "parameters": {"freq_Hz": 5.0e9}}]},
        noise=[
            {
                "id": "q0_T1_task",
                "kind": "markovian",
                "targets": ["q0"],
                "operator": "lowering",
                "rate": {"T1_s": 20.0e-6},
            }
        ],
        pulse_samples={},
    )

    assert [source.id for source in spec.noise.sources] == ["q0_T1_task"]
    assert len(spec.noise.collapse_channels) == 1
    assert spec.noise.collapse_channels[0].target == 0


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

    assert spec.system.model_type == "cqed_jc"
    assert spec.readout is not None
    assert len(spec.readout.controls) == 1
    assert spec.readout.controls[0].channel == "RO_0"
    assert spec.readout.controls[0].carrier_freq_Hz == pytest.approx(6.45e9)


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

    assert spec.system.model_type == "cqed_dispersive"
    assert spec.system.structure.qubit_cavity_coupling == "dispersive"
    assert spec.system.structure.cavity_feedline_coupling == "input_output"
    assert spec.readout is not None
    assert spec.readout.chain.kappa_ext_Hz == pytest.approx(7.0e6)
    assert spec.readout.chain.chi_Hz == pytest.approx([-1.0e6])


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

    assert spec.system.model_type == "cavity_classical_readout"
    assert spec.system.num_qubits == 0
    assert spec.dimension == 1
    assert spec.readout is not None
    assert len(spec.readout.controls) == 1
    assert spec.readout.chain.kappa_ext_Hz == pytest.approx(4.5e6)
    assert spec.readout.chain.chi_Hz == pytest.approx(-5.5e6)
