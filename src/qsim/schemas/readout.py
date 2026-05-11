"""Readout schema for engine-neutral model specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qsim.schemas.components import _dataclass_public_dict
@dataclass
class ReadoutControlSpec:
    """Sampled readout-drive channel.

    Attributes:
        channel: Identifier of the readout control channel. Defaults to "".
        target: Index of the target subsystem. Defaults to 0.
        kind: Type of readout control (e.g., "readout"). Defaults to "readout".
        times: Time grid for the sampled signal in seconds.
        values: Sampled signal coefficients.
        scale: Global scaling factor. Defaults to 1.0.
        carrier_freq_Hz: Carrier frequency in Hz. Defaults to 0.0.
        carrier_omega_rad_s: Carrier angular frequency in rad/s. Defaults to 0.0.
        carrier_phase_rad: Carrier phase in radians. Defaults to 0.0.
        metadata: Non-primary technical annotations.
    """

    channel: str = ""
    target: int = 0
    kind: str = "readout"
    times: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    scale: float = 1.0
    carrier_freq_Hz: float = 0.0
    carrier_omega_rad_s: float = 0.0
    carrier_phase_rad: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutControlSpec":
        """Create a sampled readout control from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing control fields.

        Returns:
            ReadoutControlSpec: A typed readout control specification.
        """
        raw = dict(data or {})
        core = {
            "channel",
            "target",
            "kind",
            "times",
            "values",
            "scale",
            "carrier_freq_Hz",
            "carrier_omega_rad_s",
            "carrier_phase_rad",
        }
        return cls(
            channel=str(raw.get("channel", "") or ""),
            target=int(raw.get("target", 0) or 0),
            kind=str(raw.get("kind", "readout") or "readout"),
            times=[float(x) for x in list(raw.get("times", []) or [])],
            values=[float(x) for x in list(raw.get("values", []) or [])],
            scale=float(raw.get("scale", 1.0) or 1.0),
            carrier_freq_Hz=float(raw.get("carrier_freq_Hz", 0.0) or 0.0),
            carrier_omega_rad_s=float(raw.get("carrier_omega_rad_s", 0.0) or 0.0),
            carrier_phase_rad=float(raw.get("carrier_phase_rad", 0.0) or 0.0),
            metadata={key: value for key, value in raw.items() if key not in core},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the readout control to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the readout control.
        """
        data = {
            "channel": self.channel,
            "target": self.target,
            "kind": self.kind,
            "times": list(self.times),
            "values": list(self.values),
            "scale": self.scale,
            "carrier_freq_Hz": self.carrier_freq_Hz,
            "carrier_omega_rad_s": self.carrier_omega_rad_s,
            "carrier_phase_rad": self.carrier_phase_rad,
        }
        data.update(dict(self.metadata))
        return data


@dataclass
class ReadoutLineSpec:
    """Readout line component projected into the model spec.

    Attributes:
        id: Unique identifier for the readout line. Defaults to "".
        representation: Representation mode (e.g., "quantum", "classical"). Defaults to "".
        description: Human-readable description. Defaults to "".
        eta_chain: Total quantum efficiency of the readout chain. Defaults to 1.0.
        gain_dB: Total gain of the chain in decibels. Defaults to 0.0.
        added_noise_photons: Equivalent noise temperature in photons. Defaults to 0.0.
        center_freq_Hz: Center frequency of the readout line in Hz. Defaults to 0.0.
        bandwidth_Hz: Bandwidth of the readout line in Hz. Defaults to 0.0.
    """

    id: str = ""
    representation: str = ""
    description: str = ""
    eta_chain: float = 1.0
    gain_dB: float = 0.0
    added_noise_photons: float = 0.0
    center_freq_Hz: float = 0.0
    bandwidth_Hz: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutLineSpec":
        """Create a readout-line spec from component-style input.

        Args:
            data (dict[str, Any] | None): Input dictionary containing line fields.

        Returns:
            ReadoutLineSpec: A typed readout line specification.
        """
        raw = dict(data or {})
        params = dict(raw.get("parameters", {}) or {})
        return cls(
            id=str(raw.get("id", "") or ""),
            representation=str(raw.get("representation", "") or ""),
            description=str(raw.get("description", "") or ""),
            eta_chain=float(raw.get("eta_chain", params.get("eta_chain", 1.0)) or 1.0),
            gain_dB=float(raw.get("gain_dB", params.get("gain_dB", 0.0)) or 0.0),
            added_noise_photons=float(raw.get("added_noise_photons", params.get("added_noise_photons", 0.0)) or 0.0),
            center_freq_Hz=float(raw.get("center_freq_Hz", params.get("center_freq_Hz", 0.0)) or 0.0),
            bandwidth_Hz=float(raw.get("bandwidth_Hz", params.get("bandwidth_Hz", 0.0)) or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the readout line to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the readout line.
        """
        return {
            "id": self.id,
            "representation": self.representation,
            "description": self.description,
            "eta_chain": self.eta_chain,
            "gain_dB": self.gain_dB,
            "added_noise_photons": self.added_noise_photons,
            "center_freq_Hz": self.center_freq_Hz,
            "bandwidth_Hz": self.bandwidth_Hz,
        }


@dataclass
class ResetEventSpec:
    """Measurement-conditioned reset event projected into the runtime model.

    Attributes:
        id: Unique identifier for the reset event. Defaults to "".
        target: Target qubit/subsystem index or ID. Defaults to "".
        t0_s: Start time of the event in seconds. Defaults to 0.0.
        t_meas_end_s: Time when the measurement ends. Defaults to 0.0.
        t_deplete_end_s: Time when state depletion ends. Defaults to 0.0.
        t_feedback_start_s: Time when feedback logic starts. Defaults to 0.0.
        t_apply_s: Time when the reset pulse is applied. Defaults to 0.0.
        duration_s: Duration of the reset pulse. Defaults to 0.0.
        feedback_offset_s: Delay between measurement and feedback. Defaults to 0.0.
        method: Reset method (e.g., "conditional_pi"). Defaults to "conditional_pi".
        condition: Logical condition for triggering the reset. Defaults to "".
        conditional_on: Index of the qubit the reset is conditioned on. Defaults to 1.
        apply_feedback: Whether to apply the feedback pulse. Defaults to True.
        success_probability: Probability of successful reset. Defaults to 1.0.
    """

    id: str = ""
    target: int | str = ""
    t0_s: float = 0.0
    t_meas_end_s: float = 0.0
    t_deplete_end_s: float = 0.0
    t_feedback_start_s: float = 0.0
    t_apply_s: float = 0.0
    duration_s: float = 0.0
    feedback_offset_s: float = 0.0
    method: str = "conditional_pi"
    condition: str = ""
    conditional_on: int = 1
    apply_feedback: bool = True
    success_probability: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResetEventSpec":
        """Create a reset event from current or legacy timing keys.

        Args:
            data (dict[str, Any] | None): Input dictionary containing event fields.

        Returns:
            ResetEventSpec: A typed reset event specification.
        """
        raw = dict(data or {})
        t0_s = _time_seconds(raw, "t0")
        t_meas_end_s = _time_seconds(raw, "t_meas_end")
        t_deplete_end_s = _time_seconds(raw, "t_deplete_end")
        t_feedback_start_s = _time_seconds(raw, "t_feedback_end")
        t_apply_s = _time_seconds(raw, "t1")
        duration_s = float(raw.get("duration_s", max(0.0, t_apply_s - t0_s)) or 0.0)
        feedback_offset_s = float(
            raw.get("feedback_offset_s", 1.0e-9 * float(raw.get("feedback_offset_ns", 0.0) or 0.0))
            or 0.0
        )
        target: int | str
        if "target" in raw:
            target = raw.get("target", "")
        else:
            target = int(raw.get("qubit", 0) or 0)
        return cls(
            id=str(raw.get("id", "") or ""),
            target=target,
            t0_s=t0_s,
            t_meas_end_s=t_meas_end_s,
            t_deplete_end_s=t_deplete_end_s,
            t_feedback_start_s=t_feedback_start_s,
            t_apply_s=t_apply_s,
            duration_s=duration_s,
            feedback_offset_s=feedback_offset_s,
            method=str(raw.get("method", "conditional_pi") or "conditional_pi"),
            condition=str(raw.get("condition", "") or ""),
            conditional_on=int(raw.get("conditional_on", 1) or 1),
            apply_feedback=bool(raw.get("apply_feedback", True)),
            success_probability=float(raw.get("success_probability", 1.0) or 1.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the reset event to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the reset event.
        """
        return _dataclass_public_dict(self)


def _time_seconds(raw: dict[str, Any], stem: str) -> float:
    """Convert a time value from a dictionary to seconds.

    If the key ends with `_s`, it is treated as seconds. Otherwise, it is 
    treated as nanoseconds.

    Args:
        raw (dict[str, Any]): Input dictionary.
        stem (str): Base name of the time field.

    Returns:
        float: Time value in seconds.
    """
    if f"{stem}_s" in raw:
        return float(raw.get(f"{stem}_s", 0.0) or 0.0)
    return 1.0e-9 * float(raw.get(stem, 0.0) or 0.0)


@dataclass
class ReadoutChainSpec:
    """Readout-chain parameters used by dispersive and classical readout paths.

    Attributes:
        kappa_int_Hz: Internal cavity decay rate in Hz. Defaults to 0.0.
        kappa_ext_Hz: External coupling decay rate in Hz. Defaults to 0.0.
        chi_Hz: Dispersive shift in Hz. Can be a single value or a list per qubit.
        eta_chain: Overall quantum efficiency. Defaults to 1.0.
        gain_dB: Total amplifier gain in dB. Defaults to 0.0.
        added_noise_photons: System added noise in photons. Defaults to 0.0.
        center_freq_Hz: Readout center frequency in Hz. Defaults to 0.0.
        bandwidth_Hz: Readout bandwidth in Hz. Defaults to 0.0.
        measurement_rate_Hz: Rate of information extraction in Hz. Defaults to 0.0.
        cavity_freq_Hz: Bare cavity frequency in Hz. Defaults to 0.0.
        input_amplitude_noise_rel_sigma: Relative amplitude noise sigma. Defaults to 0.0.
        input_phase_noise_std_rad: Input phase noise standard deviation in rad. Defaults to 0.0.
        input_additive_noise_sigma: Input additive noise sigma. Defaults to 0.0.
        feedback_success_prob: Probability of successful feedback. Defaults to 1.0.
        cavity_equation: Formal equation for cavity dynamics. Defaults to "".
        output_equation: Formal equation for output signal. Defaults to "".
    """

    kappa_int_Hz: float = 0.0
    kappa_ext_Hz: float = 0.0
    chi_Hz: float | list[float] = field(default_factory=list)
    eta_chain: float = 1.0
    gain_dB: float = 0.0
    added_noise_photons: float = 0.0
    center_freq_Hz: float = 0.0
    bandwidth_Hz: float = 0.0
    measurement_rate_Hz: float = 0.0
    cavity_freq_Hz: float = 0.0
    input_amplitude_noise_rel_sigma: float = 0.0
    input_phase_noise_std_rad: float = 0.0
    input_additive_noise_sigma: float = 0.0
    feedback_success_prob: float = 1.0
    cavity_equation: str = ""
    output_equation: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReadoutChainSpec":
        """Create readout-chain parameters from a plain dictionary.

        Args:
            data (dict[str, Any] | None): Input dictionary containing chain fields.

        Returns:
            ReadoutChainSpec: A typed readout chain specification.
        """
        raw = dict(data or {})
        chi_raw = raw.get("chi_Hz", [])
        chi: float | list[float]
        if isinstance(chi_raw, (list, tuple)):
            chi = [float(x) for x in list(chi_raw)]
        else:
            chi = float(chi_raw or 0.0)
        return cls(
            kappa_int_Hz=float(raw.get("kappa_int_Hz", 0.0) or 0.0),
            kappa_ext_Hz=float(raw.get("kappa_ext_Hz", 0.0) or 0.0),
            chi_Hz=chi,
            eta_chain=float(raw.get("eta_chain", 1.0) or 1.0),
            gain_dB=float(raw.get("gain_dB", 0.0) or 0.0),
            added_noise_photons=float(raw.get("added_noise_photons", 0.0) or 0.0),
            center_freq_Hz=float(raw.get("center_freq_Hz", 0.0) or 0.0),
            bandwidth_Hz=float(raw.get("bandwidth_Hz", 0.0) or 0.0),
            measurement_rate_Hz=float(raw.get("measurement_rate_Hz", 0.0) or 0.0),
            cavity_freq_Hz=float(raw.get("cavity_freq_Hz", 0.0) or 0.0),
            input_amplitude_noise_rel_sigma=float(raw.get("input_amplitude_noise_rel_sigma", 0.0) or 0.0),
            input_phase_noise_std_rad=float(raw.get("input_phase_noise_std_rad", 0.0) or 0.0),
            input_additive_noise_sigma=float(raw.get("input_additive_noise_sigma", 0.0) or 0.0),
            feedback_success_prob=float(raw.get("feedback_success_prob", 1.0) or 1.0),
            cavity_equation=str(raw.get("cavity_equation", "") or ""),
            output_equation=str(raw.get("output_equation", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize readout-chain parameters to a JSON-safe dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the readout chain.
        """
        data = {
            "kappa_int_Hz": self.kappa_int_Hz,
            "kappa_ext_Hz": self.kappa_ext_Hz,
            "chi_Hz": list(self.chi_Hz) if isinstance(self.chi_Hz, list) else self.chi_Hz,
            "eta_chain": self.eta_chain,
            "gain_dB": self.gain_dB,
            "added_noise_photons": self.added_noise_photons,
            "center_freq_Hz": self.center_freq_Hz,
            "bandwidth_Hz": self.bandwidth_Hz,
            "measurement_rate_Hz": self.measurement_rate_Hz,
            "cavity_freq_Hz": self.cavity_freq_Hz,
            "input_amplitude_noise_rel_sigma": self.input_amplitude_noise_rel_sigma,
            "input_phase_noise_std_rad": self.input_phase_noise_std_rad,
            "input_additive_noise_sigma": self.input_additive_noise_sigma,
            "feedback_success_prob": self.feedback_success_prob,
            "cavity_equation": self.cavity_equation,
            "output_equation": self.output_equation,
        }
        return data

    @property
    def is_empty(self) -> bool:
        """Whether all readout-chain fields are still at defaults.

        Returns:
            bool: True if no custom parameters have been set.
        """
        return (
            self.kappa_int_Hz == 0.0
            and self.kappa_ext_Hz == 0.0
            and (self.chi_Hz == [] or self.chi_Hz == 0.0)
            and self.eta_chain == 1.0
            and self.gain_dB == 0.0
            and self.added_noise_photons == 0.0
            and self.center_freq_Hz == 0.0
            and self.bandwidth_Hz == 0.0
            and self.measurement_rate_Hz == 0.0
            and self.cavity_freq_Hz == 0.0
            and self.input_amplitude_noise_rel_sigma == 0.0
            and self.input_phase_noise_std_rad == 0.0
            and self.input_additive_noise_sigma == 0.0
            and self.feedback_success_prob == 1.0
            and not self.cavity_equation
            and not self.output_equation
        )


@dataclass
class ReadoutSpec:
    """Engine-neutral readout request and chain description.

    The `ReadoutSpec` defines how the state of the system is measured and 
    processed, including the hardware chain and any active reset events.

    Attributes:
        protocol: Measurement protocol (e.g., "dispersive_reflectometry"). Defaults to "dispersive_reflectometry".
        update_mode: Mode for state updates (e.g., "predictor_corrector"). Defaults to "predictor_corrector".
        subsystem_model: Model of the readout subsystem. Defaults to "".
        chain: Parameters of the readout hardware chain.
        controls: List of readout drive controls.
        lines: List of physical readout lines.
        reset_events: List of measurement-conditioned reset events.
    """

    protocol: str = "dispersive_reflectometry"
    update_mode: str = "predictor_corrector"
    subsystem_model: str = ""
    chain: ReadoutChainSpec = field(default_factory=ReadoutChainSpec)
    controls: list[ReadoutControlSpec] = field(default_factory=list)
    lines: list[ReadoutLineSpec] = field(default_factory=list)
    reset_events: list[ResetEventSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Normalize nested dictionaries into typed readout specs.

        This method ensures that all readout-related lists and the chain 
        contain the appropriate typed specification objects.
        """
        if not isinstance(self.chain, ReadoutChainSpec):
            self.chain = ReadoutChainSpec.from_dict(self.chain)
        self.controls = [
            ctrl if isinstance(ctrl, ReadoutControlSpec) else ReadoutControlSpec.from_dict(ctrl)
            for ctrl in list(self.controls or [])
        ]
        self.lines = [
            line if isinstance(line, ReadoutLineSpec) else ReadoutLineSpec.from_dict(line)
            for line in list(self.lines or [])
        ]
        self.reset_events = [
            event if isinstance(event, ResetEventSpec) else ResetEventSpec.from_dict(event)
            for event in list(self.reset_events or [])
        ]


