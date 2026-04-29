"""Shared helpers for sampled control/readout channels."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a scalar to float with a conservative fallback."""
    try:
        return float(value)
    except Exception:
        return float(default)


def _control_value(control: Any, key: str, default: Any = None) -> Any:
    if isinstance(control, dict):
        return control.get(key, default)
    if hasattr(control, key):
        return getattr(control, key)
    metadata = getattr(control, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get(key, default)
    return default


def sample_complex_drive_from_controls(tlist: np.ndarray, controls: list[Any]) -> np.ndarray:
    """Sample a complex drive envelope from lowered sampled-channel controls."""
    drive = np.zeros_like(tlist, dtype=complex)
    for ctrl in controls:
        times = [float(x) for x in _control_value(ctrl, "times", [])]
        values = [float(x) for x in _control_value(ctrl, "values", [])]
        if not times or not values:
            continue
        env = np.interp(
            tlist,
            np.asarray(times, dtype=float),
            np.asarray(values, dtype=float),
            left=0.0,
            right=0.0,
        )
        phase = float(_control_value(ctrl, "carrier_phase_rad", 0.0))
        drive = drive + float(_control_value(ctrl, "scale", 1.0)) * env.astype(complex) * complex(math.cos(phase), math.sin(phase))
    return drive


def canonical_readout_protocol(options_or_model: dict[str, Any]) -> str:
    """Resolve readout/measurement protocol aliases to canonical tokens."""
    primary_step = dict(options_or_model.get("primary_step", {}) or {})
    options = dict(primary_step.get("options", {}) or {})
    if not options:
        options = dict(options_or_model or {})
    raw = str(
        options.get("readout_protocol", options.get("measurement_protocol", "dispersive_reflectometry"))
        or "dispersive_reflectometry"
    ).strip().lower()
    if raw in {"heterodyne", "heterodyne_sme", "heterodyne-sme", "sme_heterodyne"}:
        return "heterodyne_sme"
    if raw in {"homodyne", "homodyne_sme", "homodyne-sme", "sme_homodyne"}:
        return "homodyne_sme"
    if raw in {
        "photon_counting",
        "photon-counting",
        "photon_counting_sme",
        "photon-counting-sme",
        "photocurrent",
        "photocurrent_sme",
        "counting_sme",
        "sme_photon_counting",
    }:
        return "photon_counting_sme"
    return "dispersive_reflectometry"
