"""Pulse-sequence compilation utilities."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import numpy as np

from qsim.common.schemas import PulseIR
from qsim.pulse.shapes import make_shape


class PulseCompiler:
    """Compile pulse IR into uniformly sampled channel waveforms."""

    @staticmethod
    def compile(pulse_ir: PulseIR, sample_rate_Hz: float) -> dict[str, dict[str, np.ndarray]]:
        """Sample pulse envelopes by channel at a fixed sample rate in Hz."""
        if sample_rate_Hz <= 0:
            raise ValueError("sample_rate_Hz must be positive")
        dt_s = 1.0 / sample_rate_Hz
        channels: dict[str, dict[str, np.ndarray]] = {}

        for ch in pulse_ir.channels:
            t = np.arange(0.0, pulse_ir.t_end_s + dt_s, dt_s)
            y = np.zeros_like(t)
            y_quadrature = np.zeros_like(t)
            has_quadrature = False
            carrier_freq_Hz = 0.0
            for p in ch.pulses:
                shape = make_shape(p.shape, p.params)
                if p.carrier is not None and carrier_freq_Hz == 0.0:
                    carrier_freq_Hz = float(p.carrier.freq)
                phase = float(p.carrier.phase) if p.carrier is not None else 0.0
                cos_phase = float(np.cos(phase))
                sin_phase = float(np.sin(phase))
                for i, ti in enumerate(t):
                    if hasattr(shape, "quadratures"):
                        i_env, q_env = shape.quadratures(float(ti), p.t0_s, p.t1_s, p.amp)
                        y[i] += i_env * cos_phase - q_env * sin_phase
                        y_quadrature[i] += i_env * sin_phase + q_env * cos_phase
                        has_quadrature = has_quadrature or (q_env != 0.0)
                    else:
                        env = shape.sample(float(ti), p.t0_s, p.t1_s, p.amp)
                        y[i] += env * cos_phase
                        y_quadrature[i] += env * sin_phase
                        has_quadrature = has_quadrature or (abs(env * sin_phase) > 0.0)
            payload = {
                "t": t,
                "y": y,
                "carrier_freq_Hz": np.asarray([carrier_freq_Hz], dtype=float),
                "carrier_phase_rad": np.asarray([0.0], dtype=float),
            }
            if has_quadrature:
                payload["y_quadrature"] = y_quadrature
            channels[ch.name] = payload
        return channels

    @staticmethod
    def to_npz(samples: dict[str, dict[str, np.ndarray]], out_path: str | Path) -> Path:
        """Save sampled waveforms into a compressed NPZ file."""
        flat: dict[str, np.ndarray] = {}
        for ch, payload in samples.items():
            flat[f"{ch}_t"] = payload["t"]
            flat[f"{ch}_y"] = payload["y"]
            if "y_quadrature" in payload:
                flat[f"{ch}_y_quadrature"] = payload["y_quadrature"]
            if "carrier_freq_Hz" in payload:
                flat[f"{ch}_carrier_freq_Hz"] = payload["carrier_freq_Hz"]
            if "carrier_phase_rad" in payload:
                flat[f"{ch}_carrier_phase_rad"] = payload["carrier_phase_rad"]
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(out, **flat)
        return out

    @staticmethod
    def pulse_ir_to_dict(pulse_ir: PulseIR) -> dict:
        """Convert ``PulseIR`` dataclass into JSON-friendly dict."""
        return asdict(pulse_ir)
