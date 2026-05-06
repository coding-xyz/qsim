"""Shared helpers for ModelSpec lowering stages."""

from __future__ import annotations

import math
from typing import Any


TWO_PI = 2.0 * math.pi


def to_float_list(arr: Any) -> list[float]:
    """Return an array-like value as a plain list of floats."""
    return [float(x) for x in arr.tolist()] if hasattr(arr, "tolist") else [float(x) for x in arr]


def expand_value(raw: Any, count: int, default: float = 0.0) -> list[float]:
    """Expand a scalar or short sequence to exactly ``count`` float values."""
    if raw is None:
        return [float(default) for _ in range(count)]
    if isinstance(raw, (list, tuple)):
        vals = [float(x) for x in raw]
        if len(vals) < count:
            vals.extend([float(default)] * (count - len(vals)))
        return vals[:count]
    return [float(raw) for _ in range(count)]


def qubit_field(qubits: list[Any], key: str, default: float = 0.0) -> list[float]:
    """Extract a numeric field from each qubit-like mapping."""
    return [float((q or {}).get(key, default)) for q in qubits]
