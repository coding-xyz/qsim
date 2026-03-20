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
            carrier_freq_Hz = 0.0
            carrier_phase_rad = 0.0
            for p in ch.pulses:
                shape = make_shape(p.shape, p.params)
                if p.carrier is not None and carrier_freq_Hz == 0.0:
                    carrier_freq_Hz = float(p.carrier.freq)
                    carrier_phase_rad = float(p.carrier.phase)
                for i, ti in enumerate(t):
                    y[i] += shape.sample(float(ti), p.t0_s, p.t1_s, p.amp)
            channels[ch.name] = {
                "t": t,
                "y": y,
                "carrier_freq_Hz": np.asarray([carrier_freq_Hz], dtype=float),
                "carrier_phase_rad": np.asarray([carrier_phase_rad], dtype=float),
            }
        return channels

    @staticmethod
    def to_npz(samples: dict[str, dict[str, np.ndarray]], out_path: str | Path) -> Path:
        """Save sampled waveforms into a compressed NPZ file."""
        flat: dict[str, np.ndarray] = {}
        for ch, payload in samples.items():
            flat[f"{ch}_t"] = payload["t"]
            flat[f"{ch}_y"] = payload["y"]
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
