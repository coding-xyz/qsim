import math

from qsim.analysis.readout_chain import build_readout_analysis
from qsim.common.schemas import Carrier, ChannelSpec, ModelSpec, PulseIR, PulseSpec, Trace


def test_build_readout_analysis_returns_readout_and_iq_payloads():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trace = Trace(
        engine="qutip",
        times=times,
        states=[[0.0], [0.1], [0.2], [0.3]],
        metadata={
            "readout_observables": {
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
        trace=trace,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analysis_cfg=analysis_cfg,
        seed=123,
    )

    assert "readout" in out
    assert "iq" in out
    assert len(out["readout"]["a_out"]) == len(times)
    assert out["iq"]["labels"] == ["|1>"]
    assert math.isfinite(out["iq"]["assignment_fidelity"])


def test_build_readout_analysis_uses_actual_shot_payloads():
    times = [0.0, 1.0e-9, 2.0e-9, 3.0e-9]
    trace = Trace(
        engine="qutip",
        times=times,
        states=[[0.0], [0.0], [0.0], [0.0]],
        metadata={
            "readout_observables": {
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
        trace=trace,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analysis_cfg=analysis_cfg,
        seed=123,
    )

    assert out["readout"]["num_shots"] == 3
    assert out["iq"]["num_shots"] == 3
    assert len(out["iq"]["synthetic_clouds"]["|1>"]) == 3
