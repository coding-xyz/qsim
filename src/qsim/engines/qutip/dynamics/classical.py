"""Pure classical CQED dynamics for the QuTiP engine."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qsim.common.schemas import ModelSpec, Trajectory
from qsim.engines.qutip.measurement import _control_attr
from qsim.engines.qutip.runtime import QutipRunConfig


class QutipClassicalDynamicsMixin:
    """Run classical cavity/readout-line dynamics without a quantum solver."""

    @classmethod
    def _simulate_classical_readout(
        cls,
        *,
        tlist: np.ndarray,
        drive: np.ndarray,
        cavity_avg: np.ndarray,
        cavity_shots: list[np.ndarray],
        chain: dict[str, Any],
        seed: int,
    ) -> dict[str, Any]:
        if tlist.size <= 0:
            return {}
        kappa_ext = max(0.0, float(chain.get("kappa_ext_Hz", 0.0)))
        eta_chain = max(1.0e-6, float(chain.get("eta_chain", 1.0)))
        added_noise = max(0.0, float(chain.get("added_noise_photons", 0.0)))
        gain_linear = 10.0 ** (float(chain.get("gain_dB", 0.0)) / 20.0)
        bandwidth_hz = max(0.0, float(chain.get("bandwidth_Hz", 0.0)))
        gamma_line = 2.0 * math.pi * bandwidth_hz if bandwidth_hz > 0.0 else 0.0
        dt = max(1.0e-18, float(tlist[1] - tlist[0])) if tlist.size > 1 else 1.0
        noise_sigma = max(1.0e-5, math.sqrt(added_noise / eta_chain) * 1.0e-2)
        rng = np.random.default_rng(int(seed))

        def _simulate_single(cavity_series: np.ndarray) -> dict[str, np.ndarray]:
            a_in = np.asarray(drive, dtype=complex).reshape(-1)
            a_out = np.asarray(
                [
                    cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext)
                    for in_field, cavity_field in zip(a_in, np.asarray(cavity_series, dtype=complex).reshape(-1))
                ],
                dtype=complex,
            )
            line_state = np.zeros_like(a_out, dtype=complex)
            measured_voltage = np.zeros_like(a_out, dtype=complex)
            for k in range(a_out.size):
                noise = noise_sigma * (float(rng.normal()) + 1j * float(rng.normal())) / math.sqrt(2.0)
                if k > 0:
                    prev = line_state[k - 1]
                    if gamma_line > 0.0:
                        line_state[k] = prev + dt * (-0.5 * gamma_line * prev + gamma_line * a_out[k - 1])
                    else:
                        line_state[k] = a_out[k - 1]
                else:
                    line_state[k] = a_out[k]
                measured_voltage[k] = gain_linear * line_state[k] + noise
            return {
                "a_in": a_in,
                "a_out": a_out,
                "line_state": line_state,
                "measured_voltage": measured_voltage,
            }

        shots = [_simulate_single(series) for series in (cavity_shots or [cavity_avg])]
        avg = {
            key: np.mean(np.asarray([shot[key] for shot in shots], dtype=complex), axis=0)
            for key in ("a_in", "a_out", "line_state", "measured_voltage")
        }
        avg["a_cavity"] = np.asarray(cavity_avg, dtype=complex).reshape(-1)
        return {
            "average": avg,
            "shots": [
                {
                    "a_cavity": cls._serialize_complex_series(series),
                    "a_in": cls._serialize_complex_series(shot["a_in"]),
                    "a_out": cls._serialize_complex_series(shot["a_out"]),
                    "line_state": cls._serialize_complex_series(shot["line_state"]),
                    "measured_voltage": cls._serialize_complex_series(shot["measured_voltage"]),
                }
                for shot, series in zip(shots, cavity_shots or [cavity_avg])
            ],
        }

    @classmethod
    def _run_cavity_classical_readout(
        cls,
        *,
        model_spec: ModelSpec,
        run_config: QutipRunConfig,
    ) -> Trajectory:
        dt = max(float(model_spec.dt), 1.0e-12)
        t_end = max(float(model_spec.t_end), dt)
        tlist = np.arange(0.0, t_end + 0.5 * dt, dt)
        nt = int(tlist.size)
        primary_step = dict(model_spec.study.primary_step if model_spec.study else {})
        hidden_state, state_label = cls._classical_readout_state(primary_step)
        chain = cls._infer_classical_readout_params(model_spec)
        readout_controls = list(model_spec.readout.controls if model_spec.readout else [])
        base_drive = cls._sample_readout_drive(tlist, readout_controls)
        drive_freq_hz = float(_control_attr(readout_controls[0], "carrier_freq_Hz", chain.get("center_freq_Hz", 0.0))) if readout_controls else float(chain.get("center_freq_Hz", 0.0))
        cavity_freq_hz = float(chain.get("cavity_freq_Hz", drive_freq_hz) or drive_freq_hz)
        chi_hz = float(chain.get("chi_Hz", 0.0) or 0.0)
        state_shift_hz = chi_hz if hidden_state else 0.0
        delta_eff_rad_s = 2.0 * math.pi * (cavity_freq_hz + state_shift_hz - drive_freq_hz)
        kappa_int_rad_s = max(0.0, 2.0 * math.pi * float(chain.get("kappa_int_Hz", 0.0)))
        kappa_ext_rad_s = max(0.0, 2.0 * math.pi * float(chain.get("kappa_ext_Hz", 0.0)))
        kappa_total_rad_s = kappa_int_rad_s + kappa_ext_rad_s
        gamma_line = 2.0 * math.pi * max(0.0, float(chain.get("bandwidth_Hz", 0.0)))
        eta_chain = max(1.0e-6, float(chain.get("eta_chain", 1.0) or 1.0))
        gain_linear = 10.0 ** (float(chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        added_noise_photons = max(0.0, float(chain.get("added_noise_photons", 0.0) or 0.0))
        input_amp_sigma = max(0.0, float(chain.get("input_amplitude_noise_rel_sigma", 0.0) or 0.0))
        input_phase_sigma = max(0.0, float(chain.get("input_phase_noise_std_rad", 0.0) or 0.0))
        input_add_sigma = max(0.0, float(chain.get("input_additive_noise_sigma", 0.0) or 0.0))
        feedback_success_prob = min(1.0, max(0.0, float(chain.get("feedback_success_prob", 1.0) or 1.0)))
        coupling = cls._readout_coupling_prefactor(float(chain.get("kappa_ext_Hz", 0.0) or 0.0))
        seed = int(run_config.seed)
        ntraj = max(1, int(run_config.ntraj))
        rng = np.random.default_rng(seed)
        drive_scale = max(1.0, float(np.max(np.abs(base_drive))) if base_drive.size > 0 else 1.0)
        measurement_noise_sigma = max(
            1.0e-5,
            drive_scale
            * (
                math.sqrt(added_noise_photons / eta_chain) * 1.0e-2
                + float(model_spec.noise.readout_error or 0.0)
            ),
        )
        raw_reset_events = list(model_spec.readout.reset_events if model_spec.readout else [])
        reset_events = [
            {
                "target": getattr(event, "target", 0),
                "t0_s": float(getattr(event, "t0_s", 0.0)),
                "t_meas_end_s": float(getattr(event, "t_meas_end_s", 0.0)),
                "t_feedback_start_s": float(getattr(event, "t_feedback_start_s", 0.0)),
                "t_apply_s": float(getattr(event, "t_apply_s", 0.0)),
                "conditional_on": int(getattr(event, "conditional_on", 1)),
                "apply_feedback": bool(getattr(event, "apply_feedback", True)),
                "success_probability": float(getattr(event, "success_probability", feedback_success_prob)),
            }
            for event in raw_reset_events
        ]
        reset_events.sort(key=lambda item: float(item.get("t0_s", 0.0)))

        def _nearest_time_index(target_s: float) -> int:
            return int(np.clip(np.searchsorted(tlist, float(target_s), side="left"), 0, max(0, nt - 1)))

        def _integrate_complex_window(trace: np.ndarray, start_s: float, stop_s: float) -> complex:
            if nt <= 0:
                return 0.0j
            mask = (tlist >= float(start_s)) & (tlist <= float(stop_s))
            if not np.any(mask):
                idx = _nearest_time_index(0.5 * (float(start_s) + float(stop_s)))
                return complex(trace[idx])
            t_sel = tlist[mask]
            trace_sel = np.asarray(trace[mask], dtype=complex)
            if t_sel.size == 1:
                return complex(trace_sel[0])
            span = max(float(t_sel[-1] - t_sel[0]), 1.0e-18)
            if hasattr(np, "trapezoid"):
                i_val = float(np.trapezoid(np.real(trace_sel), t_sel) / span)
                q_val = float(np.trapezoid(np.imag(trace_sel), t_sel) / span)
            else:
                i_val = float(np.trapz(np.real(trace_sel), t_sel) / span)
                q_val = float(np.trapz(np.imag(trace_sel), t_sel) / span)
            return complex(i_val, q_val)

        def _reference_reset_point(
            *,
            alpha0: complex,
            line0: complex,
            a_in_series: np.ndarray,
            start_idx: int,
            stop_idx: int,
            state: int,
        ) -> complex:
            alpha = complex(alpha0)
            line = complex(line0)
            measured = np.zeros(max(1, stop_idx - start_idx + 1), dtype=complex)
            local_times = tlist[start_idx : stop_idx + 1]
            delta_rad = 2.0 * math.pi * (cavity_freq_hz + (chi_hz if state else 0.0) - drive_freq_hz)
            for out_idx, idx in enumerate(range(start_idx, stop_idx + 1)):
                if idx > start_idx:
                    alpha = alpha + dt * (-(0.5 * kappa_total_rad_s + 1j * delta_rad) * alpha + coupling * a_in_series[idx - 1])
                a_out_ref = cls._input_output_a_out(
                    a_in=complex(a_in_series[idx]),
                    cavity_field=alpha,
                    kappa_ext_hz=float(chain.get("kappa_ext_Hz", 0.0) or 0.0),
                )
                if gamma_line > 0.0:
                    line = line + dt * (-0.5 * gamma_line * line + gamma_line * a_out_ref)
                else:
                    line = a_out_ref
                measured[out_idx] = gain_linear * math.sqrt(eta_chain) * line
            if measured.size <= 1 or local_times.size <= 1:
                return complex(measured[-1])
            span = max(float(local_times[-1] - local_times[0]), 1.0e-18)
            if hasattr(np, "trapezoid"):
                i_val = float(np.trapezoid(np.real(measured), local_times) / span)
                q_val = float(np.trapezoid(np.imag(measured), local_times) / span)
            else:
                i_val = float(np.trapz(np.real(measured), local_times) / span)
                q_val = float(np.trapz(np.imag(measured), local_times) / span)
            return complex(i_val, q_val)

        shot_payloads: list[dict[str, Any]] = []
        shot_records: list[dict[str, Any]] = []
        mean_accum: dict[str, np.ndarray] = {
            "a_in": np.zeros(nt, dtype=complex),
            "cavity_a": np.zeros(nt, dtype=complex),
            "cavity_n": np.zeros(nt, dtype=float),
            "a_out": np.zeros(nt, dtype=complex),
            "line_state": np.zeros(nt, dtype=complex),
            "heterodyne_current": np.zeros(nt, dtype=complex),
            "measured_voltage": np.zeros(nt, dtype=complex),
        }

        for traj_idx in range(ntraj):
            amp_noise = rng.normal(0.0, input_amp_sigma, size=nt) if input_amp_sigma > 0.0 else np.zeros(nt, dtype=float)
            phase_noise = rng.normal(0.0, input_phase_sigma, size=nt) if input_phase_sigma > 0.0 else np.zeros(nt, dtype=float)
            additive_noise = (
                input_add_sigma
                * (rng.normal(0.0, 1.0, size=nt) + 1j * rng.normal(0.0, 1.0, size=nt))
                / math.sqrt(2.0)
                if input_add_sigma > 0.0
                else np.zeros(nt, dtype=complex)
            )
            a_in = base_drive * (1.0 + amp_noise) * np.exp(1j * phase_noise) + additive_noise

            cavity_a = np.zeros(nt, dtype=complex)
            state_series = np.zeros(nt, dtype=int)
            current_state = int(hidden_state)
            state_series[:] = current_state
            cavity_n = np.abs(cavity_a) ** 2
            a_out = np.zeros(nt, dtype=complex)
            line_state = np.zeros(nt, dtype=complex)
            heterodyne_current = np.zeros(nt, dtype=complex)
            measured_voltage = np.zeros(nt, dtype=complex)
            reset_log: list[dict[str, Any]] = []
            reset_contexts: list[dict[str, Any]] = []
            for event in reset_events:
                reset_contexts.append(
                    {
                        **event,
                        "measured": False,
                        "applied": False,
                        "predicted_state": None,
                        "alpha_start": None,
                        "line_start": None,
                    }
                )
            for idx in range(nt):
                if idx > 0:
                    current_state = int(state_series[idx - 1])
                    delta_now_rad_s = 2.0 * math.pi * (cavity_freq_hz + (chi_hz if current_state else 0.0) - drive_freq_hz)
                    cavity_a[idx] = cavity_a[idx - 1] + dt * (
                        -(0.5 * kappa_total_rad_s + 1j * delta_now_rad_s) * cavity_a[idx - 1]
                        + coupling * a_in[idx - 1]
                    )
                    cavity_n[idx] = float(abs(cavity_a[idx]) ** 2)
                a_out[idx] = cls._input_output_a_out(
                    a_in=complex(a_in[idx]),
                    cavity_field=complex(cavity_a[idx]),
                    kappa_ext_hz=float(chain.get("kappa_ext_Hz", 0.0) or 0.0),
                )
                if idx == 0:
                    line_state[idx] = a_out[idx]
                elif gamma_line > 0.0:
                    line_state[idx] = line_state[idx - 1] + dt * (-0.5 * gamma_line * line_state[idx - 1] + gamma_line * a_out[idx - 1])
                else:
                    line_state[idx] = a_out[idx]
                noise = measurement_noise_sigma * (
                    rng.normal(0.0, 1.0) + 1j * rng.normal(0.0, 1.0)
                ) / math.sqrt(2.0)
                heterodyne_current[idx] = math.sqrt(eta_chain) * line_state[idx] + noise
                measured_voltage[idx] = gain_linear * heterodyne_current[idx]
                state_series[idx] = current_state

                for event in reset_contexts:
                    if event["alpha_start"] is None and float(tlist[idx]) >= float(event.get("t0_s", 0.0)):
                        event["alpha_start"] = complex(cavity_a[idx])
                        event["line_start"] = complex(line_state[idx])
                    if not event["measured"] and float(tlist[idx]) >= float(event.get("t_meas_end_s", 0.0)):
                        start_idx = _nearest_time_index(float(event.get("t0_s", 0.0)))
                        stop_idx = _nearest_time_index(float(event.get("t_meas_end_s", 0.0)))
                        actual_point = _integrate_complex_window(measured_voltage, float(event.get("t0_s", 0.0)), float(event.get("t_meas_end_s", 0.0)))
                        alpha_start = complex(event.get("alpha_start", 0.0j) or 0.0j)
                        line_start = complex(event.get("line_start", 0.0j) or 0.0j)
                        point_0 = _reference_reset_point(alpha0=alpha_start, line0=line_start, a_in_series=a_in, start_idx=start_idx, stop_idx=stop_idx, state=0)
                        point_1 = _reference_reset_point(alpha0=alpha_start, line0=line_start, a_in_series=a_in, start_idx=start_idx, stop_idx=stop_idx, state=1)
                        predicted_state = 0 if abs(actual_point - point_0) <= abs(actual_point - point_1) else 1
                        event["predicted_state"] = int(predicted_state)
                        event["measured"] = True
                        reset_log.append(
                            {
                                "trajectory_index": traj_idx,
                                "window_s": {"t0": float(event.get("t0_s", 0.0)), "t1": float(event.get("t_meas_end_s", 0.0))},
                                "actual_state_before_feedback": int(current_state),
                                "predicted_state": int(predicted_state),
                                "integrated_iq": [float(actual_point.real), float(actual_point.imag)],
                            }
                        )
                    if (
                        not event["applied"]
                        and event["predicted_state"] is not None
                        and float(tlist[idx]) >= float(event.get("t_apply_s", 0.0))
                    ):
                        if bool(event.get("apply_feedback", False)) and int(event.get("predicted_state", -1)) == int(event.get("conditional_on", 1)):
                            if float(rng.random()) <= feedback_success_prob:
                                current_state = 1 - int(current_state)
                        event["applied"] = True
                    state_series[idx] = current_state

            cavity_n = np.abs(cavity_a) ** 2

            mean_accum["a_in"] += a_in
            mean_accum["cavity_a"] += cavity_a
            mean_accum["cavity_n"] += cavity_n
            mean_accum["a_out"] += a_out
            mean_accum["line_state"] += line_state
            mean_accum["heterodyne_current"] += heterodyne_current
            mean_accum["measured_voltage"] += measured_voltage

            shot_payload = {
                "trajectory_index": traj_idx,
                "hidden_state": int(hidden_state),
                "hidden_state_label": state_label,
                "hidden_state_series": [int(val) for val in state_series.tolist()],
                "a_cavity": cls._serialize_complex_series(cavity_a),
                "a_in": cls._serialize_complex_series(a_in),
                "a_out": cls._serialize_complex_series(a_out),
                "line_state": cls._serialize_complex_series(line_state),
                "heterodyne_current": cls._serialize_complex_series(heterodyne_current),
                "measured_voltage": cls._serialize_complex_series(measured_voltage),
                "cavity_n": [float(val) for val in cavity_n.tolist()],
                "reset_log": reset_log,
            }
            shot_payloads.append(shot_payload)
            shot_records.append(
                {
                    "trajectory_index": traj_idx,
                    "times": tlist.astype(float).tolist(),
                    "heterodyne_current": shot_payload["heterodyne_current"],
                    "heterodyne_I": [float(val.real) for val in heterodyne_current.tolist()],
                    "heterodyne_Q": [float(val.imag) for val in heterodyne_current.tolist()],
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            )

        return cls._build_cavity_classical_readout_trajectory(
            model_spec=model_spec,
            tlist=tlist,
            ntraj=ntraj,
            hidden_state=hidden_state,
            state_label=state_label,
            chain=chain,
            drive_freq_hz=drive_freq_hz,
            state_shift_hz=state_shift_hz,
            shot_payloads=shot_payloads,
            shot_records=shot_records,
            mean_accum=mean_accum,
        )

    @classmethod
    def _build_cavity_classical_readout_trajectory(
        cls,
        *,
        model_spec: ModelSpec,
        tlist: np.ndarray,
        ntraj: int,
        hidden_state: int,
        state_label: str,
        chain: dict[str, Any],
        drive_freq_hz: float,
        state_shift_hz: float,
        shot_payloads: list[dict[str, Any]],
        shot_records: list[dict[str, Any]],
        mean_accum: dict[str, np.ndarray],
    ) -> Trajectory:
        nt = int(tlist.size)
        norm = 1.0 / float(ntraj)
        avg_a_in = mean_accum["a_in"] * norm
        avg_cavity_a = mean_accum["cavity_a"] * norm
        avg_cavity_n = (mean_accum["cavity_n"] * norm).tolist()
        avg_a_out = mean_accum["a_out"] * norm
        avg_line_state = mean_accum["line_state"] * norm
        avg_heterodyne = mean_accum["heterodyne_current"] * norm
        avg_voltage = mean_accum["measured_voltage"] * norm

        avg_state_series = np.rint(
            np.mean(
                np.asarray(
                    [shot.get("hidden_state_series", [hidden_state for _ in range(nt)]) for shot in shot_payloads],
                    dtype=float,
                ),
                axis=0,
            )
        ).astype(int)
        basis_values = [[float(1 - val), float(val)] for val in avg_state_series.tolist()]
        classical = {
            "readout": {
                "times": tlist.astype(float).tolist(),
                "a_in": cls._serialize_complex_series(avg_a_in),
                "cavity_a": cls._serialize_complex_series(avg_cavity_a),
                "cavity_n": [float(val) for val in avg_cavity_n],
                "a_out": cls._serialize_complex_series(avg_a_out),
                "line_state": cls._serialize_complex_series(avg_line_state),
                "heterodyne_current": cls._serialize_complex_series(avg_heterodyne),
                "measured_voltage": cls._serialize_complex_series(avg_voltage),
                "shots": shot_payloads,
                "chain": {
                    **chain,
                    "drive_freq_Hz": float(drive_freq_hz),
                    "state_shift_Hz": float(state_shift_hz),
                    "hidden_state": int(hidden_state),
                    "hidden_state_label": state_label,
                },
                "equations": {
                    "cavity_equation": "d alpha / dt = -(i Delta_eff + kappa/2) alpha + sqrt(kappa_ext) * a_in(t)",
                    "output_equation": "a_out(t) = a_in(t) - sqrt(kappa_ext) * alpha(t)",
                    "measured_voltage": "V_meas(t) = gain * (sqrt(eta_chain) * alpha_line(t) + xi_meas)",
                    "input_noise": "a_in(t) = (1 + dA) a_in,ideal(t) exp(i dphi) + xi_in",
                },
                "feedback": {
                    "enabled": False,
                    "mode": "classical_readout_only",
                },
            },
            "basis_population": {
                "series_labels": ["0", "1"],
                "values": basis_values,
                "state_label": state_label,
                "hidden_state": int(hidden_state),
            },
        }
        return Trajectory(
            engine="qutip",
            times=tlist.astype(float).tolist(),
            classical=classical,
            measurements={"records": shot_records},
            metadata={
                "solver": model_spec.solver_mode,
                "solver_impl": "cavity_classical_readout",
                "model_type": "cavity_classical_readout",
                "num_qubits": 0,
                "num_trajectories": int(ntraj),
                "hidden_state": int(hidden_state),
                "hidden_state_label": state_label,
            },
        )

