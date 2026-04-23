import math

from qsim.analysis.readout_chain import build_readout_analysis
from qsim.common.schemas import Carrier, ChannelSpec, ModelSpec, PulseIR, PulseSpec, Trajectory


def test_build_readout_analysis_returns_readout_and_iq_payloads():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trajectory = Trajectory(
        engine="qutip",
        times=times,
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[0.9 + 0.0j, 0.0j], [0.0j, 0.1 + 0.0j]],
                [[0.8 + 0.0j, 0.0j], [0.0j, 0.2 + 0.0j]],
                [[0.7 + 0.0j, 0.0j], [0.0j, 0.3 + 0.0j]],
            ],
        },
        classical={
            "readout": {
                "times": times,
                "cavity_a": [[0.0, 0.0], [0.1, 0.05], [0.15, 0.05], [0.1, 0.0]],
                "cavity_n": [0.0, 0.01, 0.02, 0.01],
                "qubit_lowering": [],
            }
        },
    )
    model_spec = ModelSpec(
        solver="me",
        dimension=6,
        t_end=3.0e-9,
        dt=1.0e-9,
        payload={
            "components": [
                {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6}},
                {
                    "id": "ro0",
                    "type": "readout_line",
                    "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0},
                },
            ],
            "connections": [
                {
                    "id": "ro",
                    "type": "readout_feedline",
                    "a": "r0",
                    "b": "ro0",
                    "parameters": {
                        "kappa_ext_Hz": 7.0e6,
                        "eta_chain": 0.35,
                        "input_output": {
                            "cavity_equation": "da/dt = ...",
                            "output_equation": "a_out = ...",
                        },
                    },
                }
            ],
            "noise_cfg": {"readout_error": 0.02},
        },
    )
    pulse_ir = PulseIR(
        t_end_s=3.0e-9,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.8,
                        shape="readout",
                        params={"rise_s": 0.0, "fall_s": 0.0, "break_stage": "measure"},
                        carrier=Carrier(freq=6.45e9, phase=0.0),
                    )
                ],
            )
        ],
    )
    analysis_cfg = {
        "readout_model": {"mode": "dispersive_cqed"},
        "iq_discrimination": {
            "method": "linear_discriminant",
            "shots": 16,
            "calibration_states": [{"label": "|1>"}],
        },
    }
    pulse_cfg = {"acquisition": {"integration_window_ns": 3.0, "start_delay_ns": 0.0, "demodulation": {"phase_rad": 0.0}}}

    out = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analysis_cfg,
        seed=123,
    )

    assert "readout" in out
    assert "iq" in out
    assert len(out["readout"]["a_out"]) == len(times)
    assert out["iq"]["labels"] == ["|1>"]
    assert math.isfinite(out["iq"]["assignment_fidelity"])


def test_build_readout_analysis_uses_actual_shot_payloads():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trajectory = Trajectory(
        engine="qutip",
        times=times,
        wave_function={
            "actual_kind": "wave_function",
            "encoding": "complex",
            "snapshots": [
                [1.0 + 0.0j, 0.0j],
                [1.0 + 0.0j, 0.0j],
                [1.0 + 0.0j, 0.0j],
                [1.0 + 0.0j, 0.0j],
            ],
        },
        classical={
            "readout": {
                "times": times,
                "a_in": [[0.0, 0.0] for _ in times],
                "cavity_a": [[0.0, 0.0] for _ in times],
                "a_out": [[0.0, 0.0] for _ in times],
                "line_state": [[0.0, 0.0] for _ in times],
                "measured_voltage": [[0.0, 0.0] for _ in times],
                "shots": [
                    {"measured_voltage": [[0.1, 0.2] for _ in times]},
                    {"measured_voltage": [[0.2, 0.3] for _ in times]},
                    {"measured_voltage": [[0.3, 0.4] for _ in times]},
                ],
            }
        },
    )
    model_spec = ModelSpec(
        solver="mcwf",
        dimension=6,
        t_end=3.0e-9,
        dt=1.0e-9,
        payload={
            "components": [
                {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6}},
                {"id": "ro0", "type": "readout_line", "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0}},
            ],
            "connections": [{"id": "ro", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6}}],
            "noise_cfg": {"readout_error": 0.02},
        },
    )
    pulse_ir = PulseIR(
        t_end_s=3.0e-9,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.8,
                        shape="readout",
                        params={"rise_s": 0.0, "fall_s": 0.0, "break_stage": "measure"},
                        carrier=Carrier(freq=6.45e9, phase=0.0),
                    )
                ],
            )
        ],
    )
    analysis_cfg = {
        "readout_model": {"mode": "dispersive_cqed"},
        "iq_discrimination": {
            "method": "linear_discriminant",
            "shots": 3,
            "calibration_states": [{"label": "|1>"}],
        },
    }
    pulse_cfg = {"acquisition": {"integration_window_ns": 3.0, "start_delay_ns": 0.0, "demodulation": {"phase_rad": 0.0}}}

    out = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analysis_cfg,
        seed=123,
    )

    assert out["readout"]["num_shots"] == 3
    assert out["iq"]["num_shots"] == 3
    assert len(out["iq"]["synthetic_clouds"]["|1>"]) == 3


def test_build_readout_analysis_consumes_heterodyne_iq_shot_payloads():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trajectory = Trajectory(
        engine="qutip",
        times=times,
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
            ],
        },
        classical={
            "readout": {
                "times": times,
                "a_in": [[0.0, 0.0] for _ in times],
                "cavity_a": [[0.0, 0.0] for _ in times],
                "a_out": [[0.0, 0.0] for _ in times],
                "heterodyne_current": [[0.0, 0.0] for _ in times],
                "shots": [
                    {"heterodyne_I": [0.1, 0.1, 0.1, 0.1], "heterodyne_Q": [0.2, 0.2, 0.2, 0.2]},
                    {"heterodyne_I": [0.2, 0.2, 0.2, 0.2], "heterodyne_Q": [0.3, 0.3, 0.3, 0.3]},
                ],
            }
        },
    )
    model_spec = ModelSpec(
        solver="me",
        dimension=6,
        t_end=3.0e-9,
        dt=1.0e-9,
        payload={
            "components": [
                {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6}},
                {"id": "ro0", "type": "readout_line", "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0}},
            ],
            "connections": [{"id": "ro", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6}}],
            "noise_cfg": {"readout_error": 0.02},
        },
    )
    pulse_ir = PulseIR(
        t_end_s=3.0e-9,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.8,
                        shape="readout",
                        params={"rise_s": 0.0, "fall_s": 0.0, "break_stage": "measure"},
                        carrier=Carrier(freq=6.45e9, phase=0.0),
                    )
                ],
            )
        ],
    )
    analysis_cfg = {
        "readout_model": {"mode": "dispersive_cqed"},
        "iq_discrimination": {
            "method": "linear_discriminant",
            "shots": 2,
            "calibration_states": [{"label": "|1>"}],
        },
    }
    pulse_cfg = {"acquisition": {"integration_window_ns": 3.0, "start_delay_ns": 0.0, "demodulation": {"phase_rad": 0.0, "if_Hz": 25.0e6}}}

    out = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analysis_cfg,
        seed=123,
    )

    assert out["readout"]["num_shots"] == 2
    assert len(out["readout"]["heterodyne_current"]) == len(times)
    assert len(out["readout"]["ro_line_if"]) == len(times)
    assert out["iq"]["num_shots"] == 2
    assert len(out["iq"]["synthetic_clouds"]["|1>"]) == 2


def test_build_readout_analysis_direct_adc_outputs_receiver_views():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trajectory = Trajectory(
        engine="qutip",
        times=times,
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
            ],
        },
        classical={
            "readout": {
                "times": times,
                "a_in": [[0.0, 0.0] for _ in times],
                "cavity_a": [[0.0, 0.0] for _ in times],
                "a_out": [[0.0, 0.0] for _ in times],
                "measured_voltage": [[1.0, 0.0] for _ in times],
                "shots": [{"measured_voltage": [[1.0, 0.0] for _ in times]}],
            }
        },
    )
    model_spec = ModelSpec(
        solver="mcwf",
        dimension=6,
        t_end=3.0e-9,
        dt=1.0e-9,
        payload={
            "components": [
                {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6}},
                {"id": "ro0", "type": "readout_line", "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0}},
            ],
            "connections": [{"id": "ro", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6}}],
            "noise_cfg": {"readout_error": 0.02},
        },
    )
    pulse_ir = PulseIR(
        t_end_s=3.0e-9,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.8,
                        shape="readout",
                        params={"rise_s": 0.0, "fall_s": 0.0, "break_stage": "measure"},
                        carrier=Carrier(freq=6.45e9, phase=0.0),
                    )
                ],
            ),
            ChannelSpec(
                name="LO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.0,
                        shape="rect",
                        params={},
                        carrier=Carrier(freq=5.8e9, phase=0.0),
                    )
                ],
            ),
        ],
    )
    analysis_cfg = {
        "readout_model": {
            "mode": "cavity_classical_readout",
            "channels": {"cavity_drive": "RO_0", "local_oscillator": "LO_0"},
            "receiver": {
                "mode": "direct_adc",
                "adc_sample_rate_Hz": 1.0e9,
                "carrier_frequency_Hz": 6.45e9,
                "adc_noise_sigma": 0.0,
            },
        },
        "iq_discrimination": {"method": "linear_discriminant", "shots": 1, "calibration_states": [{"label": "|1>"}]},
    }
    pulse_cfg = {"acquisition": {"integration_window_ns": 3.0, "start_delay_ns": 0.0, "demodulation": {"phase_rad": 0.0, "if_Hz": 650.0e6}}}

    out = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analysis_cfg,
        seed=123,
    )

    assert out["readout"]["receiver"]["mode"] == "direct_adc"
    assert out["readout"]["receiver"]["alias_frequency_Hz"] == 450.0e6
    assert len(out["readout"]["complex_envelope"]) == len(times)
    assert len(out["readout"]["rf_signal"]) == len(times)
    assert len(out["readout"]["adc_signal"]) == len(out["readout"]["adc_times"])
    assert out["iq"]["num_shots"] == 1


def test_build_readout_analysis_downconversion_outputs_if_alias():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trajectory = Trajectory(
        engine="qutip",
        times=times,
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
            ],
        },
        classical={
            "readout": {
                "times": times,
                "a_in": [[0.0, 0.0] for _ in times],
                "cavity_a": [[0.0, 0.0] for _ in times],
                "a_out": [[0.0, 0.0] for _ in times],
                "measured_voltage": [[1.0, 0.0] for _ in times],
            }
        },
    )
    model_spec = ModelSpec(
        solver="me",
        dimension=6,
        t_end=3.0e-9,
        dt=1.0e-9,
        payload={
            "components": [
                {"id": "r0", "type": "resonator", "parameters": {"freq_Hz": 6.45e9, "kappa_int_Hz": 1.0e6}},
                {"id": "ro0", "type": "readout_line", "parameters": {"eta_chain": 0.35, "gain_dB": 40.0, "added_noise_photons": 12.0}},
            ],
            "connections": [{"id": "ro", "type": "readout_feedline", "a": "r0", "b": "ro0", "parameters": {"kappa_ext_Hz": 7.0e6}}],
            "noise_cfg": {"readout_error": 0.02},
        },
    )
    pulse_ir = PulseIR(
        t_end_s=3.0e-9,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.8,
                        shape="readout",
                        params={"rise_s": 0.0, "fall_s": 0.0, "break_stage": "measure"},
                        carrier=Carrier(freq=6.45e9, phase=0.0),
                    )
                ],
            ),
            ChannelSpec(
                name="LO_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=3.0e-9,
                        amp=0.0,
                        shape="rect",
                        params={},
                        carrier=Carrier(freq=5.8e9, phase=0.0),
                    )
                ],
            ),
        ],
    )
    analysis_cfg = {
        "readout_model": {
            "mode": "cavity_classical_readout",
            "channels": {"cavity_drive": "RO_0", "local_oscillator": "LO_0"},
            "receiver": {
                "mode": "downconversion",
                "adc_sample_rate_Hz": 1.0e9,
                "carrier_frequency_Hz": 6.45e9,
                "lo_frequency_Hz": 5.8e9,
                "if_frequency_Hz": 650.0e6,
                "adc_noise_sigma": 0.0,
            },
        },
        "iq_discrimination": {"method": "linear_discriminant", "shots": 2, "calibration_states": [{"label": "|1>"}]},
    }
    pulse_cfg = {"acquisition": {"integration_window_ns": 3.0, "start_delay_ns": 0.0, "demodulation": {"phase_rad": 0.0, "if_Hz": 650.0e6}}}

    out = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analysis_cfg,
        seed=123,
    )

    assert out["readout"]["receiver"]["mode"] == "downconversion"
    assert out["readout"]["receiver"]["if_frequency_Hz"] == 650.0e6
    assert out["readout"]["receiver"]["alias_frequency_Hz"] == 350.0e6
    assert len(out["readout"]["if_signal"]) == len(times)
    assert len(out["readout"]["adc_signal"]) == len(out["readout"]["adc_times"])

