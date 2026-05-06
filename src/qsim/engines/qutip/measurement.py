"""Measurement context helpers for the QuTiP engine."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from qsim.backend.config import normalize_device_config
from qsim.backend.model.lowering import (
    ReadoutTopologyInput,
    has_classical_readout_line,
    infer_classical_readout_chain,
    infer_cqed_readout_chain,
    readout_coupling_prefactor,
    readout_topology_input,
    resolve_hybrid_update_mode,
    resolve_readout_protocol,
)
from qsim.common.channels import canonical_readout_protocol, sample_complex_drive_from_controls
from qsim.common.schemas import ModelSpec


def _control_attr(control: Any, name: str, default: Any = None) -> Any:
    if isinstance(control, dict):
        return control.get(name, default)
    if hasattr(control, name):
        return getattr(control, name)
    return default


def _readout_input_from_payload(payload: dict[str, Any]) -> ReadoutTopologyInput:
    device = normalize_device_config(
        {
            "components": list(payload.get("components", []) or []),
            "connections": list(payload.get("connections", []) or []),
        }
    )
    return readout_topology_input(
        device.components,
        device.connections,
        primary_step=dict(payload.get("primary_step", {}) or {}),
        readout_chain=dict(payload.get("readout_chain", {}) or {}),
    )


def _readout_input_from_model_spec(model_spec: ModelSpec) -> ReadoutTopologyInput:
    system = model_spec.system
    readout = model_spec.readout
    device = normalize_device_config(
        {
            "components": [component.to_device_dict() for component in system.components],
            "connections": [connection.to_device_dict() for connection in system.connections],
        }
    )
    return readout_topology_input(
        device.components,
        device.connections,
        primary_step=dict(model_spec.study.primary_step if model_spec.study else {}),
        readout_chain={} if readout is None or readout.chain.is_empty else readout.chain.to_dict(),
    )


class QutipMeasurementMixin:
    """Resolve measurement protocol, chain, controls, and line helper coefficients."""

    @staticmethod
    def _sample_readout_drive(tlist: np.ndarray, controls: list[Any]) -> np.ndarray:
        return sample_complex_drive_from_controls(tlist, controls)

    @staticmethod
    def _infer_cqed_readout_params(model: ModelSpec | dict[str, Any], n_qubits: int) -> dict[str, Any]:
        if isinstance(model, ModelSpec):
            readout = model.readout
            if readout is not None and not readout.chain.is_empty:
                return readout.chain.to_dict()
            return infer_cqed_readout_chain(_readout_input_from_model_spec(model), n_qubits)
        return infer_cqed_readout_chain(_readout_input_from_payload(model), n_qubits)

    @staticmethod
    def _infer_classical_readout_params(model: ModelSpec | dict[str, Any]) -> dict[str, Any]:
        if isinstance(model, ModelSpec):
            readout = model.readout
            if readout is not None and not readout.chain.is_empty:
                return readout.chain.to_dict()
            return infer_classical_readout_chain(_readout_input_from_model_spec(model))
        return infer_classical_readout_chain(_readout_input_from_payload(model))

    @staticmethod
    def _classical_readout_state(primary_step: dict[str, Any]) -> tuple[int, str]:
        prep_state = dict(primary_step.get("prep_state", {}) or {})
        options = dict(primary_step.get("options", {}) or {})
        raw_label = str(
            options.get("classical_readout_state", options.get("readout_state_label", prep_state.get("label", "0")))
            or "0"
        ).strip()
        label = raw_label or "0"
        digits = [ch for ch in label if ch.isdigit()]
        state = 1 if digits and digits[0] == "1" else 0
        return state, label

    @classmethod
    def _has_classical_readout_line(cls, model: ModelSpec | dict[str, Any]) -> bool:
        if isinstance(model, ModelSpec):
            return has_classical_readout_line(_readout_input_from_model_spec(model))
        return has_classical_readout_line(_readout_input_from_payload(model))

    @staticmethod
    def _resolve_hybrid_update_mode(model: ModelSpec | dict[str, Any]) -> str:
        if isinstance(model, ModelSpec):
            if model.readout is not None:
                return str(model.readout.update_mode or "predictor_corrector")
            return resolve_hybrid_update_mode(_readout_input_from_model_spec(model))
        return resolve_hybrid_update_mode(_readout_input_from_payload(model))

    @staticmethod
    def _resolve_readout_protocol(model: ModelSpec | dict[str, Any]) -> str:
        if isinstance(model, ModelSpec):
            if model.readout is not None:
                return str(model.readout.protocol)
            return canonical_readout_protocol(model.study.primary_step if model.study else {})
        return resolve_readout_protocol(_readout_input_from_payload(model))

    @staticmethod
    def _arg_coeff(name: str, store: dict[str, float] | None = None) -> Callable[[float, dict[str, Any] | None], float]:
        def f(_t, args=None):
            if isinstance(args, dict) and name in args:
                return float(args.get(name, 0.0))
            if store is not None:
                return float(store.get(name, 0.0))
            return 0.0

        return f

    @staticmethod
    def _advance_line_state(
        prev: complex,
        *,
        line_target: complex,
        dt: float,
        gamma_line: float,
        line_detuning_rad: float,
        thermal_noise: complex,
    ) -> complex:
        if gamma_line > 0.0:
            next_state = prev + dt * (-(0.5 * gamma_line + 1j * line_detuning_rad) * prev + gamma_line * line_target)
        else:
            next_state = complex(line_target)
        return complex(next_state + thermal_noise)

    @staticmethod
    def _readout_coupling_prefactor(kappa_ext_hz: float) -> float:
        return readout_coupling_prefactor(kappa_ext_hz)

    @classmethod
    def _input_output_a_out(cls, *, a_in: complex, cavity_field: complex, kappa_ext_hz: float) -> complex:
        return complex(a_in) - cls._readout_coupling_prefactor(kappa_ext_hz) * complex(cavity_field)

    @classmethod
    def _build_quantum_state_trajectory(
        cls,
        *,
        snapshots: list[Any],
        requested_kind: str,
        actual_kind: str,
    ) -> dict[str, object] | None:
        if not snapshots:
            return None
        note = ""
        if requested_kind == "density_matrix" and actual_kind != "density_matrix":
            note = "requested density_matrix but hybrid mcwf stores wave_function trajectories"
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in snapshots if isinstance(item, dict)],
            "note": note,
        }
