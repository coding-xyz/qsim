"""Readout-chain postprocessing for cqed task flows."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

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
    try:
        return float(value)
    except Exception:
        return float(default)


def _readout_coupling_prefactor(kappa_ext_hz: float) -> float:
    return math.sqrt(max(0.0, 2.0 * math.pi * float(kappa_ext_hz)))


def _integrate_trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(y, x))
    return float(np.trapz(y, x))


def _extract_readout_windows(pulse_ir) -> list[dict[str, float | str]]:
    windows: list[dict[str, float | str]] = []
    for channel in list(getattr(pulse_ir, "channels", []) or []):
        channel_name = str(getattr(channel, "name", ""))
        if not channel_name.upper().startswith("RO_"):
            continue
        for pulse in list(getattr(channel, "pulses", []) or []):
            shape = str(getattr(pulse, "shape", "")).lower()
            params = dict(getattr(pulse, "params", {}) or {})
            if shape != "readout":
                continue
            if str(params.get("break_stage", "")).strip().lower() != "measure":
                continue
            windows.append(
                {
                    "channel": channel_name,
                    "t0_s": float(getattr(pulse, "t0_s", 0.0)),
                    "t1_s": float(getattr(pulse, "t1_s", 0.0)),
                }
            )
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
    components = list(model_payload.get("components", []) or [])
    connections = list(model_payload.get("connections", []) or [])

    cavity_params: dict[str, Any] = {}
    line_params: dict[str, Any] = {}
    io_params: dict[str, Any] = {}
    for comp in components:
        if not isinstance(comp, dict):
            continue
        comp_type = str(comp.get("type", "")).strip().lower()
        params = dict(comp.get("parameters", {}) or {})
        if comp_type == "resonator" and not cavity_params:
            cavity_params = params
        elif comp_type == "readout_line" and not line_params:
            line_params = params
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        if str(conn.get("type", "")).strip().lower() == "readout_feedline":
            io_params = dict(conn.get("parameters", {}) or {})
            break

    kappa_ext = _safe_float(io_params.get("kappa_ext_Hz", cavity_params.get("kappa_ext_Hz", 0.0)), 0.0)
    kappa_int = _safe_float(cavity_params.get("kappa_int_Hz", 0.0), 0.0)
    eta_chain = _safe_float(io_params.get("eta_chain", line_params.get("eta_chain", 1.0)), 1.0)
    added_noise_photons = _safe_float(line_params.get("added_noise_photons", 0.0), 0.0)
    gain_dB = _safe_float(line_params.get("gain_dB", 0.0), 0.0)
    center_freq_Hz = _safe_float(line_params.get("center_freq_Hz", cavity_params.get("freq_Hz", 0.0)), 0.0)

    return {
        "kappa_ext_Hz": kappa_ext,
        "kappa_int_Hz": kappa_int,
        "eta_chain": eta_chain,
        "added_noise_photons": added_noise_photons,
        "gain_dB": gain_dB,
        "center_freq_Hz": center_freq_Hz,
        "cavity_equation": str(dict(io_params.get("input_output", {}) or {}).get("cavity_equation", "")),
        "output_equation": str(dict(io_params.get("input_output", {}) or {}).get("output_equation", "")),
    }


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
    baseband_source = measured_voltage if measured_voltage.size > 0 else (line_state if line_state.size > 0 else a_out)
    baseband = baseband_source * complex(math.cos(-demod_phase), math.sin(-demod_phase))

    rng = np.random.default_rng(int(seed))
    noise_sigma = max(
        1.0e-4,
        math.sqrt(max(added_noise_photons, 0.0) / eta_chain) * 1.0e-2 + _safe_float(payload.get("noise_cfg", {}).get("readout_error", 0.0), 0.0),
    )
    if measured_voltage.size > 0 or line_state.size > 0:
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
        for idx, window in enumerate(measure_windows):
            label = labels[idx] if idx < len(labels) else f"state_{idx}"
            t0 = float(window["t0_s"]) + start_delay_s
            t1 = min(float(window["t1_s"]), t0 + integration_window_s)
            points: list[complex] = []
            for shot in shot_payloads:
                shot_voltage = _complex_from_pairs(list(shot.get("measured_voltage", []) or []))
                if shot_voltage.size <= 0:
                    continue
                shot_baseband = shot_voltage * complex(math.cos(-demod_phase), math.sin(-demod_phase))
                point = _integrate_window(times, np.real(shot_baseband), np.imag(shot_baseband), t0, t1)
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
            point = _integrate_window(times, i_trace, q_trace, t0, t1)
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
                    "measured_voltage": _complex_pairs(measured_voltage) if measured_voltage.size > 0 else _complex_pairs(baseband_source),
                },
            },
            "feedback": dict(obs.get("feedback", {}) or {}),
            "times": times.astype(float).tolist(),
            "a_in": _complex_pairs(drive),
            "a_cavity": _complex_pairs(cavity_a),
            "a_out": _complex_pairs(a_out),
            "line_state": _complex_pairs(line_state) if line_state.size > 0 else [],
            "measured_voltage": _complex_pairs(measured_voltage) if measured_voltage.size > 0 else _complex_pairs(baseband_source),
            "I": [float(x) for x in i_trace.tolist()],
            "Q": [float(x) for x in q_trace.tolist()],
            "windows": iq_samples,
            "num_shots": len(shot_payloads) if shot_payloads else int(iq_cfg.get("shots", 128) or 128),
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
                "measured_voltage": str((dict(obs.get("equations", {}) or {})).get("measured_voltage", readout_cfg.get("input_output", {}).get("measured_voltage", ""))),
            },
        },
        "iq": {
            "schema_version": "1.0",
            "method": str(iq_cfg.get("method", "nearest_centroid") or "nearest_centroid"),
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

