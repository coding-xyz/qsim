"""Serialization helpers for QuTiP result objects."""

from __future__ import annotations

from typing import Any

import numpy as np


class QutipSerializationMixin:
    """Serialize QuTiP states, measurements, and complex-valued series."""

    @staticmethod
    def _measurement_to_real_series(measurement, nt: int) -> np.ndarray:
        arr = np.asarray(measurement)
        if np.iscomplexobj(arr):
            arr = np.real(arr)
        arr = np.asarray(arr, dtype=float)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        out = np.zeros(max(0, int(nt)), dtype=float)
        if out.size <= 0 or arr.size <= 0:
            return out
        if arr.size == out.size - 1:
            out[1:] = arr
            return out
        if arr.size >= out.size:
            out[:] = arr[: out.size]
            return out
        out[-arr.size :] = arr
        return out

    @classmethod
    def _measurement_to_complex_series(cls, measurement, nt: int) -> np.ndarray:
        arr = np.asarray(measurement)
        if np.iscomplexobj(arr):
            if arr.ndim <= 1:
                flat = arr.reshape(-1).astype(complex)
                out = np.zeros(max(0, int(nt)), dtype=complex)
                if out.size <= 0 or flat.size <= 0:
                    return out
                if flat.size == out.size - 1:
                    out[1:] = flat
                    return out
                if flat.size >= out.size:
                    out[:] = flat[: out.size]
                    return out
                out[-flat.size :] = flat
                return out
            if arr.ndim == 2 and arr.shape[0] == 1:
                return cls._measurement_to_complex_series(arr[0], nt)
            if arr.ndim == 2 and arr.shape[1] == 1:
                return cls._measurement_to_complex_series(arr[:, 0], nt)
            arr = np.real(arr)
        arr = np.asarray(arr, dtype=float)
        if arr.ndim <= 1:
            return cls._measurement_to_real_series(arr, nt).astype(complex)
        if arr.ndim == 2 and arr.shape[0] >= 2:
            i_vals = cls._measurement_to_real_series(arr[0], nt)
            q_vals = cls._measurement_to_real_series(arr[1], nt)
            return i_vals.astype(complex) + 1j * q_vals.astype(complex)
        if arr.ndim == 2 and arr.shape[-1] >= 2:
            i_vals = cls._measurement_to_real_series(arr[:, 0], nt)
            q_vals = cls._measurement_to_real_series(arr[:, 1], nt)
            return i_vals.astype(complex) + 1j * q_vals.astype(complex)
        return cls._measurement_to_real_series(arr.reshape(-1), nt).astype(complex)

    @staticmethod
    def _complex_vector(values) -> list[complex]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [complex(float(v.real), float(v.imag)) for v in arr]

    @classmethod
    def _serialize_complex_series(cls, values) -> list[list[float]]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [[float(v.real), float(v.imag)] for v in arr]

    @classmethod
    def _serialize_real_series_as_complex(cls, values) -> list[list[float]]:
        arr = np.asarray(values, dtype=float).reshape(-1)
        return [[float(v), 0.0] for v in arr]

    @classmethod
    def _serialize_qobj_state(cls, qobj) -> dict[str, object]:
        data = np.asarray(qobj.full(), dtype=complex)
        if data.ndim == 2 and 1 in data.shape:
            return {"kind": "wave_function", "data": cls._complex_vector(data.reshape(-1))}
        return {
            "kind": "density_matrix",
            "data": [[cls._complex_vector(row) for row in data]][0],
        }

    @classmethod
    def _extract_quantum_state_trajectory(cls, result, solver: str, requested_kind: str) -> dict[str, object] | None:
        if requested_kind not in {"wave_function", "density_matrix"}:
            return None
        raw_states = list(getattr(result, "states", []) or [])
        if not raw_states and solver == "mcwf":
            runs_states = list(getattr(result, "runs_states", []) or [])
            raw_states = list(runs_states[:1] or [])
            if raw_states and isinstance(raw_states[0], list):
                raw_states = list(raw_states[0])
        if raw_states and isinstance(raw_states[0], list):
            raw_states = list(raw_states[0])
        if not raw_states:
            return None
        serialized = [cls._serialize_qobj_state(state) for state in raw_states]
        actual_kind = str(serialized[0].get("kind", "unknown"))
        if requested_kind == "wave_function" and actual_kind != "wave_function":
            note = "requested wave_function but solver returned density_matrix"
        else:
            note = ""
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in serialized],
            "note": note,
        }

    @staticmethod
    def _average_qobj_sequences(sequences: list[list[Any]]) -> list[Any]:
        averaged: list[Any] = []
        if not sequences:
            return averaged
        nsteps = max(len(seq) for seq in sequences)
        for idx in range(nsteps):
            samples = [seq[idx] for seq in sequences if idx < len(seq)]
            if not samples:
                continue
            accum = samples[0] * 0.0
            for state in samples:
                accum = accum + state
            averaged.append(accum * (1.0 / float(len(samples))))
        return averaged

    @classmethod
    def _extract_stochastic_density_trajectory(cls, result, requested_kind: str) -> dict[str, object] | None:
        if requested_kind not in {"wave_function", "density_matrix"}:
            return None
        raw_runs_states = list(getattr(result, "runs_states", []) or [])
        state_runs: list[list[Any]] = []
        if raw_runs_states:
            state_runs = [list(run) for run in raw_runs_states if isinstance(run, list) and run]
        if not state_runs:
            raw_states = list(getattr(result, "states", []) or [])
            if raw_states and isinstance(raw_states[0], list):
                state_runs = [list(run) for run in raw_states if isinstance(run, list) and run]
            elif raw_states:
                state_runs = [list(raw_states)]
        if not state_runs:
            return None
        averaged_states = cls._average_qobj_sequences(state_runs)
        if not averaged_states:
            return None
        serialized = [cls._serialize_qobj_state(state) for state in averaged_states]
        serialized_runs = [
            [cls._serialize_qobj_state(state) for state in run]
            for run in state_runs
        ]
        actual_kind = str(serialized[0].get("kind", "density_matrix"))
        note = ""
        if requested_kind == "wave_function":
            note = "requested wave_function but stochastic SME returns density_matrix"
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in serialized],
            "runs": [[item.get("data", []) for item in run] for run in serialized_runs],
            "num_runs": len(serialized_runs),
            "note": note,
        }

    @staticmethod
    def _quantum_payloads(qstate: dict[str, object] | None) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        payload = dict(qstate or {})
        actual_kind = str(payload.get("actual_kind", "")).strip().lower()
        if actual_kind == "wave_function":
            return payload, None
        if actual_kind == "density_matrix":
            return None, payload
        return None, None
