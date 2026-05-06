"""Pulse and executable-model intermediate representations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION


@dataclass
class Carrier:
    """Carrier tone parameters for pulse modulation."""

    freq: float
    phase: float = 0.0


@dataclass
class PulseSpec:
    """Single pulse segment scheduled on a channel."""

    t0_s: float
    t1_s: float
    amp: float
    shape: str
    params: dict[str, Any] = field(default_factory=dict)
    carrier: Carrier | None = None

    @property
    def duration_s(self) -> float:
        """Pulse duration in seconds."""
        return float(self.t1_s) - float(self.t0_s)

    @property
    def t0_ns(self) -> float:
        """Pulse start time in nanoseconds."""
        return round(float(self.t0_s) * 1e9, 12)

    @property
    def t1_ns(self) -> float:
        """Pulse end time in nanoseconds."""
        return round(float(self.t1_s) * 1e9, 12)

    @property
    def duration_ns(self) -> float:
        """Pulse duration in nanoseconds."""
        return round(self.duration_s * 1e9, 12)


@dataclass
class ChannelSpec:
    """Collection of pulses for one hardware channel."""

    name: str
    pulses: list[PulseSpec] = field(default_factory=list)


@dataclass
class PulseIR:
    """Pulse-level intermediate representation for one schedule."""

    schema_version: str = SCHEMA_VERSION
    t_end_s: float = 0.0
    channels: list[ChannelSpec] = field(default_factory=list)

    @property
    def t_end_ns(self) -> float:
        """Schedule end time in nanoseconds."""
        return round(float(self.t_end_s) * 1e9, 12)


@dataclass
class ExecutableModel:
    """Lowered executable model before numeric model construction."""

    schema_version: str = SCHEMA_VERSION
    level: str = "qubit"
    solver: str = "se"
    h_terms: list[dict[str, Any]] = field(default_factory=list)
    noise_terms: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


