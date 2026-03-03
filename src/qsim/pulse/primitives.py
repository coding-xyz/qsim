"""Primitive pulse sample containers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WaveformSamples:
    """Uniformly sampled waveform payload for one channel."""

    times: list[float]
    values: list[float]
