"""Typed system component schema and component factories."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from qsim.schemas._factory_utils import _float, _merged_payload, _optional_float, _str


@dataclass
class SystemComponentSpec:
    """Base entry for a typed engine-neutral system component."""

    id: str = ""
    type: str = ""
    representation: str = "quantum"
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemComponentSpec":
        """Build the appropriate component subclass from a plain mapping."""
        return system_component_from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a flat JSON-safe representation of the component."""
        return _dataclass_public_dict(self)

    def to_device_dict(self) -> dict[str, Any]:
        """Return a compatibility device-style mapping with nested parameters."""
        data = {
            "id": self.id,
            "type": self.type,
            "representation": self.representation,
            "parameters": _component_parameters_dict(self),
        }
        basis = _component_basis_dict(self)
        if basis:
            data["basis"] = basis
        if self.description:
            data["description"] = self.description
        return data


@dataclass
class TransmonComponentSpec(SystemComponentSpec):
    """Typed transmon component entry."""

    type: str = "transmon"
    levels: int = 2
    freq_Hz: float = 0.0
    omega_rad_s: float = 0.0
    anharmonicity_Hz: float = 0.0
    anharmonicity_rad_s: float = 0.0
    T1_s: float | None = None
    T2_s: float | None = None
    Tphi_s: float | None = None
    Tup_s: float | None = None
    gamma1_Hz: float = 0.0
    gamma_phi_Hz: float = 0.0
    gamma_up_Hz: float = 0.0


@dataclass
class ResonatorComponentSpec(SystemComponentSpec):
    """Typed resonator/cavity component entry."""

    type: str = "resonator"
    nmax: int = 0
    freq_Hz: float = 0.0
    omega_rad_s: float = 0.0
    kappa_int_Hz: float = 0.0
    kappa_int_rad_s: float = 0.0
    kappa_ext_Hz: float = 0.0
    kappa_ext_rad_s: float = 0.0
    chi_Hz: float = 0.0
    chi_rad_s: float = 0.0


@dataclass
class ReadoutLineComponentSpec(SystemComponentSpec):
    """Typed readout-line component entry."""

    type: str = "readout_line"
    eta_chain: float = 1.0
    gain_dB: float = 0.0
    added_noise_photons: float = 0.0
    center_freq_Hz: float = 0.0
    bandwidth_Hz: float = 0.0
    input_amplitude_noise_rel_sigma: float = 0.0
    input_phase_noise_std_rad: float = 0.0
    input_additive_noise_sigma: float = 0.0
    feedback_success_prob: float = 1.0


def _dataclass_public_dict(obj: Any) -> dict[str, Any]:
    data = asdict(obj)
    return {key: value for key, value in data.items() if value is not None}


def _component_parameters_dict(component: SystemComponentSpec) -> dict[str, Any]:
    if isinstance(component, TransmonComponentSpec):
        return {
            "freq_Hz": component.freq_Hz,
            "anharmonicity_Hz": component.anharmonicity_Hz,
        }
    if isinstance(component, ResonatorComponentSpec):
        return {
            "freq_Hz": component.freq_Hz,
            "kappa_int_Hz": component.kappa_int_Hz,
            "kappa_ext_Hz": component.kappa_ext_Hz,
            "chi_Hz": component.chi_Hz,
        }
    if isinstance(component, ReadoutLineComponentSpec):
        return {
            "eta_chain": component.eta_chain,
            "gain_dB": component.gain_dB,
            "added_noise_photons": component.added_noise_photons,
            "center_freq_Hz": component.center_freq_Hz,
            "bandwidth_Hz": component.bandwidth_Hz,
            "input_amplitude_noise_rel_sigma": component.input_amplitude_noise_rel_sigma,
            "input_phase_noise_std_rad": component.input_phase_noise_std_rad,
            "input_additive_noise_sigma": component.input_additive_noise_sigma,
            "feedback_success_prob": component.feedback_success_prob,
        }
    return {}


def _component_basis_dict(component: SystemComponentSpec) -> dict[str, Any]:
    if isinstance(component, TransmonComponentSpec):
        return {"kind": "nlevel", "levels": component.levels} if component.levels > 2 else {}
    if isinstance(component, ResonatorComponentSpec):
        return {"kind": "fock", "nmax": component.nmax} if component.nmax > 0 else {}
    return {}


def _base_component_kwargs(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(raw.get("id", "") or ""),
        "representation": str(raw.get("representation", "quantum") or "quantum"),
        "description": str(raw.get("description", "") or ""),
    }


def _build_transmon_component(raw: dict[str, Any]) -> TransmonComponentSpec:
    data = _merged_payload(raw)
    basis = data["_basis"]
    noise = data["_noise"]
    return TransmonComponentSpec(
        **_base_component_kwargs(raw),
        levels=int(basis.get("levels", data.get("levels", 2)) or 2),
        freq_Hz=_float(data, "freq_Hz"),
        omega_rad_s=_float(data, "omega_rad_s"),
        anharmonicity_Hz=_float(data, "anharmonicity_Hz"),
        anharmonicity_rad_s=_float(data, "anharmonicity_rad_s"),
        T1_s=_optional_float(data.get("T1_s", noise.get("T1_s"))),
        T2_s=_optional_float(data.get("T2_s", noise.get("T2_s"))),
        Tphi_s=_optional_float(data.get("Tphi_s", noise.get("Tphi_s"))),
        Tup_s=_optional_float(data.get("Tup_s", noise.get("Tup_s"))),
        gamma1_Hz=float(data.get("gamma1_Hz", noise.get("gamma1_Hz", 0.0)) or 0.0),
        gamma_phi_Hz=float(data.get("gamma_phi_Hz", noise.get("gamma_phi_Hz", 0.0)) or 0.0),
        gamma_up_Hz=float(data.get("gamma_up_Hz", noise.get("gamma_up_Hz", 0.0)) or 0.0),
    )


def _build_resonator_component(raw: dict[str, Any]) -> ResonatorComponentSpec:
    data = _merged_payload(raw)
    return ResonatorComponentSpec(
        **_base_component_kwargs(raw),
        type=str(raw.get("type", "resonator") or "resonator"),
        nmax=int(data["_basis"].get("nmax", data.get("nmax", 0)) or 0),
        freq_Hz=_float(data, "freq_Hz"),
        omega_rad_s=_float(data, "omega_rad_s"),
        kappa_int_Hz=_float(data, "kappa_int_Hz"),
        kappa_int_rad_s=_float(data, "kappa_int_rad_s"),
        kappa_ext_Hz=_float(data, "kappa_ext_Hz"),
        kappa_ext_rad_s=_float(data, "kappa_ext_rad_s"),
        chi_Hz=_float(data, "chi_Hz"),
        chi_rad_s=_float(data, "chi_rad_s"),
    )


def _build_readout_line_component(raw: dict[str, Any]) -> ReadoutLineComponentSpec:
    data = _merged_payload(raw)
    return ReadoutLineComponentSpec(
        **_base_component_kwargs(raw),
        eta_chain=_float(data, "eta_chain", 1.0),
        gain_dB=_float(data, "gain_dB"),
        added_noise_photons=_float(data, "added_noise_photons"),
        center_freq_Hz=_float(data, "center_freq_Hz"),
        bandwidth_Hz=_float(data, "bandwidth_Hz"),
        input_amplitude_noise_rel_sigma=_float(data, "input_amplitude_noise_rel_sigma"),
        input_phase_noise_std_rad=_float(data, "input_phase_noise_std_rad"),
        input_additive_noise_sigma=_float(data, "input_additive_noise_sigma"),
        feedback_success_prob=_float(data, "feedback_success_prob", 1.0),
    )


_COMPONENT_BUILDERS = {
    "transmon": _build_transmon_component,
    "resonator": _build_resonator_component,
    "cavity": _build_resonator_component,
    "readout_line": _build_readout_line_component,
}


def system_component_from_dict(data: dict[str, Any] | None) -> SystemComponentSpec:
    """Parse a plain component dictionary into a typed component spec."""
    raw = dict(data or {})
    comp_type = _str(raw, "type").strip().lower()
    builder = _COMPONENT_BUILDERS.get(comp_type)
    if builder is not None:
        return builder(raw)
    return SystemComponentSpec(type=comp_type, **_base_component_kwargs(raw))
