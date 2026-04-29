import copy
import math

import numpy as np
import pytest

from qsim.common.schemas import model_spec_from_runtime_dict
from qsim.engines.qutip import QuTiPEngine


def _spec(*, solver="se", dimension=2, t_end=0.0, dt=1.0, model=None):
    return model_spec_from_runtime_dict(
        solver=solver,
        dimension=dimension,
        t_end=t_end,
        dt=dt,
        model=dict(model or {}),
    )


def _with_solver_run(spec, *, ntraj: int, seed: int):
    spec.solver.ntraj = int(ntraj)
    spec.solver.seed = int(seed)
    return spec


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
    spec = _spec(
        solver="se",
        dimension=4,
        t_end=10.0,
        dt=1.0,
        model={
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


def test_qutip_engine_resolves_photon_counting_readout_protocol_aliases():
    for alias in ["photon_counting", "photon-counting", "photon_counting_sme", "photocurrent"]:
        payload = {"primary_step": {"options": {"readout_protocol": alias}}}
        assert QuTiPEngine._resolve_readout_protocol(payload) == "photon_counting_sme"


def test_qutip_relaxation_does_not_excite_ground_state():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="me",
        dimension=2,
        t_end=2.0,
        dt=0.05,
        model={
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

    spec = _spec(
        solver="se",
        dimension=2,
        t_end=1.0,
        dt=0.1,
        model={"model_type": "qubit_network", "num_qubits": 1, "qubit_omega_rad_s": [0.0]},
    )

    with pytest.raises(RuntimeError, match="QuTiP dependency unavailable"):
        QuTiPEngine().run(spec)


def test_qutip_engine_raises_for_unsupported_model_type():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="se",
        dimension=2,
        t_end=1.0,
        dt=0.1,
        model={"model_type": "unsupported_model", "num_qubits": 1},
    )

    with pytest.raises(ValueError, match="Unsupported model_type"):
        QuTiPEngine().run(spec)


def test_qutip_engine_cqed_readout_emits_readout_observables():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="se",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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
    spec = _spec(
        solver="mcwf",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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

    Trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=4, seed=7))

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
    sampled_drive = QuTiPEngine._sample_readout_drive(np.asarray(Trajectory.times, dtype=float), list(spec.readout.controls if spec.readout else []))
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
        _with_solver_run(
            _spec(solver="mcwf", dimension=9, t_end=5.0e-9, dt=1.0e-9, model=copy.deepcopy(payload)),
            ntraj=4,
            seed=7,
        ),
    )

    staggered_payload = copy.deepcopy(payload)
    staggered_payload["primary_step"] = {"options": {"hybrid_readout_update": "staggered"}}
    staggered_trace = QuTiPEngine().run(
        _with_solver_run(
            _spec(solver="mcwf", dimension=9, t_end=5.0e-9, dt=1.0e-9, model=staggered_payload),
            ntraj=4,
            seed=7,
        ),
    )

    assert predictor_trace.metadata.get("hybrid_update_mode") == "predictor_corrector"
    assert staggered_trace.metadata.get("hybrid_update_mode") == "staggered"
    predictor_a_in = np.asarray(predictor_trace.metadata["readout_observables"]["a_in"], dtype=float)
    staggered_a_in = np.asarray(staggered_trace.metadata["readout_observables"]["a_in"], dtype=float)
    assert np.max(np.abs(predictor_a_in - staggered_a_in)) > 0.0


def test_qutip_engine_supports_cqed_dispersive_with_classical_feedline():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="mcwf",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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

    Trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=4, seed=9))

    assert Trajectory.metadata.get("model_type") == "cqed_dispersive"
    readout = dict(Trajectory.metadata.get("readout_observables", {}) or {})
    assert len(readout.get("shots", [])) == 4
    assert len(readout.get("a_out", [])) == len(Trajectory.times)
    assert len(readout.get("measured_voltage", [])) == len(Trajectory.times)


def test_qutip_engine_supports_homodyne_sme_without_line_state_feedback():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="me",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "eta_chain": 0.35, "bandwidth_Hz": 8.0e6}},
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
            "primary_step": {"options": {"readout_protocol": "homodyne_sme"}},
            "analyser": {"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}},
        },
    )

    Trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=4, seed=11))

    assert Trajectory.metadata.get("solver_impl") == "smesolve"
    assert len((Trajectory.density_matrix or {}).get("snapshots", [])) == len(Trajectory.times)
    readout = dict(Trajectory.classical.get("readout", {}) or {})
    assert readout.get("feedback", {}).get("enabled") is False
    assert "line_state" not in readout
    assert len(readout.get("shots", [])) == 4
    assert len(readout.get("measured_voltage", [])) == len(Trajectory.times)
    cavity_a = np.asarray(readout.get("cavity_a", []), dtype=float)
    assert cavity_a.size > 0
    assert float(np.max(np.abs(cavity_a))) > 0.0
    basis = dict(Trajectory.classical.get("basis_population", {}) or {})
    assert len(basis.get("values", [])) == len(Trajectory.times)
    assert len((Trajectory.measurements or {}).get("records", [])) == 4


def test_qutip_engine_supports_heterodyne_sme_with_iq_records():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="me",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "eta_chain": 0.35, "bandwidth_Hz": 8.0e6}},
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
            "primary_step": {"options": {"readout_protocol": "heterodyne_sme"}},
            "analyser": {"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}},
        },
    )

    Trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=4, seed=13))

    assert Trajectory.metadata.get("solver_impl") == "smesolve"
    assert Trajectory.metadata.get("readout_protocol") == "heterodyne_sme"
    readout = dict(Trajectory.classical.get("readout", {}) or {})
    assert readout.get("feedback", {}).get("enabled") is False
    assert len(readout.get("shots", [])) == 4
    assert len(readout.get("measured_voltage", [])) == len(Trajectory.times)
    assert len(readout.get("heterodyne_current", [])) == len(Trajectory.times)
    shot0 = dict(readout.get("shots", [])[0] or {})
    assert len(shot0.get("heterodyne_I", [])) == len(Trajectory.times)
    assert len(shot0.get("heterodyne_Q", [])) == len(Trajectory.times)
    current = np.asarray(readout.get("heterodyne_current", []), dtype=float)
    assert current.size > 0
    assert float(np.max(np.abs(current))) > 0.0
    records = list((Trajectory.measurements or {}).get("records", []) or [])
    assert len(records) == 4
    assert len(records[0].get("heterodyne_I", [])) == len(Trajectory.times)


def test_qutip_engine_supports_photon_counting_sme_with_count_records():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="me",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "eta_chain": 0.35, "bandwidth_Hz": 8.0e6}},
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
            "primary_step": {"options": {"readout_protocol": "photon_counting_sme"}},
            "analyser": {"trajectory": {"quantum": "wave_function", "save_times": "all", "save_final_state": True}},
        },
    )

    trajectory = QuTiPEngine().run(_with_solver_run(copy.deepcopy(spec), ntraj=4, seed=19))
    trajectory_repeat = QuTiPEngine().run(_with_solver_run(copy.deepcopy(spec), ntraj=4, seed=19))

    assert trajectory.metadata.get("solver_impl") == "mcsolve"
    assert trajectory.metadata.get("readout_protocol") == "photon_counting_sme"
    readout = dict(trajectory.classical.get("readout", {}) or {})
    assert readout.get("feedback", {}).get("mode") == "photon_counting_sme"
    assert "heterodyne_current" not in readout
    assert "homodyne_current" not in readout
    assert len(readout.get("shots", [])) == 4
    assert len(readout.get("photon_counts", [])) == len(trajectory.times)
    assert len(readout.get("count_rate", [])) == len(trajectory.times)
    records = list((trajectory.measurements or {}).get("records", []) or [])
    assert len(records) == 4
    assert len(records[0].get("photon_counts", [])) == len(trajectory.times)
    repeat_records = list((trajectory_repeat.measurements or {}).get("records", []) or [])
    assert [rec.get("photon_counts", []) for rec in records] == [rec.get("photon_counts", []) for rec in repeat_records]


def test_qutip_engine_heterodyne_sme_preserves_raw_runs_and_stochastic_cavity_shots():
    pytest.importorskip("qutip")
    spec = _spec(
        solver="me",
        dimension=9,
        t_end=5.0e-9,
        dt=1.0e-9,
        model={
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
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6, "eta_chain": 0.35, "bandwidth_Hz": 8.0e6}},
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
            "primary_step": {"options": {"readout_protocol": "heterodyne_sme"}},
            "analyser": {"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}},
        },
    )

    trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=3, seed=17))

    density_matrix = dict(trajectory.density_matrix or {})
    assert density_matrix.get("actual_kind") == "density_matrix"
    assert density_matrix.get("num_runs") == 3
    assert len(density_matrix.get("runs", [])) == 3
    assert all(len(run) == len(trajectory.times) for run in density_matrix.get("runs", []))

    readout = dict(trajectory.classical.get("readout", {}) or {})
    shots = list(readout.get("shots", []) or [])
    assert len(shots) == 3
    shot0 = np.asarray(shots[0].get("a_cavity", []), dtype=float)
    shot1 = np.asarray(shots[1].get("a_cavity", []), dtype=float)
    assert shot0.shape == shot1.shape
    assert not np.allclose(shot0, shot1)


def test_qutip_engine_runs_cavity_classical_readout_without_qutip_dependency():
    spec = _spec(
        solver="me",
        dimension=1,
        t_end=6.0e-9,
        dt=1.0e-9,
        model={
            "model_type": "cavity_classical_readout",
            "num_qubits": 0,
            "components": [
                {
                    "id": "r0",
                    "type": "resonator",
                    "representation": "classical",
                    "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6, "kappa_ext_Hz": 4.5e6, "chi_Hz": -5.5e6},
                },
                {
                    "id": "ro0",
                    "type": "readout_line",
                    "representation": "classical",
                    "parameters": {
                        "eta_chain": 0.8,
                        "gain_dB": 42.0,
                        "added_noise_photons": 2.0,
                        "bandwidth_Hz": 6.0e6,
                        "input_amplitude_noise_rel_sigma": 0.02,
                    },
                },
            ],
            "connections": [
                {"id": "feed", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 4.5e6, "eta_chain": 0.8, "bandwidth_Hz": 6.0e6}}
            ],
            "readout_controls": [
                {
                    "channel": "RO_0",
                    "kind": "readout",
                    "target": 0,
                    "times": [0.0, 3.0e-9, 6.0e-9],
                    "values": [0.0, 1.0, 0.0],
                    "scale": 1.0,
                    "carrier_freq_Hz": 6.45e9,
                    "carrier_omega_rad_s": 2.0 * math.pi * 6.45e9,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "primary_step": {"prep_state": {"label": "1", "sequence": []}, "options": {"subsystem_model": "cavity_classical_readout"}},
            "noise_cfg": {"readout_error": 0.01},
        },
    )

    trajectory = QuTiPEngine().run(_with_solver_run(spec, ntraj=4, seed=23))

    assert trajectory.times
    assert not trajectory.density_matrix
    readout = dict((trajectory.classical or {}).get("readout", {}) or {})
    assert len(readout.get("shots", [])) == 4
    assert readout.get("chain", {}).get("hidden_state") == 1
    basis_population = dict((trajectory.classical or {}).get("basis_population", {}) or {})
    assert basis_population.get("series_labels") == ["0", "1"]



