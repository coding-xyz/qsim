"""Noise schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
@dataclass
class CollapseChannelSpec:
    """Markovian collapse channel."""

    target: int = 0
    kind: str = ""
    rate_Hz: float = 0.0
    rate_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CollapseChannelSpec":
        """Create a collapse channel from a plain dictionary."""
        raw = dict(data or {})
        return cls(
            target=int(raw.get("target", 0) or 0),
            kind=str(raw.get("kind", "") or ""),
            rate_Hz=float(raw.get("rate_Hz", 0.0) or 0.0),
            rate_rad_s=float(raw.get("rate_rad_s", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the collapse channel to a JSON-safe dictionary."""
        return {
            "target": self.target,
            "kind": self.kind,
            "rate_Hz": self.rate_Hz,
            "rate_rad_s": self.rate_rad_s,
        }


@dataclass
class StochasticChannelSpec:
    """Classical stochastic-noise channel parameters for one qubit."""

    q: int = 0
    one_over_f_amp_Hz: float = 0.0
    one_over_f_amp_rad_s: float = 0.0
    one_over_f_fmin: float = 0.0
    one_over_f_fmax: float = 0.0
    one_over_f_exponent: float = 1.0
    ou_sigma_Hz: float = 0.0
    ou_sigma_rad_s: float = 0.0
    ou_tau: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StochasticChannelSpec":
        """Create a stochastic channel from a plain dictionary."""
        raw = dict(data or {})
        return cls(
            q=int(raw.get("q", 0) or 0),
            one_over_f_amp_Hz=float(raw.get("one_over_f_amp_Hz", 0.0) or 0.0),
            one_over_f_amp_rad_s=float(raw.get("one_over_f_amp_rad_s", 0.0) or 0.0),
            one_over_f_fmin=float(raw.get("one_over_f_fmin", 0.0) or 0.0),
            one_over_f_fmax=float(raw.get("one_over_f_fmax", 0.0) or 0.0),
            one_over_f_exponent=float(raw.get("one_over_f_exponent", 1.0) or 1.0),
            ou_sigma_Hz=float(raw.get("ou_sigma_Hz", 0.0) or 0.0),
            ou_sigma_rad_s=float(raw.get("ou_sigma_rad_s", 0.0) or 0.0),
            ou_tau=float(raw.get("ou_tau", 1.0) or 1.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the stochastic channel to a JSON-safe dictionary."""
        return asdict(self)


@dataclass
class PerQubitRateSpec:
    """Resolved per-qubit Markovian rates."""

    q: int = 0
    gamma1_Hz: float = 0.0
    gamma_phi_Hz: float = 0.0
    gamma_up_Hz: float = 0.0
    gamma1_rad_s: float = 0.0
    gamma_phi_rad_s: float = 0.0
    gamma_up_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PerQubitRateSpec":
        """Create per-qubit rate data from a plain dictionary."""
        raw = dict(data or {})
        return cls(
            q=int(raw.get("q", 0) or 0),
            gamma1_Hz=float(raw.get("gamma1_Hz", 0.0) or 0.0),
            gamma_phi_Hz=float(raw.get("gamma_phi_Hz", 0.0) or 0.0),
            gamma_up_Hz=float(raw.get("gamma_up_Hz", 0.0) or 0.0),
            gamma1_rad_s=float(raw.get("gamma1_rad_s", 0.0) or 0.0),
            gamma_phi_rad_s=float(raw.get("gamma_phi_rad_s", 0.0) or 0.0),
            gamma_up_rad_s=float(raw.get("gamma_up_rad_s", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize per-qubit rates to a JSON-safe dictionary."""
        return asdict(self)


@dataclass
class NoiseSpec:
    """Engine-neutral noise model."""

    selected_model: str = "markovian_lindblad"
    readout_error: float = 0.0
    collapse_channels: list[CollapseChannelSpec] = field(default_factory=list)
    stochastic_channels: list[StochasticChannelSpec] = field(default_factory=list)
    per_qubit_rates: list[PerQubitRateSpec] = field(default_factory=list)
    supported: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize nested channel dictionaries into typed specs."""
        self.collapse_channels = [
            ch if isinstance(ch, CollapseChannelSpec) else CollapseChannelSpec.from_dict(ch)
            for ch in list(self.collapse_channels or [])
        ]
        self.stochastic_channels = [
            ch if isinstance(ch, StochasticChannelSpec) else StochasticChannelSpec.from_dict(ch)
            for ch in list(self.stochastic_channels or [])
        ]
        self.per_qubit_rates = [
            item if isinstance(item, PerQubitRateSpec) else PerQubitRateSpec.from_dict(item)
            for item in list(self.per_qubit_rates or [])
        ]


