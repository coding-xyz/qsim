"""Solver, time-grid, and frame schema for model specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
@dataclass
class SolverSpec:
    """Solver selection and numerical run controls.

    ``mode`` selects the mathematical solver family. ``engine`` is optional
    because a ``ModelSpec`` can be inspected or serialized before a concrete
    backend is selected.
    """

    mode: str = "se"
    engine: str | None = None
    seed: int | None = None
    ntraj: int | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        """Return the solver mode for compatibility with string-based callers."""
        return str(self.mode)


@dataclass
class TimeSpec:
    """Simulation time-grid request in seconds."""

    dt_s: float = 1.0
    t_end_s: float = 0.0
    t_padding_s: float = 0.0


@dataclass
class FrameSpec:
    """Reference-frame and rotating-wave approximation configuration."""

    mode: str = "rotating"
    reference: str = "pulse_carrier"
    rwa: bool = True
    qubit_reference_freqs_Hz: list[float] = field(default_factory=list)
    qubit_reference_omega_rad_s: list[float] = field(default_factory=list)
    pulse_carrier_reference_freqs_Hz: list[float] = field(default_factory=list)
    pulse_carrier_reference_omega_rad_s: list[float] = field(default_factory=list)


