"""Typed system connection schema and connection factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qsim.schemas.components import _dataclass_public_dict
from qsim.schemas._factory_utils import _float, _int, _merged_payload, _str


@dataclass
class SystemConnectionSpec:
    """Base entry for a typed engine-neutral system connection."""

    id: str = ""
    type: str = ""
    a: str = ""
    b: str = ""
    via: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemConnectionSpec":
        """Build the appropriate connection subclass from a plain mapping."""
        return system_connection_from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a flat JSON-safe representation of the connection."""
        return _dataclass_public_dict(self)

    def to_device_dict(self) -> dict[str, Any]:
        """Return a compatibility device-style mapping with nested parameters."""
        data = {"id": self.id, "type": self.type, "a": self.a, "b": self.b, "parameters": _connection_parameters_dict(self)}
        if self.via:
            data["via"] = self.via
        return data


@dataclass
class JCConnectionSpec(SystemConnectionSpec):
    """Jaynes-Cummings coupling connection."""

    type: str = "jc"
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


@dataclass
class DispersiveConnectionSpec(SystemConnectionSpec):
    """Dispersive qubit-resonator coupling connection."""

    type: str = "dispersive"
    chi_Hz: float = 0.0
    chi_rad_s: float = 0.0
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


@dataclass
class ReadoutFeedlineConnectionSpec(SystemConnectionSpec):
    """Input-output coupling between resonator and readout line."""

    type: str = "readout_feedline"
    kappa_ext_Hz: float = 0.0
    kappa_ext_rad_s: float = 0.0
    eta_chain: float = 1.0
    bandwidth_Hz: float = 0.0
    cavity_equation: str = ""
    output_equation: str = ""


@dataclass
class ZZConnectionSpec(SystemConnectionSpec):
    """Static ZZ-style two-qubit coupling connection."""

    type: str = "zz"
    i: int = 0
    j: int = 1
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


def _connection_parameters_dict(connection: SystemConnectionSpec) -> dict[str, Any]:
    if isinstance(connection, JCConnectionSpec):
        return {"g_Hz": connection.g_Hz}
    if isinstance(connection, DispersiveConnectionSpec):
        return {"chi_Hz": connection.chi_Hz, "g_Hz": connection.g_Hz}
    if isinstance(connection, ReadoutFeedlineConnectionSpec):
        data = {
            "kappa_ext_Hz": connection.kappa_ext_Hz,
            "eta_chain": connection.eta_chain,
            "bandwidth_Hz": connection.bandwidth_Hz,
        }
        input_output = {}
        if connection.cavity_equation:
            input_output["cavity_equation"] = connection.cavity_equation
        if connection.output_equation:
            input_output["output_equation"] = connection.output_equation
        if input_output:
            data["input_output"] = input_output
        return data
    if isinstance(connection, ZZConnectionSpec):
        return {"g_Hz": connection.g_Hz}
    return {}


def _base_connection_kwargs(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(raw.get("id", "") or ""),
        "a": str(raw.get("a", "") or ""),
        "b": str(raw.get("b", "") or ""),
        "via": str(raw.get("via", "") or ""),
    }


def _build_jc_connection(raw: dict[str, Any]) -> JCConnectionSpec:
    data = _merged_payload(raw)
    return JCConnectionSpec(**_base_connection_kwargs(raw), g_Hz=_float(data, "g_Hz"), g_rad_s=_float(data, "g_rad_s"))


def _build_dispersive_connection(raw: dict[str, Any]) -> DispersiveConnectionSpec:
    data = _merged_payload(raw)
    return DispersiveConnectionSpec(
        **_base_connection_kwargs(raw),
        chi_Hz=_float(data, "chi_Hz"),
        chi_rad_s=_float(data, "chi_rad_s"),
        g_Hz=_float(data, "g_Hz"),
        g_rad_s=_float(data, "g_rad_s"),
    )


def _build_readout_feedline_connection(raw: dict[str, Any]) -> ReadoutFeedlineConnectionSpec:
    data = _merged_payload(raw)
    input_output = dict(data.get("input_output", {}) or {})
    return ReadoutFeedlineConnectionSpec(
        **_base_connection_kwargs(raw),
        kappa_ext_Hz=_float(data, "kappa_ext_Hz"),
        kappa_ext_rad_s=_float(data, "kappa_ext_rad_s"),
        eta_chain=_float(data, "eta_chain", 1.0),
        bandwidth_Hz=_float(data, "bandwidth_Hz"),
        cavity_equation=str(data.get("cavity_equation", input_output.get("cavity_equation", "")) or ""),
        output_equation=str(data.get("output_equation", input_output.get("output_equation", "")) or ""),
    )


def _build_zz_connection(raw: dict[str, Any]) -> ZZConnectionSpec:
    data = _merged_payload(raw)
    return ZZConnectionSpec(
        **_base_connection_kwargs(raw),
        i=_int(data, "i", 0),
        j=_int(data, "j", 1),
        g_Hz=_float(data, "g_Hz"),
        g_rad_s=_float(data, "g_rad_s"),
    )


_CONNECTION_BUILDERS = {
    "jc": _build_jc_connection,
    "dispersive": _build_dispersive_connection,
    "readout_feedline": _build_readout_feedline_connection,
    "zz": _build_zz_connection,
}


def system_connection_from_dict(data: dict[str, Any] | None) -> SystemConnectionSpec:
    """Parse a plain connection dictionary into a typed connection spec."""
    raw = dict(data or {})
    conn_type = _str(raw, "type").strip().lower()
    builder = _CONNECTION_BUILDERS.get(conn_type)
    if builder is not None:
        return builder(raw)
    return SystemConnectionSpec(type=conn_type, **_base_connection_kwargs(raw))
