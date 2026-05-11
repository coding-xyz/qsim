"""Noise schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float, falling back to a default if None.

    Args:
        value (Any): Value to convert.
        default (float): Default value if input is None. Defaults to 0.0.

    Returns:
        float: Converted float value.
    """
    return float(default if value is None else value)


def _as_str_list(value: Any) -> list[str]:
    """Convert a value or collection to a list of strings.

    Args:
        value (Any): Input value (None, str, int, or iterable).

    Returns:
        list[str]: List of strings.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, int):
        return [str(value)]
    return [str(item) for item in list(value or [])]


def _as_int_list(value: Any) -> list[int]:
    """Convert a value or collection to a list of integers.

    Args:
        value (Any): Input value (None, str, int, or iterable).

    Returns:
        list[int]: List of integers.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [int(value)]
    if isinstance(value, int):
        return [int(value)]
    return [int(item) for item in list(value or [])]


@dataclass
class NoiseSourceSpec:
    """Authored, engine-neutral stochastic or Markovian noise source.

    Attributes:
        id: Unique identifier for the noise source. Defaults to "".
        kind: Type of noise (e.g., "markovian", "stochastic"). Defaults to "".
        targets: List of subsystem IDs affected by this noise.
        operator: Symbolic operator associated with the noise. Defaults to "".
        amplitude: Numerical amplitude of the noise.
        rate: Transition rate or decay rate.
        spectrum: Spectral density information.
        band_Hz: Frequency band limits in Hz.
        exponent: Spectral exponent (e.g., for 1/f noise).
        psd_convention: Power Spectral Density convention used. Defaults to "".
        correlation: Correlation parameters between sources.
        units: Units for the noise parameters.
        realization_hints: Hints for the engine to generate specific noise realizations.
        metadata: Non-primary technical annotations.
    """

    id: str = ""
    kind: str = ""
    targets: list[str] = field(default_factory=list)
    operator: str = ""
    amplitude: dict[str, Any] = field(default_factory=dict)
    rate: dict[str, Any] = field(default_factory=dict)
    spectrum: dict[str, Any] = field(default_factory=dict)
    band_Hz: list[float] = field(default_factory=list)
    exponent: float | None = None
    psd_convention: str = ""
    correlation: dict[str, Any] = field(default_factory=dict)
    units: dict[str, Any] = field(default_factory=dict)
    realization_hints: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NoiseSourceSpec":
        """Create an authored noise source from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing noise source fields.

        Returns:
            NoiseSourceSpec: A typed noise source specification.
        """
        raw = dict(data or {})
        band = raw.get("band_Hz", [])
        if band is None:
            band = []
        return cls(
            id=str(raw.get("id", "") or ""),
            kind=str(raw.get("kind", raw.get("model", "")) or ""),
            targets=_as_str_list(raw.get("targets", raw.get("target"))),
            operator=str(raw.get("operator", "") or ""),
            amplitude=dict(raw.get("amplitude", {}) or {}),
            rate=dict(raw.get("rate", {}) or {}),
            spectrum=dict(raw.get("spectrum", {}) or {}),
            band_Hz=[float(x) for x in list(band or [])],
            exponent=None if raw.get("exponent") is None else float(raw.get("exponent")),
            psd_convention=str(raw.get("psd_convention", "") or ""),
            correlation=dict(raw.get("correlation", {}) or {}),
            units=dict(raw.get("units", {}) or {}),
            realization_hints=dict(raw.get("realization_hints", {}) or {}),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the source to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the noise source.
        """
        return asdict(self)


@dataclass
class ControlCrosstalkSpec:
    """Device-level control-channel transfer or leakage specification.

    Attributes:
        id: Unique identifier for the crosstalk entry. Defaults to "".
        kind: Type of crosstalk (e.g., "deterministic_control_transfer"). Defaults to "deterministic_control_transfer".
        source_channel: The channel where the signal originates. Defaults to "".
        target_channel: The channel where the signal leaks into. Defaults to "".
        transfer: Transfer function or coefficient describing the leakage.
        metadata: Non-primary technical annotations.
    """

    id: str = ""
    kind: str = "deterministic_control_transfer"
    source_channel: str = ""
    target_channel: str = ""
    transfer: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ControlCrosstalkSpec":
        """Create a crosstalk spec from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary.

        Returns:
            ControlCrosstalkSpec: A typed crosstalk specification.
        """
        raw = dict(data or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            kind=str(raw.get("kind", "deterministic_control_transfer") or "deterministic_control_transfer"),
            source_channel=str(raw.get("source_channel", "") or ""),
            target_channel=str(raw.get("target_channel", "") or ""),
            transfer=dict(raw.get("transfer", {}) or {}),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the crosstalk spec to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the crosstalk spec.
        """
        return asdict(self)


@dataclass
class ReadoutCrosstalkSpec:
    """Device-level readout crosstalk or assignment-correlation specification.

    Attributes:
        id: Unique identifier for the readout crosstalk entry. Defaults to "".
        kind: Type of readout crosstalk. Defaults to "".
        source: Source of the crosstalk (e.g., a specific qubit). Defaults to "".
        target: Target of the crosstalk. Defaults to "".
        probability: Probability matrix or values for misassignment.
        transfer: Transfer characteristics of the crosstalk.
        metadata: Non-primary technical annotations.
    """

    id: str = ""
    kind: str = ""
    source: str = ""
    target: str = ""
    probability: dict[str, Any] = field(default_factory=dict)
    transfer: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutCrosstalkSpec":
        """Create a readout crosstalk spec from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary.

        Returns:
            ReadoutCrosstalkSpec: A typed readout crosstalk specification.
        """
        raw = dict(data or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            kind=str(raw.get("kind", "") or ""),
            source=str(raw.get("source", "") or ""),
            target=str(raw.get("target", "") or ""),
            probability=dict(raw.get("probability", {}) or {}),
            transfer=dict(raw.get("transfer", {}) or {}),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the readout crosstalk spec to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the readout crosstalk spec.
        """
        return asdict(self)


@dataclass
class CollapseChannelSpec:
    """Markovian collapse channel.

    Attributes:
        target: Index of the target subsystem. Defaults to 0.
        kind: Type of the collapse channel (e.g., "relaxation", "dephasing"). Defaults to "".
        rate_Hz: Collapse rate in Hz. Defaults to 0.0.
        rate_rad_s: Collapse rate in rad/s. Defaults to 0.0.
    """

    target: int = 0
    kind: str = ""
    rate_Hz: float = 0.0
    rate_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CollapseChannelSpec":
        """Create a collapse channel from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing channel fields.

        Returns:
            CollapseChannelSpec: A typed collapse channel specification.
        """
        raw = dict(data or {})
        return cls(
            target=int(raw.get("target", 0) or 0),
            kind=str(raw.get("kind", "") or ""),
            rate_Hz=float(raw.get("rate_Hz", 0.0) or 0.0),
            rate_rad_s=float(raw.get("rate_rad_s", 0.0) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the collapse channel to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the collapse channel.
        """
        return {
            "target": self.target,
            "kind": self.kind,
            "rate_Hz": self.rate_Hz,
            "rate_rad_s": self.rate_rad_s,
        }


@dataclass
class StochasticChannelSpec:
    """Classical stochastic-noise channel parameters for one qubit.

    Attributes:
        q: Index of the target qubit. Defaults to 0.
        id: Unique identifier for the stochastic channel. Defaults to "".
        kind: Type of stochastic noise model. Defaults to "".
        targets: List of target indices. Defaults to an empty list.
        operator: Symbolic operator associated with the noise. Defaults to "sigma_z_over_2".
        correlation: Correlation parameters.
        one_over_f_amp_Hz: Amplitude of 1/f noise in Hz. Defaults to 0.0.
        one_over_f_amp_rad_s: Amplitude of 1/f noise in rad/s. Defaults to 0.0.
        one_over_f_fmin: Minimum frequency for 1/f noise. Defaults to 0.0.
        one_over_f_fmax: Maximum frequency for 1/f noise. Defaults to 0.0.
        one_over_f_exponent: Spectral exponent for 1/f noise. Defaults to 1.0.
        ou_sigma_Hz: Ornstein-Uhlenbeck noise amplitude in Hz. Defaults to 0.0.
        ou_sigma_rad_s: Ornstein-Uhlenbeck noise amplitude in rad/s. Defaults to 0.0.
        ou_tau: Ornstein-Uhlenbeck correlation time. Defaults to 1.0.
    """

    q: int = 0
    id: str = ""
    kind: str = ""
    targets: list[int] = field(default_factory=list)
    operator: str = "sigma_z_over_2"
    correlation: dict[str, Any] = field(default_factory=dict)
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
        """Create a stochastic channel from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing channel fields.

        Returns:
            StochasticChannelSpec: A typed stochastic channel specification.
        """
        raw = dict(data or {})
        targets = _as_int_list(raw.get("targets"))
        return cls(
            q=int(raw.get("q", 0) or 0),
            id=str(raw.get("id", "") or ""),
            kind=str(raw.get("kind", raw.get("model", "")) or ""),
            targets=targets,
            operator=str(raw.get("operator", "sigma_z_over_2") or "sigma_z_over_2"),
            correlation=dict(raw.get("correlation", {}) or {}),
            one_over_f_amp_Hz=_as_float(raw.get("one_over_f_amp_Hz"), 0.0),
            one_over_f_amp_rad_s=_as_float(raw.get("one_over_f_amp_rad_s"), 0.0),
            one_over_f_fmin=_as_float(raw.get("one_over_f_fmin"), 0.0),
            one_over_f_fmax=_as_float(raw.get("one_over_f_fmax"), 0.0),
            one_over_f_exponent=_as_float(raw.get("one_over_f_exponent"), 1.0),
            ou_sigma_Hz=_as_float(raw.get("ou_sigma_Hz"), 0.0),
            ou_sigma_rad_s=_as_float(raw.get("ou_sigma_rad_s"), 0.0),
            ou_tau=_as_float(raw.get("ou_tau"), 1.0),
        )

    def __post_init__(self) -> None:
        if not self.targets:
            self.targets = [int(self.q)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the stochastic channel to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the stochastic channel.
        """
        return asdict(self)


@dataclass
class PerQubitRateSpec:
    """Derived per-qubit Markovian-rate summary.

    This is compatibility metadata emitted by lowering for legacy consumers.
    Authored noise should use ``NoiseSourceSpec(kind="markovian", ...)``
    instead of treating this as a source of truth.

    Attributes:
        q: Index of the target qubit. Defaults to 0.
        gamma1_Hz: Longitudinal relaxation rate in Hz. Defaults to 0.0.
        gamma_phi_Hz: Pure dephasing rate in Hz. Defaults to 0.0.
        gamma_up_Hz: Excitation rate in Hz. Defaults to 0.0.
        gamma1_rad_s: Longitudinal relaxation rate in rad/s. Defaults to 0.0.
        gamma_phi_rad_s: Pure dephasing rate in rad/s. Defaults to 0.0.
        gamma_up_rad_s: Excitation rate in rad/s. Defaults to 0.0.
    """

    q: int = 0
    gamma1_Hz: float = 0.0
    gamma_phi_Hz: float = 0.0
    gamma_up_Hz: float = 0.0
    gamma1_rad_s: float = 0.0
    gamma_phi_rad_s: float = 0.0
    gamma_up_rad_s: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PerQubitRateSpec":
        """Create per-qubit rate data from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing rate fields.

        Returns:
            PerQubitRateSpec: A typed per-qubit rate specification.
        """
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
        """Serialize per-qubit rates to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the per-qubit rates.
        """
        return asdict(self)


@dataclass
class NoiseSpec:
    """Engine-neutral noise model.

    The `NoiseSpec` aggregates all noise sources, including Markovian channels,
    stochastic processes, and device-level crosstalk.

    Attributes:
        selected_model: Identifier of the primary noise model. Defaults to "markovian_lindblad".
        readout_error: Global readout error probability. Defaults to 0.0.
        sources: List of general noise source specifications.
        realizations: Specific noise realizations for stochastic simulations.
        control_crosstalk: Specifications for control-channel leakage.
        readout_crosstalk: Specifications for readout crosstalk.
        collapse_channels: List of Markovian collapse channels.
        stochastic_channels: List of stochastic noise channels.
        per_qubit_rates: Summary of per-qubit Markovian rates (legacy/compatibility).
        supported: List of noise features supported by the current engine.
        unsupported: List of noise features not supported.
        warnings: List of warnings regarding the noise configuration.
    """

    selected_model: str = "markovian_lindblad"
    readout_error: float = 0.0
    sources: list[NoiseSourceSpec] = field(default_factory=list)
    realizations: list[dict[str, Any]] = field(default_factory=list)
    control_crosstalk: list[ControlCrosstalkSpec] = field(default_factory=list)
    readout_crosstalk: list[ReadoutCrosstalkSpec] = field(default_factory=list)
    collapse_channels: list[CollapseChannelSpec] = field(default_factory=list)
    stochastic_channels: list[StochasticChannelSpec] = field(default_factory=list)
    per_qubit_rates: list[PerQubitRateSpec] = field(default_factory=list)
    supported: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize nested channel dictionaries into typed specs.

        This method ensures that all noise-related lists contain the 
        appropriate typed specification objects rather than raw dictionaries.
        """
        self.sources = [
            item if isinstance(item, NoiseSourceSpec) else NoiseSourceSpec.from_dict(item)
            for item in list(self.sources or [])
        ]
        self.realizations = [dict(item) for item in list(self.realizations or []) if isinstance(item, dict)]
        self.control_crosstalk = [
            item if isinstance(item, ControlCrosstalkSpec) else ControlCrosstalkSpec.from_dict(item)
            for item in list(self.control_crosstalk or [])
        ]
        self.readout_crosstalk = [
            item if isinstance(item, ReadoutCrosstalkSpec) else ReadoutCrosstalkSpec.from_dict(item)
            for item in list(self.readout_crosstalk or [])
        ]
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

