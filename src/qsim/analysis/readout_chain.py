"""Readout-chain postprocessing for cqed task flows."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qsim.backend.config import normalize_device_config
from qsim.backend.model.lowering import (
    infer_classical_readout_chain,
    readout_coupling_prefactor,
    readout_topology_input,
)
from qsim.common.channels import safe_float
from qsim.pulse.shapes import make_shape


def _complex_pairs(values: np.ndarray) -> list[list[float]]:
    arr = np.asarray(values, dtype=complex).reshape(-1)
    return [[float(v.real), float(v.imag)] for v in arr]


def _complex_from_pairs(values: list[list[float]] | list[float] | None) -> np.ndarray:
    if not values:
        return np.asarray([], dtype=complex)
    if isinstance(values[0], complex):
        return np.asarray(values, dtype=complex).reshape(-1)
    if isinstance(values[0], dict) and "__qsim_complex__" in values[0]:
        return np.asarray(
            [
                complex(float(item["__qsim_complex__"][0]), float(item["__qsim_complex__"][1]))
                for item in values
                if isinstance(item, dict) and "__qsim_complex__" in item
            ],
            dtype=complex,
        ).reshape(-1)
    arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        return arr.astype(complex)
    if arr.shape[-1] < 2:
        return arr.reshape(-1).astype(complex)
    return arr[..., 0].reshape(-1) + 1j * arr[..., 1].reshape(-1)


def _safe_float(value: Any, default: float = 0.0) -> float:
    return safe_float(value, default)


def _readout_coupling_prefactor(kappa_ext_hz: float) -> float:
    return readout_coupling_prefactor(kappa_ext_hz)


def _integrate_trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def _real_list(values: np.ndarray) -> list[float]:
    arr = np.asarray(values, dtype=float).reshape(-1)
    return [float(x) for x in arr]


def _infer_channel_carrier(pulse_ir, channel_name: str) -> tuple[float, float]:
    target = str(channel_name or "").strip()
    if not target:
        return 0.0, 0.0
    for channel in list(getattr(pulse_ir, "channels", []) or []):
        if str(getattr(channel, "name", "")).strip() != target:
            continue
        for pulse in list(getattr(channel, "pulses", []) or []):
            carrier = getattr(pulse, "carrier", None)
            if carrier is None:
                continue
            return (
                _safe_float(getattr(carrier, "freq", 0.0), 0.0),
                _safe_float(getattr(carrier, "phase", 0.0), 0.0),
            )
    return 0.0, 0.0


def _resample_complex(times: np.ndarray, values: np.ndarray, sample_times: np.ndarray) -> np.ndarray:
    if sample_times.size <= 0:
        return np.asarray([], dtype=complex)
    src_t = np.asarray(times, dtype=float).reshape(-1)
    src_v = np.asarray(values, dtype=complex).reshape(-1)
    dst_t = np.asarray(sample_times, dtype=float).reshape(-1)
    if src_t.size <= 0 or src_v.size <= 0:
        return np.zeros(dst_t.size, dtype=complex)
    if src_t.size == dst_t.size and np.allclose(src_t, dst_t):
        return src_v.astype(complex)
    re = np.interp(dst_t, src_t, np.real(src_v), left=0.0, right=0.0)
    im = np.interp(dst_t, src_t, np.imag(src_v), left=0.0, right=0.0)
    return re.astype(complex) + 1j * im.astype(complex)


def _build_sample_times(times: np.ndarray, sample_rate_hz: float) -> np.ndarray:
    src_t = np.asarray(times, dtype=float).reshape(-1)
    if src_t.size <= 1 or sample_rate_hz <= 0.0:
        return src_t
    dt = 1.0 / float(sample_rate_hz)
    t0 = float(src_t[0])
    t1 = float(src_t[-1])
    sample_times = np.arange(t0, t1 + 0.5 * dt, dt, dtype=float)
    if sample_times.size <= 0:
        return np.asarray([t0, t1], dtype=float)
    if sample_times[-1] < t1 - 1.0e-18:
        sample_times = np.append(sample_times, t1)
    return sample_times


def _signed_alias_frequency(freq_hz: float, sample_rate_hz: float) -> float:
    if sample_rate_hz <= 0.0:
        return 0.0
    fs = float(sample_rate_hz)
    return float(((float(freq_hz) + 0.5 * fs) % fs) - 0.5 * fs)


def _receiver_traces(
    *,
    times: np.ndarray,
    complex_envelope: np.ndarray,
    pulse_ir,
    readout_cfg: dict[str, Any],
    pulse_cfg: dict[str, Any],
    chain: dict[str, float | str],
    rng: np.random.Generator,
) -> dict[str, Any]:
    receiver_cfg = dict(readout_cfg.get("receiver", {}) or {})
    channels_cfg = dict(readout_cfg.get("channels", {}) or {})
    mode = str(receiver_cfg.get("mode", "direct_adc") or "direct_adc").strip().lower()
    if mode not in {"direct_adc", "downconversion"}:
        mode = "direct_adc"

    demod_cfg = dict((pulse_cfg.get("acquisition", {}) or {}).get("demodulation", {}) or {})
    cavity_drive_channel = str(channels_cfg.get("cavity_drive", "")) or str(demod_cfg.get("drive_channel", ""))
    lo_channel = str(receiver_cfg.get("lo_channel", channels_cfg.get("local_oscillator", demod_cfg.get("lo_channel", ""))) or "")

    carrier_freq_hz, carrier_phase = _infer_channel_carrier(pulse_ir, cavity_drive_channel)
    lo_freq_hz, lo_phase = _infer_channel_carrier(pulse_ir, lo_channel)
    carrier_freq_hz = _safe_float(
        receiver_cfg.get("carrier_frequency_Hz", carrier_freq_hz if carrier_freq_hz > 0.0 else chain.get("center_freq_Hz", 0.0)),
        _safe_float(chain.get("center_freq_Hz", 0.0), 0.0),
    )
    lo_freq_hz = _safe_float(receiver_cfg.get("lo_frequency_Hz", lo_freq_hz), lo_freq_hz)
    rf_phase = _safe_float(receiver_cfg.get("rf_phase_rad", carrier_phase), carrier_phase)
    if_phase = _safe_float(receiver_cfg.get("if_phase_rad", carrier_phase - lo_phase), carrier_phase - lo_phase)
    digital_lo_phase = _safe_float(receiver_cfg.get("digital_lo_phase_rad", demod_cfg.get("phase_rad", 0.0)), _safe_float(demod_cfg.get("phase_rad", 0.0), 0.0))

    if times.size > 1:
        inferred_rate = 1.0 / max(float(np.mean(np.diff(times))), 1.0e-18)
    else:
        inferred_rate = 0.0
    adc_sample_rate_hz = _safe_float(receiver_cfg.get("adc_sample_rate_Hz", inferred_rate), inferred_rate)
    adc_times = _build_sample_times(times, adc_sample_rate_hz)
    envelope_adc = _resample_complex(times, complex_envelope, adc_times)

    rf_signal = np.real(complex_envelope * np.exp(1j * (2.0 * math.pi * carrier_freq_hz * times + rf_phase)))
    rf_signal_adc = np.real(envelope_adc * np.exp(1j * (2.0 * math.pi * carrier_freq_hz * adc_times + rf_phase)))

    if_frequency_hz = _safe_float(
        receiver_cfg.get("if_frequency_Hz", demod_cfg.get("if_Hz", abs(carrier_freq_hz - lo_freq_hz))),
        abs(carrier_freq_hz - lo_freq_hz),
    )
    if_signal = np.real(complex_envelope * np.exp(1j * (2.0 * math.pi * if_frequency_hz * times + if_phase)))
    if_signal_adc = np.real(envelope_adc * np.exp(1j * (2.0 * math.pi * if_frequency_hz * adc_times + if_phase)))

    sampled_frequency_hz = carrier_freq_hz if mode == "direct_adc" else if_frequency_hz
    sampled_signal = rf_signal_adc if mode == "direct_adc" else if_signal_adc
    rf_noise_sigma = max(0.0, _safe_float(receiver_cfg.get("rf_noise_sigma", 0.0), 0.0))
    adc_noise_sigma = max(0.0, _safe_float(receiver_cfg.get("adc_noise_sigma", 0.0), 0.0))
    if rf_noise_sigma > 0.0:
        sampled_signal = sampled_signal + rng.normal(0.0, rf_noise_sigma, size=adc_times.size)
    adc_signal = sampled_signal + (rng.normal(0.0, adc_noise_sigma, size=adc_times.size) if adc_noise_sigma > 0.0 else 0.0)

    adc_alias_signed_hz = _signed_alias_frequency(sampled_frequency_hz, adc_sample_rate_hz)
    rf_alias_signed_hz = _signed_alias_frequency(carrier_freq_hz, adc_sample_rate_hz)
    digital_baseband = 2.0 * adc_signal.astype(complex) * np.exp(
        -1j * (2.0 * math.pi * adc_alias_signed_hz * adc_times + digital_lo_phase)
    )

    return {
        "mode": mode,
        "adc_times": adc_times.astype(float),
        "adc_sample_rate_Hz": float(adc_sample_rate_hz),
        "complex_envelope": np.asarray(complex_envelope, dtype=complex),
        "complex_envelope_adc": envelope_adc,
        "rf_signal": rf_signal.astype(float),
        "rf_signal_adc": rf_signal_adc.astype(float),
        "if_signal": if_signal.astype(float),
        "if_signal_adc": if_signal_adc.astype(float),
        "adc_signal": np.asarray(adc_signal, dtype=float),
        "digital_baseband": np.asarray(digital_baseband, dtype=complex),
        "carrier_frequency_Hz": float(carrier_freq_hz),
        "lo_frequency_Hz": float(lo_freq_hz),
        "if_frequency_Hz": float(if_frequency_hz),
        "sampled_frequency_Hz": float(sampled_frequency_hz),
        "alias_frequency_Hz": abs(float(adc_alias_signed_hz)),
        "alias_frequency_signed_Hz": float(adc_alias_signed_hz),
        "rf_alias_frequency_Hz": abs(float(rf_alias_signed_hz)),
        "rf_alias_frequency_signed_Hz": float(rf_alias_signed_hz),
        "rf_phase_rad": float(rf_phase),
        "if_phase_rad": float(if_phase),
        "digital_lo_phase_rad": float(digital_lo_phase),
        "adc_noise_sigma": float(adc_noise_sigma),
        "rf_noise_sigma": float(rf_noise_sigma),
        "adc_source": "rf_signal" if mode == "direct_adc" else "if_signal",
    }


def _extract_readout_windows(pulse_ir) -> list[dict[str, float | str]]:
    windows: list[dict[str, float | str]] = []
    for channel in list(getattr(pulse_ir, "channels", []) or []):
        channel_name = str(getattr(channel, "name", ""))
        if not channel_name.upper().startswith("RO_"):
            continue
        pending: dict[str, float | str] | None = None
        for pulse in list(getattr(channel, "pulses", []) or []):
            shape = str(getattr(pulse, "shape", "")).lower()
            params = dict(getattr(pulse, "params", {}) or {})
            if shape != "readout":
                continue
            if str(params.get("break_stage", "")).strip().lower() != "measure":
                continue
            t0 = float(getattr(pulse, "t0_s", 0.0))
            t1 = float(getattr(pulse, "t1_s", 0.0))
            if pending is None:
                pending = {"channel": channel_name, "t0_s": t0, "t1_s": t1}
                continue
            if abs(float(pending["t1_s"]) - t0) <= 1.0e-18:
                pending["t1_s"] = t1
                continue
            windows.append(pending)
            pending = {"channel": channel_name, "t0_s": t0, "t1_s": t1}
        if pending is not None:
            windows.append(pending)
    windows.sort(key=lambda item: float(item["t0_s"]))
    return windows


def _sample_readout_drive(pulse_ir, times: np.ndarray) -> np.ndarray:
    drive = np.zeros_like(times, dtype=complex)
    if times.size <= 0:
        return drive
    for channel in list(getattr(pulse_ir, "channels", []) or []):
        channel_name = str(getattr(channel, "name", ""))
        if not channel_name.upper().startswith("RO_"):
            continue
        for pulse in list(getattr(channel, "pulses", []) or []):
            params = dict(getattr(pulse, "params", {}) or {})
            sampler = make_shape(str(getattr(pulse, "shape", "rect")), params)
            amp = float(getattr(pulse, "amp", 0.0))
            t0 = float(getattr(pulse, "t0_s", 0.0))
            t1 = float(getattr(pulse, "t1_s", 0.0))
            carrier = getattr(pulse, "carrier", None)
            phase = float(getattr(carrier, "phase", 0.0)) if carrier is not None else 0.0
            phase_factor = complex(math.cos(phase), math.sin(phase))
            env = np.asarray([sampler.sample(float(t), t0, t1, amp) for t in times], dtype=float)
            drive = drive + env.astype(complex) * phase_factor
    return drive


def _infer_chain_params(model_payload: dict[str, Any]) -> dict[str, float | str]:
    device = normalize_device_config(
        {
            "components": list(model_payload.get("components", []) or []),
            "connections": list(model_payload.get("connections", []) or []),
        }
    )
    topology = readout_topology_input(
        device.components,
        device.connections,
        primary_step=dict(model_payload.get("primary_step", {}) or {}),
        readout_chain=dict(model_payload.get("readout_chain", {}) or {}),
    )
    return infer_classical_readout_chain(topology)


def _nearest_centroid(point: complex, centroids: dict[str, complex]) -> str:
    if not centroids:
        return ""
    return min(centroids, key=lambda label: abs(point - centroids[label]))


def _integrate_window(times: np.ndarray, i_trace: np.ndarray, q_trace: np.ndarray, t0: float, t1: float) -> complex | None:
    mask = (times >= t0) & (times <= t1)
    if not np.any(mask):
        return None
    t_sel = times[mask]
    i_sel = i_trace[mask]
    q_sel = q_trace[mask]
    if t_sel.size == 1:
        return complex(float(i_sel[0]), float(q_sel[0]))
    span = max(float(t_sel[-1] - t_sel[0]), 1.0e-18)
    i_int = _integrate_trapezoid(i_sel, t_sel) / span
    q_int = _integrate_trapezoid(q_sel, t_sel) / span
    return complex(i_int, q_int)


def _shot_complex_trace(shot: dict[str, Any]) -> np.ndarray:
    measured_voltage = _complex_from_pairs(list(shot.get("measured_voltage", []) or []))
    if measured_voltage.size > 0:
        return measured_voltage
    heterodyne_current = _complex_from_pairs(list(shot.get("heterodyne_current", []) or []))
    if heterodyne_current.size > 0:
        return heterodyne_current
    i_vals = list(shot.get("heterodyne_I", []) or [])
    q_vals = list(shot.get("heterodyne_Q", []) or [])
    if i_vals or q_vals:
        i_arr = np.asarray(i_vals, dtype=float).reshape(-1)
        q_arr = np.asarray(q_vals, dtype=float).reshape(-1)
        size = min(i_arr.size, q_arr.size) if i_arr.size and q_arr.size else max(i_arr.size, q_arr.size)
        if size <= 0:
            return np.asarray([], dtype=complex)
        if i_arr.size < size:
            i_arr = np.pad(i_arr, (0, size - i_arr.size))
        if q_arr.size < size:
            q_arr = np.pad(q_arr, (0, size - q_arr.size))
        return i_arr.astype(complex) + 1j * q_arr.astype(complex)
    return np.asarray([], dtype=complex)


def build_readout_analysis(
    *,
    trajectory,
    model_spec,
    pulse_ir,
    pulse_cfg: dict[str, Any] | None,
    analyser_cfg: dict[str, Any] | None,
    seed: int,
) -> dict[str, dict[str, Any]]:
    """Build readout-chain and IQ-classification analysis payloads."""
    analyser_cfg = dict(analyser_cfg or {})
    pulse_cfg = dict(pulse_cfg or {})
    readout_cfg = dict(analyser_cfg.get("readout_model", {}) or {})
    iq_cfg = dict(analyser_cfg.get("iq_discrimination", {}) or {})
    noise_cfg = dict(analyser_cfg.get("noise_analysis", {}) or {})
    if not readout_cfg and not iq_cfg and not noise_cfg:
        return {}

    payload = dict(getattr(model_spec, "payload", {}) or {})
    obs = dict((getattr(trajectory, "classical", {}) or {}).get("readout", {}) or {})
    times = np.asarray(list(getattr(trajectory, "times", []) or []), dtype=float)
    a_in_obs = _complex_from_pairs(list(obs.get("a_in", []) or []))
    cavity_a = _complex_from_pairs(list(obs.get("cavity_a", []) or []))
    a_out_obs = _complex_from_pairs(list(obs.get("a_out", []) or []))
    line_state = _complex_from_pairs(list(obs.get("line_state", []) or []))
    measured_voltage = _complex_from_pairs(list(obs.get("measured_voltage", []) or []))
    shot_payloads = [dict(item) for item in list(obs.get("shots", []) or []) if isinstance(item, dict)]
    if times.size <= 0 or cavity_a.size <= 0:
        return {}

    drive = a_in_obs if a_in_obs.size > 0 else _sample_readout_drive(pulse_ir, times)
    chain = _infer_chain_params(payload)
    chain.update(dict(obs.get("chain", {}) or {}))
    eta_chain = max(1.0e-6, _safe_float(chain.get("eta_chain", 1.0), 1.0))
    added_noise_photons = max(0.0, _safe_float(chain.get("added_noise_photons", 0.0), 0.0))
    coupling_scale = _readout_coupling_prefactor(_safe_float(chain.get("kappa_ext_Hz", 0.0), 0.0))

    a_out = a_out_obs if a_out_obs.size > 0 else (drive - coupling_scale * cavity_a)

    demod_cfg = dict((pulse_cfg.get("acquisition", {}) or {}).get("demodulation", {}) or {})
    demod_phase = _safe_float(demod_cfg.get("phase_rad", 0.0), 0.0)
    if_Hz = _safe_float(demod_cfg.get("if_Hz", 0.0), 0.0)
    heterodyne_current = _complex_from_pairs(list(obs.get("heterodyne_current", []) or []))
    baseband_source = measured_voltage if measured_voltage.size > 0 else (heterodyne_current if heterodyne_current.size > 0 else (line_state if line_state.size > 0 else a_out))
    lo = np.exp(1j * (2.0 * math.pi * if_Hz * times + demod_phase)) if times.size > 0 else np.asarray([], dtype=complex)
    ro_line_if = baseband_source * lo if lo.size > 0 else np.asarray(baseband_source, dtype=complex)
    baseband = baseband_source * complex(math.cos(-demod_phase), math.sin(-demod_phase))

    rng = np.random.default_rng(int(seed))
    noise_sigma = max(
        1.0e-4,
        math.sqrt(max(added_noise_photons, 0.0) / eta_chain) * 1.0e-2 + _safe_float(payload.get("noise_cfg", {}).get("readout_error", 0.0), 0.0),
    )
    receiver = _receiver_traces(
        times=times,
        complex_envelope=baseband_source,
        pulse_ir=pulse_ir,
        readout_cfg=readout_cfg,
        pulse_cfg=pulse_cfg,
        chain=chain,
        rng=rng,
    )
    adc_times = np.asarray(receiver.get("adc_times", times), dtype=float)
    adc_signal = np.asarray(receiver.get("adc_signal", []), dtype=float)
    digital_baseband = np.asarray(receiver.get("digital_baseband", []), dtype=complex)
    if digital_baseband.size > 0:
        i_trace = np.real(digital_baseband)
        q_trace = np.imag(digital_baseband)
    elif measured_voltage.size > 0 or line_state.size > 0:
        i_trace = np.real(baseband)
        q_trace = np.imag(baseband)
    else:
        i_trace = np.real(baseband) + rng.normal(0.0, noise_sigma, size=times.size)
        q_trace = np.imag(baseband) + rng.normal(0.0, noise_sigma, size=times.size)

    measure_windows = _extract_readout_windows(pulse_ir)
    integration_window_s = _safe_float((pulse_cfg.get("acquisition", {}) or {}).get("integration_window_ns", 0.0), 0.0) * 1.0e-9
    start_delay_s = _safe_float((pulse_cfg.get("acquisition", {}) or {}).get("start_delay_ns", 0.0), 0.0) * 1.0e-9
    if integration_window_s <= 0.0:
        integration_window_s = _safe_float(pulse_cfg.get("measure_duration_ns", 0.0), 0.0) * 1.0e-9

    calibration = list(iq_cfg.get("calibration_states", []) or [])
    labels = [str(item.get("label", f"state_{idx}")) for idx, item in enumerate(calibration)] if calibration else []
    if not labels:
        labels = [f"state_{idx}" for idx in range(len(measure_windows))]

    iq_samples: list[dict[str, Any]] = []
    centroids: dict[str, complex] = {}
    actual_clouds: dict[str, list[list[float]]] = {}
    if shot_payloads:
        window_points: dict[str, list[complex]] = {}
        shot_views: list[dict[str, Any]] = []
        for shot_index, shot in enumerate(shot_payloads):
            shot_voltage = _shot_complex_trace(shot)
            if shot_voltage.size <= 0:
                continue
            shot_receiver = _receiver_traces(
                times=times,
                complex_envelope=shot_voltage,
                pulse_ir=pulse_ir,
                readout_cfg=readout_cfg,
                pulse_cfg=pulse_cfg,
                chain=chain,
                rng=np.random.default_rng(int(seed) + shot_index + 1),
            )
            shot_views.append(
                {
                    "trajectory_index": shot_index,
                    "complex_envelope": _complex_pairs(np.asarray(shot_voltage, dtype=complex)),
                    "adc_times": _real_list(np.asarray(shot_receiver.get("adc_times", []), dtype=float)),
                    "adc_signal": _real_list(np.asarray(shot_receiver.get("adc_signal", []), dtype=float)),
                    "digital_baseband": _complex_pairs(np.asarray(shot_receiver.get("digital_baseband", []), dtype=complex)),
                    "alias_frequency_Hz": float(shot_receiver.get("alias_frequency_Hz", 0.0)),
                    "alias_frequency_signed_Hz": float(shot_receiver.get("alias_frequency_signed_Hz", 0.0)),
                }
            )
        for idx, window in enumerate(measure_windows):
            label = labels[idx] if idx < len(labels) else f"state_{idx}"
            t0 = float(window["t0_s"]) + start_delay_s
            t1 = min(float(window["t1_s"]), t0 + integration_window_s)
            points: list[complex] = []
            for shot_view in shot_views:
                shot_baseband = _complex_from_pairs(list(shot_view.get("digital_baseband", []) or []))
                shot_times = np.asarray(list(shot_view.get("adc_times", []) or []), dtype=float)
                if shot_baseband.size <= 0 or shot_times.size <= 0:
                    continue
                point = _integrate_window(shot_times, np.real(shot_baseband), np.imag(shot_baseband), t0, t1)
                if point is not None:
                    points.append(point)
            if not points:
                continue
            window_points[label] = points
            center = sum(points) / float(len(points))
            centroids[label] = center
            actual_clouds[label] = [[float(p.real), float(p.imag)] for p in points]
            iq_samples.append(
                {
                    "label": label,
                    "channel": window["channel"],
                    "window_s": {"t0": t0, "t1": t1},
                    "integrated_iq": [float(center.real), float(center.imag)],
                }
            )
        labels = [item["label"] for item in iq_samples]
        confusion = np.zeros((len(labels), len(labels)), dtype=int)
        for i, label in enumerate(labels):
            for point in window_points.get(label, []):
                pred = _nearest_centroid(point, centroids)
                if pred in labels:
                    confusion[i, labels.index(pred)] += 1
        synthetic_clouds = actual_clouds
    else:
        for idx, window in enumerate(measure_windows):
            label = labels[idx] if idx < len(labels) else f"state_{idx}"
            t0 = float(window["t0_s"]) + start_delay_s
            t1 = min(float(window["t1_s"]), t0 + integration_window_s)
            point = _integrate_window(adc_times if adc_times.size > 0 else times, i_trace, q_trace, t0, t1)
            if point is None:
                continue
            centroids[label] = point
            iq_samples.append(
                {
                    "label": label,
                    "channel": window["channel"],
                    "window_s": {"t0": t0, "t1": t1},
                    "integrated_iq": [float(point.real), float(point.imag)],
                }
            )

        labels = [item["label"] for item in iq_samples]
        shots = int(iq_cfg.get("shots", 128) or 128)
        synthetic_clouds = {}
        confusion = np.zeros((len(labels), len(labels)), dtype=int)
        for i, label in enumerate(labels):
            center = centroids[label]
            points: list[list[float]] = []
            for _ in range(max(1, shots)):
                point = center + complex(rng.normal(0.0, noise_sigma), rng.normal(0.0, noise_sigma))
                pred = _nearest_centroid(point, centroids)
                if pred in labels:
                    confusion[i, labels.index(pred)] += 1
                points.append([float(point.real), float(point.imag)])
            synthetic_clouds[label] = points

    assignment_fidelity = float(np.trace(confusion) / max(1, confusion.sum())) if confusion.size else 0.0
    pairwise_distances = [
        abs(centroids[a] - centroids[b])
        for i, a in enumerate(labels)
        for b in labels[i + 1 :]
    ]
    cluster_separation = float(min(pairwise_distances) / max(noise_sigma, 1.0e-12)) if pairwise_distances else 0.0
    snr = float((np.mean(pairwise_distances) if pairwise_distances else 0.0) / max(2.0 * noise_sigma, 1.0e-12))

    return {
        "readout": {
            "schema_version": "1.0",
            "mode": str(readout_cfg.get("mode", "input_output_v1") or "input_output_v1"),
            "signals": {
                "quantum": {
                    "cavity_a": _complex_pairs(cavity_a),
                    "cavity_n": [float(x) for x in list(obs.get("cavity_n", []) or [])],
                    "qubit_lowering": list(obs.get("qubit_lowering", []) or []),
                },
                "io_chain": {
                    "a_in": _complex_pairs(drive),
                    "a_out": _complex_pairs(a_out),
                    "line_state": _complex_pairs(line_state) if line_state.size > 0 else [],
                    "heterodyne_current": _complex_pairs(heterodyne_current) if heterodyne_current.size > 0 else [],
                    "ro_line_if": _complex_pairs(ro_line_if),
                    "complex_envelope": _complex_pairs(np.asarray(receiver.get("complex_envelope", baseband_source), dtype=complex)),
                    "rf_signal": _real_list(np.asarray(receiver.get("rf_signal", []), dtype=float)),
                    "if_signal": _real_list(np.asarray(receiver.get("if_signal", []), dtype=float)),
                    "adc_signal": _real_list(np.asarray(receiver.get("adc_signal", []), dtype=float)),
                },
            },
            "feedback": dict(obs.get("feedback", {}) or {}),
            "times": times.astype(float).tolist(),
            "adc_times": _real_list(adc_times),
            "a_in": _complex_pairs(drive),
            "a_cavity": _complex_pairs(cavity_a),
            "a_out": _complex_pairs(a_out),
            "line_state": _complex_pairs(line_state) if line_state.size > 0 else [],
            "heterodyne_current": _complex_pairs(heterodyne_current) if heterodyne_current.size > 0 else [],
            "ro_line_if": _complex_pairs(ro_line_if),
            "complex_envelope": _complex_pairs(np.asarray(receiver.get("complex_envelope", baseband_source), dtype=complex)),
            "rf_signal": _real_list(np.asarray(receiver.get("rf_signal", []), dtype=float)),
            "if_signal": _real_list(np.asarray(receiver.get("if_signal", []), dtype=float)),
            "adc_signal": _real_list(np.asarray(receiver.get("adc_signal", []), dtype=float)),
            "demodulated_voltage": _complex_pairs(digital_baseband if digital_baseband.size > 0 else baseband),
            "I": [float(x) for x in i_trace.tolist()],
            "Q": [float(x) for x in q_trace.tolist()],
            "windows": iq_samples,
            "num_shots": len(shot_payloads) if shot_payloads else int(iq_cfg.get("shots", 128) or 128),
            "receiver": {
                "mode": str(receiver.get("mode", "direct_adc")),
                "adc_sample_rate_Hz": _safe_float(receiver.get("adc_sample_rate_Hz", 0.0), 0.0),
                "carrier_frequency_Hz": _safe_float(receiver.get("carrier_frequency_Hz", 0.0), 0.0),
                "lo_frequency_Hz": _safe_float(receiver.get("lo_frequency_Hz", 0.0), 0.0),
                "if_frequency_Hz": _safe_float(receiver.get("if_frequency_Hz", 0.0), 0.0),
                "sampled_frequency_Hz": _safe_float(receiver.get("sampled_frequency_Hz", 0.0), 0.0),
                "alias_frequency_Hz": _safe_float(receiver.get("alias_frequency_Hz", 0.0), 0.0),
                "alias_frequency_signed_Hz": _safe_float(receiver.get("alias_frequency_signed_Hz", 0.0), 0.0),
                "rf_alias_frequency_Hz": _safe_float(receiver.get("rf_alias_frequency_Hz", 0.0), 0.0),
                "rf_alias_frequency_signed_Hz": _safe_float(receiver.get("rf_alias_frequency_signed_Hz", 0.0), 0.0),
                "adc_noise_sigma": _safe_float(receiver.get("adc_noise_sigma", 0.0), 0.0),
                "rf_noise_sigma": _safe_float(receiver.get("rf_noise_sigma", 0.0), 0.0),
                "adc_source": str(receiver.get("adc_source", "rf_signal")),
            },
            "chain": {
                "kappa_ext_Hz": _safe_float(chain.get("kappa_ext_Hz", 0.0), 0.0),
                "kappa_int_Hz": _safe_float(chain.get("kappa_int_Hz", 0.0), 0.0),
                "eta_chain": eta_chain,
                "gain_dB": _safe_float(chain.get("gain_dB", 0.0), 0.0),
                "added_noise_photons": added_noise_photons,
                "center_freq_Hz": _safe_float(chain.get("center_freq_Hz", 0.0), 0.0),
            },
            "equations": {
                "cavity": str(readout_cfg.get("input_output", {}).get("cavity_equation", chain.get("cavity_equation", ""))),
                "output": str((dict(obs.get("equations", {}) or {})).get("a_out", readout_cfg.get("input_output", {}).get("output_equation", chain.get("output_equation", "")))),
                "line_state": str((dict(obs.get("equations", {}) or {})).get("line_state", "")),
                "quantum_drive": str((dict(obs.get("equations", {}) or {})).get("quantum_drive", "")),
                "complex_envelope": str((dict(obs.get("equations", {}) or {})).get("measured_voltage", readout_cfg.get("input_output", {}).get("measured_voltage", ""))),
                "heterodyne_current": str((dict(obs.get("equations", {}) or {})).get("heterodyne_current", "")),
                "demodulation": "v_bb(t) = v_if(t) * exp(-i (2*pi*if_Hz*t + phase_rad))",
                "rf_reconstruction": "v_rf(t) = Re{v_env(t) * exp(i*(2*pi*f_carrier*t + phi_rf))}",
                "adc_sampling": "v_adc[n] = v_sampled(t_n) + n_adc[n], t_n = n / f_s",
            },
            "demodulation": {
                "phase_rad": demod_phase,
                "if_Hz": if_Hz,
                "source": "complex_envelope" if measured_voltage.size > 0 else ("heterodyne_current" if heterodyne_current.size > 0 else ("line_state" if line_state.size > 0 else "a_out")),
            },
            "shots": shot_views if shot_payloads else [],
        },
        "iq": {
            "schema_version": "1.0",
            "method": str(iq_cfg.get("method", "nearest_centroid") or "nearest_centroid"),
            "integration": {
                "mode": str(iq_cfg.get("integration_mode", "uniform_window") or "uniform_window"),
                "window_ns": integration_window_s * 1.0e9,
                "start_delay_ns": start_delay_s * 1.0e9,
            },
            "labels": labels,
            "samples": iq_samples,
            "centroids": {label: [float(val.real), float(val.imag)] for label, val in centroids.items()},
            "synthetic_clouds": synthetic_clouds,
            "confusion_matrix": {
                "labels": labels,
                "values": confusion.astype(int).tolist(),
            },
            "assignment_fidelity": assignment_fidelity,
            "noise_sigma": float(noise_sigma),
            "cluster_separation": cluster_separation,
            "snr": snr,
            "num_shots": len(shot_payloads) if shot_payloads else int(iq_cfg.get("shots", 128) or 128),
        },
    }


__all__ = ["build_readout_analysis"]

