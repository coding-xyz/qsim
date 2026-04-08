import copy
import math

import numpy as np
import pytest

from qsim.common.schemas import ModelSpec
from qsim.engines.qutip_engine import QuTiPEngine


def _population_series_from_quantum_payload(trajectory):
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    if density_matrix:
        return [float(max(0.0, 1.0 - snapshot[0][0].real)) for snapshot in density_matrix.get("snapshots", [])]
    if wave_function:
        return [float(max(0.0, 1.0 - abs(snapshot[0]) ** 2)) for snapshot in wave_function.get("snapshots", [])]
    return []


def test_qutip_engine_handles_general_payload():
    pytest.importorskip("qutip")
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
    Trajectory = QuTiPEngine().run(spec)
    assert len(Trajectory.times) > 0
    snapshots = list((Trajectory.density_matrix or Trajectory.wave_function or {}).get("snapshots", []) or [])
    assert snapshots
    assert len(snapshots) == len(Trajectory.times)


def test_qutip_engine_dephasing_prefactor_matches_model_convention():
    engine = QuTiPEngine()

    assert engine._dephasing_collapse_prefactor(8.0, "qubit_network") == 2.0
    assert engine._dephasing_collapse_prefactor(8.0, "transmon_nlevel") == 4.0


def test_qutip_relaxation_does_not_excite_ground_state():
    pytest.importorskip("qutip")
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
    Trajectory = QuTiPEngine().run(spec)
    excited = _population_series_from_quantum_payload(Trajectory)
    assert max(excited) < 1e-6


def test_qutip_engine_raises_when_dependency_missing(monkeypatch):
    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "qutip":
            raise ImportError("missing qutip")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    spec = ModelSpec(
        solver="se",
        dimension=2,
        t_end=1.0,
        dt=0.1,
        payload={"model_type": "qubit_network", "num_qubits": 1, "qubit_omega_rad_s": [0.0]},
    )

    with pytest.raises(RuntimeError, match="QuTiP dependency unavailable"):
        QuTiPEngine().run(spec)


def test_qutip_engine_raises_for_unsupported_model_type():
    pytest.importorskip("qutip")
    spec = ModelSpec(
        solver="se",
        dimension=2,
        t_end=1.0,
        dt=0.1,
        payload={"model_type": "unsupported_model", "num_qubits": 1},
    )

    with pytest.raises(ValueError, match="Unsupported model_type"):
        QuTiPEngine().run(spec)


def test_qutip_engine_cqed_readout_emits_readout_observables():
    pytest.importorskip("qutip")
    spec = ModelSpec(
        solver="se",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        payload={
            "model_type": "cqed_jc",
            "num_qubits": 1,
            "transmon_levels": 3,
            "cavity_nmax": 2,
            "cavity_omega_rad_s": 0.0,
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [0.0],
            "g_cavity_rad_s": [0.0],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [],
            "readout_controls": [
                {
                    "channel": "RO_0",
                    "kind": "readout",
                    "target": 0,
                    "times": [0.0, 2.5e-9, 5.0e-9],
                    "values": [0.0, 0.4, 0.0],
                    "scale": 1.0,
                    "carrier_freq_Hz": 6.45e9,
                    "carrier_omega_rad_s": 2.0 * math.pi * 6.45e9,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
        },
    )

    Trajectory = QuTiPEngine().run(spec)

    readout = dict(Trajectory.metadata.get("readout_observables", {}) or {})
    assert len(readout.get("times", [])) == len(Trajectory.times)
    assert len(readout.get("cavity_a", [])) == len(Trajectory.times)
    assert len(readout.get("cavity_n", [])) == len(Trajectory.times)
    assert len(readout.get("a_out", [])) == len(Trajectory.times)
    assert len(readout.get("measured_voltage", [])) == len(Trajectory.times)


def test_qutip_engine_mcwf_keeps_readout_shots_without_state_storage():
    pytest.importorskip("qutip")
    spec = ModelSpec(
        solver="mcwf",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        payload={
            "model_type": "cqed_jc",
            "num_qubits": 1,
            "transmon_levels": 3,
            "cavity_nmax": 2,
            "cavity_omega_rad_s": 0.0,
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [0.0],
            "g_cavity_rad_s": [0.0],
            "components": [
                {"id": "q0", "type": "transmon", "parameters": {"freq_Hz": 5.0e9}},
                {
                    "id": "r0",
                    "type": "resonator",
                    "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6, "kappa_ext_Hz": 7.0e6, "chi_Hz": -1.0e6},
                },
                {
                    "id": "ro0",
                    "type": "readout_line",
                    "representation": "classical",
                    "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0, "bandwidth_Hz": 8.0e6},
                },
            ],
            "connections": [
                {"id": "disp", "type": "dispersive", "a": "q0", "b": "r0", "parameters": {"chi_Hz": -1.0e6}},
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "bandwidth_Hz": 8.0e6}},
            ],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [],
            "readout_controls": [
                {
                    "channel": "RO_0",
                    "kind": "readout",
                    "target": 0,
                    "times": [0.0, 2.5e-9, 5.0e-9],
                    "values": [0.0, 0.4, 0.0],
                    "scale": 1.0,
                    "carrier_freq_Hz": 6.45e9,
                    "carrier_omega_rad_s": 2.0 * math.pi * 6.45e9,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
            "analyser": {"trajectory": {"quantum": "", "save_times": "none", "save_final_state": False}},
        },
    )

    Trajectory = QuTiPEngine().run(spec, run_options={"ntraj": 4, "seed": 7})

    assert "quantum_state_trajectory" not in Trajectory.metadata
    assert Trajectory.metadata.get("hybrid_update_mode") == "predictor_corrector"
    readout = dict(Trajectory.metadata.get("readout_observables", {}) or {})
    assert readout.get("feedback", {}).get("enabled") is True
    assert "sqrt(kappa_ext_rad_s)" in str(readout.get("equations", {}).get("a_out", ""))
    assert len(readout.get("shots", [])) == 4
    assert len(readout["shots"][0]["measured_voltage"]) == len(Trajectory.times)
    a_in = np.asarray(readout.get("a_in", []), dtype=float)
    a_out = np.asarray(readout.get("a_out", []), dtype=float)
    cavity_a = np.asarray(readout.get("cavity_a", []), dtype=float)
    sampled_drive = QuTiPEngine._sample_readout_drive(np.asarray(Trajectory.times, dtype=float), spec.payload["readout_controls"])
    sampled_pairs = np.asarray([[float(v.real), float(v.imag)] for v in sampled_drive], dtype=float)
    assert np.max(np.abs(a_in - sampled_pairs)) > 0.0
    coupling = QuTiPEngine._readout_coupling_prefactor(7.0e6)
    expected_a_out = a_in[:, 0] + 1j * a_in[:, 1] - coupling * (cavity_a[:, 0] + 1j * cavity_a[:, 1])
    actual_a_out = a_out[:, 0] + 1j * a_out[:, 1]
    assert np.allclose(actual_a_out, expected_a_out)


def test_qutip_engine_hybrid_readout_mode_can_switch_back_to_staggered():
    pytest.importorskip("qutip")
    payload = {
        "model_type": "cqed_jc",
        "num_qubits": 1,
        "transmon_levels": 3,
        "cavity_nmax": 2,
        "cavity_omega_rad_s": 0.0,
        "qubit_omega_rad_s": [0.0],
        "anharmonicity_rad_s": [0.0],
        "g_cavity_rad_s": [0.0],
        "components": [
            {"id": "q0", "type": "transmon", "parameters": {"freq_Hz": 5.0e9}},
            {
                "id": "r0",
                "type": "resonator",
                "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6, "kappa_ext_Hz": 7.0e6, "chi_Hz": -1.0e6},
            },
            {
                "id": "ro0",
                "type": "readout_line",
                "representation": "classical",
                "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0, "bandwidth_Hz": 8.0e6},
            },
        ],
        "connections": [
            {"id": "disp", "type": "dispersive", "a": "q0", "b": "r0", "parameters": {"chi_Hz": -1.0e6}},
            {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "bandwidth_Hz": 8.0e6}},
        ],
        "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
        "controls": [],
        "readout_controls": [
            {
                "channel": "RO_0",
                "kind": "readout",
                "target": 0,
                "times": [0.0, 2.5e-9, 5.0e-9],
                "values": [0.0, 0.4, 0.0],
                "scale": 1.0,
                "carrier_freq_Hz": 6.45e9,
                "carrier_omega_rad_s": 2.0 * math.pi * 6.45e9,
                "carrier_phase_rad": 0.0,
            }
        ],
        "collapse_operators": [],
        "analyser": {"trajectory": {"quantum": "", "save_times": "none", "save_final_state": False}},
    }
    predictor_trace = QuTiPEngine().run(
        ModelSpec(solver="mcwf", dimension=9, t_end=5.0e-9, dt=1.0e-9, payload=copy.deepcopy(payload)),
        run_options={"ntraj": 4, "seed": 7},
    )

    staggered_payload = copy.deepcopy(payload)
    staggered_payload["primary_step"] = {"options": {"hybrid_readout_update": "staggered"}}
    staggered_trace = QuTiPEngine().run(
        ModelSpec(solver="mcwf", dimension=9, t_end=5.0e-9, dt=1.0e-9, payload=staggered_payload),
        run_options={"ntraj": 4, "seed": 7},
    )

    assert predictor_trace.metadata.get("hybrid_update_mode") == "predictor_corrector"
    assert staggered_trace.metadata.get("hybrid_update_mode") == "staggered"
    predictor_a_in = np.asarray(predictor_trace.metadata["readout_observables"]["a_in"], dtype=float)
    staggered_a_in = np.asarray(staggered_trace.metadata["readout_observables"]["a_in"], dtype=float)
    assert np.max(np.abs(predictor_a_in - staggered_a_in)) > 0.0


def test_qutip_engine_supports_cqed_dispersive_with_classical_feedline():
    pytest.importorskip("qutip")
    spec = ModelSpec(
        solver="mcwf",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        payload={
            "model_type": "cqed_dispersive",
            "num_qubits": 1,
            "transmon_levels": 3,
            "cavity_nmax": 2,
            "cavity_omega_rad_s": 0.0,
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [0.0],
            "g_cavity_rad_s": [2.0 * math.pi * 9.0e7],
            "components": [
                {"id": "q0", "type": "transmon", "representation": "quantum", "parameters": {"freq_Hz": 5.0e9}},
                {
                    "id": "r0",
                    "type": "resonator",
                    "representation": "quantum",
                    "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6, "kappa_ext_Hz": 7.0e6, "chi_Hz": -1.0e6},
                },
                {
                    "id": "ro0",
                    "type": "readout_line",
                    "representation": "classical",
                    "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0, "bandwidth_Hz": 8.0e6},
                },
            ],
            "connections": [
                {"id": "disp", "type": "dispersive", "a": "q0", "b": "r0", "parameters": {"chi_Hz": -1.0e6}},
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "bandwidth_Hz": 8.0e6}},
            ],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [],
            "readout_controls": [
                {
                    "channel": "RO_0",
                    "kind": "readout",
                    "target": 0,
                    "times": [0.0, 2.5e-9, 5.0e-9],
                    "values": [0.0, 0.4, 0.0],
                    "scale": 1.0,
                    "carrier_freq_Hz": 6.45e9,
                    "carrier_omega_rad_s": 2.0 * math.pi * 6.45e9,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
            "analyser": {"trajectory": {"quantum": "", "save_times": "none", "save_final_state": False}},
        },
    )

    Trajectory = QuTiPEngine().run(spec, run_options={"ntraj": 4, "seed": 9})

    assert Trajectory.metadata.get("model_type") == "cqed_dispersive"
    readout = dict(Trajectory.metadata.get("readout_observables", {}) or {})
    assert len(readout.get("shots", [])) == 4
    assert len(readout.get("a_out", [])) == len(Trajectory.times)
    assert len(readout.get("measured_voltage", [])) == len(Trajectory.times)


