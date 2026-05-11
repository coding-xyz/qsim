"""Typed system connection schema and connection factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qsim.schemas.components import _dataclass_public_dict
from qsim.schemas._factory_utils import _float, _int, _merged_payload, _str


@dataclass
class SystemConnectionSpec:
    """Base entry for a typed engine-neutral system connection.

    Attributes:
        id: Unique identifier for the connection. Defaults to "".
        type: Type of connection (e.g., "jc", "dispersive"). Defaults to "".
        a: ID of the first connected component. Defaults to "".
        b: ID of the second connected component. Defaults to "".
        via: ID of a mediator component, if applicable. Defaults to "".
    """

    id: str = ""
    type: str = ""
    a: str = ""
    b: str = ""
    via: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SystemConnectionSpec":
        """Build the appropriate connection subclass from a plain mapping.

        Args:
            data (dict[str, Any] | None): Input dictionary containing connection fields.

        Returns:
            SystemConnectionSpec: A typed connection specification (possibly a subclass).
        """
        return system_connection_from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a flat JSON-safe representation of the connection.

        Returns:
            dict[str, Any]: A dictionary containing all public fields of the connection.
        """
        return _dataclass_public_dict(self)

    def to_device_dict(self) -> dict[str, Any]:
        """Return a compatibility device-style mapping with nested parameters.

        This method formats the connection in a style compatible with legacy 
        device descriptions, grouping parameters into a nested dictionary.

        Returns:
            dict[str, Any]: Device-style mapping.
        """
        data = {"id": self.id, "type": self.type, "a": self.a, "b": self.b, "parameters": _connection_parameters_dict(self)}
        if self.via:
            data["via"] = self.via
        return data


@dataclass
class JCConnectionSpec(SystemConnectionSpec):
    """Jaynes-Cummings coupling connection.

    Attributes:
        type: Connection type. Defaults to "jc".
        g_Hz: Coupling strength in Hz. Defaults to 0.0.
        g_rad_s: Coupling strength in rad/s. Defaults to 0.0.
    """

    type: str = "jc"
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


@dataclass
class DispersiveConnectionSpec(SystemConnectionSpec):
    """Dispersive qubit-resonator coupling connection.

    Attributes:
        type: Connection type. Defaults to "dispersive".
        chi_Hz: Dispersive shift in Hz. Defaults to 0.0.
        chi_rad_s: Dispersive shift in rad/s. Defaults to 0.0.
        g_Hz: Coupling strength in Hz. Defaults to 0.0.
        g_rad_s: Coupling strength in rad/s. Defaults to 0.0.
    """

    type: str = "dispersive"
    chi_Hz: float = 0.0
    chi_rad_s: float = 0.0
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


@dataclass
class ReadoutFeedlineConnectionSpec(SystemConnectionSpec):
    """Input-output coupling between resonator and readout line.

    Attributes:
        type: Connection type. Defaults to "readout_feedline".
        kappa_ext_Hz: External coupling rate in Hz. Defaults to 0.0.
        kappa_ext_rad_s: External coupling rate in rad/s. Defaults to 0.0.
        eta_chain: Overall quantum efficiency. Defaults to 1.0.
        bandwidth_Hz: Readout bandwidth in Hz. Defaults to 0.0.
        cavity_equation: Formal equation for cavity dynamics. Defaults to "".
        output_equation: Formal equation for output signal. Defaults to "".
    """

    type: str = "readout_feedline"
    kappa_ext_Hz: float = 0.0
    kappa_ext_rad_s: float = 0.0
    eta_chain: float = 1.0
    bandwidth_Hz: float = 0.0
    cavity_equation: str = ""
    output_equation: str = ""


@dataclass
class ZZConnectionSpec(SystemConnectionSpec):
    """Static ZZ-style two-qubit coupling connection.

    Attributes:
        type: Connection type. Defaults to "zz".
        i: Index of the first qubit. Defaults to 0.
        j: Index of the second qubit. Defaults to 1.
        g_Hz: Coupling strength in Hz. Defaults to 0.0.
        g_rad_s: Coupling strength in rad/s. Defaults to 0.0.
    """

    type: str = "zz"
    i: int = 0
    j: int = 1
    g_Hz: float = 0.0
    g_rad_s: float = 0.0


def _connection_parameters_dict(connection: SystemConnectionSpec) -> dict[str, Any]:
    """Extract key physical parameters from a connection.

    Args:
        connection (SystemConnectionSpec): The connection to extract parameters from.

    Returns:
        dict[str, Any]: Dictionary of parameters.
    """
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
    """Extract common base fields for any system connection.

    Args:
        raw (dict[str, Any]): Raw input data.

    Returns:
        dict[str, str]: Dictionary of base keyword arguments.
    """
    return {
        "id": str(raw.get("id", "") or ""),
        "a": str(raw.get("a", "") or ""),
        "b": str(raw.get("b", "") or ""),
        "via": str(raw.get("via", "") or ""),
    }


def _build_jc_connection(raw: dict[str, Any]) -> JCConnectionSpec:
    """Builder for Jaynes-Cummings connections.

    Args:
        raw (dict[str, Any]): Raw input data.

    Returns:
        JCConnectionSpec: A typed JC connection specification.
    """
    data = _merged_payload(raw)
    return JCConnectionSpec(**_base_connection_kwargs(raw), g_Hz=_float(data, "g_Hz"), g_rad_s=_float(data, "g_rad_s"))


def _build_dispersive_connection(raw: dict[str, Any]) -> DispersiveConnectionSpec:
    """Builder for dispersive connections.

    Args:
        raw (dict[str, Any]): Raw input data.

    Returns:
        DispersiveConnectionSpec: A typed dispersive connection specification.
    """
    data = _merged_payload(raw)
    return DispersiveConnectionSpec(
        **_base_connection_kwargs(raw),
        chi_Hz=_float(data, "chi_Hz"),
        chi_rad_s=_float(data, "chi_rad_s"),
        g_Hz=_float(data, "g_Hz"),
        g_rad_s=_float(data, "g_rad_s"),
    )


def _build_readout_feedline_connection(raw: dict[str, Any]) -> ReadoutFeedlineConnectionSpec:
    """Builder for readout feedline connections.

    Args:
        raw (dict[str, Any]): Raw input data.

    Returns:
        ReadoutFeedlineConnectionSpec: A typed readout feedline specification.
    """
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
    """Builder for ZZ coupling connections.

    Args:
        raw (dict[str, Any]): Raw input data.

    Returns:
        ZZConnectionSpec: A typed ZZ connection specification.
    """
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
    """Parse a plain connection dictionary into a typed connection spec.

    Args:
        data (dict[str, Any] | None): Input dictionary containing connection fields.

    Returns:
        SystemConnectionSpec: A typed connection specification of the correct subclass.
    """
    raw = dict(data or {})
    conn_type = _str(raw, "type").strip().lower()
    builder = _CONNECTION_BUILDERS.get(conn_type)
    if builder is not None:
        return builder(raw)
    return SystemConnectionSpec(type=conn_type, **_base_connection_kwargs(raw))
