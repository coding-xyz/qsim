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
    def compile(pulse_ir: PulseIR, sample_rate: float) -> dict[str, dict[str, np.ndarray]]:
        """Sample pulse envelopes by channel at a fixed sample rate."""
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        dt = 1.0 / sample_rate
        channels: dict[str, dict[str, np.ndarray]] = {}

        for ch in pulse_ir.channels:
            t = np.arange(0.0, pulse_ir.t_end + dt, dt)
            y = np.zeros_like(t)
            for p in ch.pulses:
                shape = make_shape(p.shape, p.params)
                for i, ti in enumerate(t):
                    y[i] += shape.sample(float(ti), p.t0, p.t1, p.amp)
            channels[ch.name] = {"t": t, "y": y}
        return channels

    @staticmethod
    def to_npz(samples: dict[str, dict[str, np.ndarray]], out_path: str | Path) -> Path:
        """Save sampled waveforms into a compressed NPZ file."""
        flat: dict[str, np.ndarray] = {}
        for ch, payload in samples.items():
            flat[f"{ch}_t"] = payload["t"]
            flat[f"{ch}_y"] = payload["y"]
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez(out, **flat)
        return out

    @staticmethod
    def pulse_ir_to_dict(pulse_ir: PulseIR) -> dict:
        """Convert ``PulseIR`` dataclass into JSON-friendly dict."""
        return asdict(pulse_ir)
