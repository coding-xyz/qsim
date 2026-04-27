"""Catalog and instantiation helpers for gate-to-pulse mappings."""

from __future__ import annotations

import math
from typing import Any

from qsim.common.unit_schema import MODEL_HARDWARE_KEYS, reject_unknown_keys
from qsim.common.schemas import Carrier, PulseSpec
from qsim.pulse.shapes import make_shape

PULSE_GATE_MAP_SCHEMA = "qsim.pulse-gate-map.v1"
NS_TO_S = 1e-9
DEFAULT_BREAK_KEEP_HEAD_S = 60.0 * NS_TO_S
DEFAULT_BREAK_KEEP_TAIL_S = 60.0 * NS_TO_S
DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_S = 30.0 * NS_TO_S
DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_S = 30.0 * NS_TO_S

# Backward-compatible aliases for display-layer code still phrased in ns.
DEFAULT_BREAK_KEEP_HEAD_NS = DEFAULT_BREAK_KEEP_HEAD_S * 1e9
DEFAULT_BREAK_KEEP_TAIL_NS = DEFAULT_BREAK_KEEP_TAIL_S * 1e9
DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_NS = DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_S * 1e9
DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_NS = DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_S * 1e9


def breakable_params(
    *,
    keep_head_s: float,
    keep_tail_s: float,
    break_kind: str,
    break_stage: str | None = None,
) -> dict[str, Any]:
    """Return standard breakability metadata stored on pulse params."""
    out: dict[str, Any] = {
        "breakable": True,
        "break_keep_head_s": float(keep_head_s),
        "break_keep_tail_s": float(keep_tail_s),
        "break_kind": str(break_kind),
    }
    if break_stage is not None:
        out["break_stage"] = str(break_stage)
    return out


def pulse_break_window(channel_name: str, pulse: PulseSpec) -> tuple[float, float] | None:
    """Return breakable middle window for one pulse if explicitly allowed."""
    params = dict(getattr(pulse, "params", {}) or {})
    if not bool(params.get("breakable", False)):
        return None
    keep_head_s = float(params.get("break_keep_head_s", DEFAULT_BREAK_KEEP_HEAD_S))
    keep_tail_s = float(params.get("break_keep_tail_s", DEFAULT_BREAK_KEEP_TAIL_S))
    t0 = float(pulse.t0_s)
    t1 = float(pulse.t1_s)
    b0 = t0 + max(0.0, keep_head_s)
    b1 = t1 - max(0.0, keep_tail_s)
    return (b0, b1) if b1 > b0 else None


def _normalized_pulse_area_s(shape: str, duration_s: float, params: dict[str, Any]) -> float:
    sampler = make_shape(shape, params)
    n = 257
    if duration_s <= 0.0:
        return 0.0
    dt = duration_s / (n - 1)
    values = [sampler.sample(i * dt, 0.0, duration_s, 1.0) for i in range(n)]
    area = 0.0
    for i in range(n - 1):
        area += 0.5 * (values[i] + values[i + 1]) * dt
    return max(area, 1e-18)


def _xy_rotation_amp_rad_s(*, shape: str, duration_s: float, params: dict[str, Any], rotation_rad: float) -> float:
    area_s = _normalized_pulse_area_s(shape, duration_s, params)
    return float(rotation_rad) / (2.0 * area_s)


def _single_qubit_rotation_rad(gate_name: str) -> float:
    gate = str(gate_name).lower()
    if gate == "x":
        return math.pi
    if gate == "sx":
        return 0.5 * math.pi
    return 0.0


def _single_qubit_xy_phase_rad(gate_name: str) -> float:
    gate = str(gate_name).lower()
    if gate == "ry":
        return 0.5 * math.pi
    return 0.0


def _single_qubit_shape(cfg: dict[str, Any]) -> str:
    shape = str(cfg.get("single_qubit_shape", "gaussian")).strip().lower()
    if shape not in {"gaussian", "drag", "rect"}:
        return "gaussian"
    return shape


def _single_qubit_shape_hardware_keys(cfg: dict[str, Any]) -> list[str]:
    keys = ["gate_duration_ns", "xy_freq_Hz", "single_qubit_shape"]
    shape = _single_qubit_shape(cfg)
    if shape in {"gaussian", "drag"}:
        keys.append("single_qubit_sigma_fraction")
    if shape == "drag":
        keys.append("single_qubit_drag_beta")
    if shape == "rect":
        keys.append("single_qubit_rect_edge_ns")
    return keys


def _single_qubit_shape_params(
    cfg: dict[str, Any],
    *,
    rotation_rad: float,
    rotation_axis: str,
) -> tuple[str, dict[str, Any]]:
    gate_dur_s = float(cfg["gate_duration_ns"]) * NS_TO_S
    shape = _single_qubit_shape(cfg)
    params: dict[str, Any] = {
        "rotation_rad": float(rotation_rad),
        "rotation_axis": str(rotation_axis),
    }
    if shape in {"gaussian", "drag"}:
        sigma_fraction = max(float(cfg.get("single_qubit_sigma_fraction", 1.0 / 6.0)), 1e-6)
        params["sigma_s"] = max(gate_dur_s * sigma_fraction, 1e-18)
    if shape == "drag":
        params["beta"] = float(cfg.get("single_qubit_drag_beta", 0.35))
    if shape == "rect":
        edge_s = max(float(cfg.get("single_qubit_rect_edge_ns", 0.0)), 0.0) * NS_TO_S
        params["rise_s"] = edge_s
        params["fall_s"] = edge_s
    return shape, params


def resolve_lowering_hardware(hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize lowering device/pulse knobs into one resolved config."""
    hw = hw or {}
    reject_unknown_keys("device", hw, MODEL_HARDWARE_KEYS)
    gate_dur = float(hw.get("gate_duration_ns", 20.0))
    measure_dur = float(hw.get("measure_duration_ns", 200.0))
    edge_ns = float(hw.get("rect_edge_ns", 2.0))
    schedule_value = hw.get("schedule", hw.get("schedule_policy", "serial"))
    resolved = {
        "xy_freq_Hz": float(hw.get("xy_freq_Hz", 5.0e9)),
        "ro_freq_Hz": float(hw.get("ro_freq_Hz", 6.5e9)),
        "schedule_policy": str(schedule_value).strip().lower() or "serial",
        "gate_duration_ns": gate_dur,
        "measure_duration_ns": measure_dur,
        "measure_amp": float(hw.get("measure_amp", 0.8)),
        "rect_edge_ns": edge_ns,
        "readout_edge_ns": float(hw.get("readout_edge_ns", edge_ns)),
        "single_qubit_shape": _single_qubit_shape(hw),
        "single_qubit_sigma_fraction": float(hw.get("single_qubit_sigma_fraction", 1.0 / 6.0)),
        "single_qubit_drag_beta": float(hw.get("single_qubit_drag_beta", 0.35)),
        "single_qubit_rect_edge_ns": float(hw.get("single_qubit_rect_edge_ns", hw.get("rect_edge_ns", 0.0))),
        "reset_measure_duration_ns": float(hw.get("reset_measure_duration_ns", max(measure_dur, 400.0))),
        "reset_deplete_duration_ns": float(hw.get("reset_deplete_duration_ns", 150.0)),
        "reset_latency_duration_ns": float(hw.get("reset_latency_duration_ns", 120.0)),
        "reset_pi_duration_ns": float(hw.get("reset_pi_duration_ns", gate_dur)),
        "reset_measure_amp": float(hw.get("reset_measure_amp", 0.8)),
        "reset_deplete_amp": float(hw.get("reset_deplete_amp", 0.15)),
        "reset_pi_amp": float(hw.get("reset_pi_amp", 1.0)),
        "reset_cond_on": int(hw.get("reset_cond_on", 1)),
        "reset_apply_feedback": bool(hw.get("reset_apply_feedback", True)),
        "reset_feedback_policy": str(hw.get("reset_feedback_policy", "parallel")).strip().lower() or "parallel",
    }
    measure_segments = list(hw.get("measure_segments", []) or [])
    if measure_segments:
        resolved["measure_segments"] = [
            {
                "duration_ns": float(seg.get("duration_ns", 0.0) or 0.0),
                "amp": float(seg.get("amp", resolved["measure_amp"]) or resolved["measure_amp"]),
                "edge_ns": float(seg.get("edge_ns", resolved["readout_edge_ns"]) or resolved["readout_edge_ns"]),
                "rise_ns": float(seg.get("rise_ns", seg.get("edge_ns", resolved["readout_edge_ns"])) or 0.0),
                "fall_ns": float(seg.get("fall_ns", seg.get("edge_ns", resolved["readout_edge_ns"])) or 0.0),
                "shape": str(seg.get("shape", "readout") or "readout"),
            }
            for seg in measure_segments
            if float(seg.get("duration_ns", 0.0) or 0.0) > 0.0
        ]
        if resolved["measure_segments"]:
            resolved["measure_duration_ns"] = float(sum(seg["duration_ns"] for seg in resolved["measure_segments"]))
            resolved["measure_amp"] = float(resolved["measure_segments"][0]["amp"])
    resolved["measure_start_delay_ns"] = float(hw.get("measure_start_delay_ns", 0.0) or 0.0)
    return resolved


def _xy_carrier(cfg: dict[str, Any], phase: float = 0.0) -> dict[str, float]:
    return {"freq": float(cfg["xy_freq_Hz"]), "phase": float(phase)}


def _ro_carrier(cfg: dict[str, Any], phase: float = 0.0) -> dict[str, float]:
    return {"freq": float(cfg["ro_freq_Hz"]), "phase": float(phase)}


def _shared_single_qubit_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration_ns"])
    shape, params = _single_qubit_shape_params(cfg, rotation_rad=0.0, rotation_axis="x")
    return [
        {
            "kind": "pulse",
            "role": "each_qubit",
            "channel_template": "XY_{q}",
            "start_ns": 0.0,
            "end_ns": gate_dur,
            "duration_ns": gate_dur,
            "shape": shape,
            "amp": 0.0,
            "params": params,
            "carrier": _xy_carrier(cfg),
            "hardware_keys": _single_qubit_shape_hardware_keys(cfg),
        }
    ]


def _z_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    del cfg
    return []


def _h_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration_ns"])
    xy_shape, xy_params = _single_qubit_shape_params(cfg, rotation_rad=0.5 * math.pi, rotation_axis="y")
    return [
        {
            "kind": "pulse",
            "role": "each_qubit",
            "channel_template": "XY_{q}",
            "start_ns": 0.0,
            "end_ns": gate_dur,
            "duration_ns": gate_dur,
            "shape": xy_shape,
            "amp": 0.0,
            "params": xy_params,
            "carrier": _xy_carrier(cfg, phase=0.5 * math.pi),
            "hardware_keys": _single_qubit_shape_hardware_keys(cfg),
        },
    ]


def _cz_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration_ns"])
    edge_s = float(cfg["rect_edge_ns"]) * NS_TO_S
    duration = 2.0 * gate_dur
    duration_s = duration * NS_TO_S
    amp = -math.pi / max(duration_s, 1e-18)
    return [
        {
            "kind": "pulse",
            "role": "pair_coupler",
            "channel_template": "TC_{pair_index}",
            "start_ns": 0.0,
            "end_ns": duration,
            "duration_ns": duration,
            "shape": "rect",
            "amp": amp,
            "params": {"rise_s": edge_s, "fall_s": edge_s, "target_conditional_phase_rad": math.pi},
            "carrier": None,
            "hardware_keys": ["gate_duration_ns", "rect_edge_ns"],
        }
    ]


def _cx_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration_ns"])
    gate_dur_s = gate_dur * NS_TO_S
    edge_s = float(cfg["rect_edge_ns"]) * NS_TO_S
    duration = 2.0 * gate_dur
    return [
        {
            "kind": "pulse",
            "role": "control_qubit",
            "channel_template": "XY_{control}",
            "start_ns": 0.0,
            "end_ns": duration,
            "duration_ns": duration,
            "shape": "drag",
            "amp": 1.2,
            "params": {"beta": 0.35, "sigma_s": gate_dur_s / 4.0},
            "carrier": _xy_carrier(cfg, phase=0.0),
            "hardware_keys": ["gate_duration_ns", "xy_freq_Hz"],
        },
        {
            "kind": "pulse",
            "role": "target_qubit",
            "channel_template": "XY_{target}",
            "start_ns": 0.0,
            "end_ns": duration,
            "duration_ns": duration,
            "shape": "drag",
            "amp": 1.2,
            "params": {"beta": 0.35, "sigma_s": gate_dur_s / 4.0},
            "carrier": _xy_carrier(cfg, phase=0.2),
            "hardware_keys": ["gate_duration_ns", "xy_freq_Hz"],
        },
        {
            "kind": "pulse",
            "role": "pair_coupler",
            "channel_template": "TC_{pair_index}",
            "start_ns": 0.0,
            "end_ns": duration,
            "duration_ns": duration,
            "shape": "rect",
            "amp": 0.75,
            "params": {"rise_s": edge_s, "fall_s": edge_s},
            "carrier": None,
            "hardware_keys": ["gate_duration_ns", "rect_edge_ns"],
        },
    ]


def _measure_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    segments = list(cfg.get("measure_segments", []) or [])
    if not segments:
        segments = [
            {
                "duration_ns": float(cfg["measure_duration_ns"]),
                "amp": float(cfg["measure_amp"]),
                "edge_ns": float(cfg["readout_edge_ns"]),
                "shape": "readout",
            }
        ]
    steps: list[dict[str, Any]] = []
    start_ns = 0.0
    for idx, seg in enumerate(segments):
        duration = float(seg.get("duration_ns", 0.0) or 0.0)
        if duration <= 0.0:
            continue
        edge_s = float(seg.get("edge_ns", cfg["readout_edge_ns"])) * NS_TO_S
        end_ns = start_ns + duration
        steps.append(
            {
                "kind": "pulse",
                "role": "each_qubit",
                "channel_template": "RO_{q}",
                "start_ns": start_ns,
                "end_ns": end_ns,
                "duration_ns": duration,
                "shape": str(seg.get("shape", "readout") or "readout"),
                "amp": float(seg.get("amp", cfg["measure_amp"]) or cfg["measure_amp"]),
                "params": {
                    "rise_s": edge_s,
                    "fall_s": edge_s,
                    "measure_segment_index": idx,
                    "measure_segment_count": len(segments),
                    **breakable_params(
                        keep_head_s=DEFAULT_BREAK_KEEP_HEAD_S,
                        keep_tail_s=DEFAULT_BREAK_KEEP_TAIL_S,
                        break_kind="readout",
                        break_stage="measure",
                    ),
                },
                "carrier": _ro_carrier(cfg),
                "hardware_keys": ["measure_duration_ns", "measure_amp", "measure_segments", "readout_edge_ns", "ro_freq_Hz"],
            }
        )
        start_ns = end_ns
    return steps


def _reset_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    t1 = float(cfg["reset_measure_duration_ns"])
    t2 = t1 + float(cfg["reset_deplete_duration_ns"])
    t3 = t2 + float(cfg["reset_latency_duration_ns"])
    t4 = t3 + (float(cfg["reset_pi_duration_ns"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
    edge_s = float(cfg["readout_edge_ns"]) * NS_TO_S
    steps: list[dict[str, Any]] = [
        {
            "kind": "pulse",
            "stage": "reset_measure",
            "role": "each_qubit",
            "channel_template": "RO_{q}",
            "start_ns": 0.0,
            "end_ns": t1,
            "duration_ns": t1,
            "shape": "readout",
            "amp": float(cfg["reset_measure_amp"]),
            "params": {
                "stage": "reset_measure",
                "rise_s": edge_s,
                "fall_s": edge_s,
                **breakable_params(
                    keep_head_s=DEFAULT_BREAK_KEEP_HEAD_S,
                    keep_tail_s=DEFAULT_BREAK_KEEP_TAIL_S,
                    break_kind="reset",
                    break_stage="reset_measure",
                ),
            },
            "carrier": _ro_carrier(cfg),
            "hardware_keys": ["reset_measure_duration_ns", "reset_measure_amp", "readout_edge_ns", "ro_freq_Hz"],
        },
        {
            "kind": "pulse",
            "stage": "reset_deplete",
            "role": "each_qubit",
            "channel_template": "RO_{q}",
            "start_ns": t1,
            "end_ns": t2,
            "duration_ns": t2 - t1,
            "shape": "rect",
            "amp": float(cfg["reset_deplete_amp"]),
            "params": {
                "stage": "reset_deplete",
                "rise_s": edge_s,
                "fall_s": edge_s,
                **breakable_params(
                    keep_head_s=DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_S,
                    keep_tail_s=DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_S,
                    break_kind="reset",
                    break_stage="reset_deplete",
                ),
            },
            "carrier": _ro_carrier(cfg),
            "hardware_keys": ["reset_deplete_duration_ns", "reset_deplete_amp", "readout_edge_ns", "ro_freq_Hz"],
        },
        {
            "kind": "wait",
            "stage": "feedback_latency",
            "role": "each_qubit",
            "channel_template": None,
            "start_ns": t2,
            "end_ns": t3,
            "duration_ns": t3 - t2,
            "hardware_keys": ["reset_latency_duration_ns"],
        },
    ]
    if bool(cfg["reset_apply_feedback"]) and t4 > t3:
        steps.append(
            {
                "kind": "pulse",
                "stage": "reset_conditional_pi",
                "role": "each_qubit",
                "channel_template": "XY_{q}",
                "start_ns": t3,
                "end_ns": t4,
                "duration_ns": t4 - t3,
                "shape": "gaussian",
                "amp": float(cfg["reset_pi_amp"]),
                "params": {
                    "stage": "reset_conditional_pi",
                    "sigma_s": max(float(cfg["reset_pi_duration_ns"]) * NS_TO_S / 6.0, 1e-18),
                    "conditional": True,
                    "cond_on": int(cfg["reset_cond_on"]),
                },
                "carrier": _xy_carrier(cfg),
                "hardware_keys": ["reset_pi_duration_ns", "reset_pi_amp", "reset_cond_on", "xy_freq_Hz"],
            }
        )
    return steps


def _catalog_entry(
    *,
    name: str,
    arity: int | str,
    duration_ns: float,
    steps: list[dict[str, Any]],
    summary: str,
    hardware_keys: list[str],
    shared_recipe_group: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    out = {
        "op_name": name,
        "qubit_arity": arity,
        "duration_ns": duration_ns,
        "summary": summary,
        "steps": steps,
        "hardware_keys": hardware_keys,
    }
    if shared_recipe_group is not None:
        out["shared_recipe_group"] = shared_recipe_group
    if note is not None:
        out["note"] = note
    return out


def build_gate_mapping_catalog(hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a machine-readable catalog of supported gate-to-pulse mappings."""
    cfg = resolve_lowering_hardware(hw)
    gate_dur = float(cfg["gate_duration_ns"])
    measure_dur = float(cfg["measure_duration_ns"])
    reset_total = (
        float(cfg["reset_measure_duration_ns"])
        + float(cfg["reset_deplete_duration_ns"])
        + float(cfg["reset_latency_duration_ns"])
        + (float(cfg["reset_pi_duration_ns"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
    )
    operations = [
        _catalog_entry(
            name="x",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Single-qubit XY pulse with configurable gaussian, DRAG, or rectangular envelope.",
            hardware_keys=_single_qubit_shape_hardware_keys(cfg),
            shared_recipe_group="single_qubit_xy_configurable",
            note="Current lowering uses the same physical recipe as sx.",
        ),
        _catalog_entry(
            name="sx",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Single-qubit XY pulse with configurable gaussian, DRAG, or rectangular envelope.",
            hardware_keys=_single_qubit_shape_hardware_keys(cfg),
            shared_recipe_group="single_qubit_xy_configurable",
            note="Current lowering uses the same physical recipe as x.",
        ),
        _catalog_entry(
            name="h",
            arity=1,
            duration_ns=gate_dur,
            steps=_h_steps(cfg),
            summary="Hadamard lowering as one physical Y(pi/2) pulse plus a virtual Z(pi) frame update.",
            hardware_keys=_single_qubit_shape_hardware_keys(cfg),
            shared_recipe_group="single_qubit_hadamard_virtual_z",
            note="The emitted pulse is Ry(pi/2); the trailing Z(pi) is virtual and is applied by lowering as a frame update.",
        ),
        _catalog_entry(
            name="rx",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Parametric single-qubit XY pulse with configurable envelope and angle from gate parameter.",
            hardware_keys=_single_qubit_shape_hardware_keys(cfg),
            shared_recipe_group="single_qubit_xy_configurable",
            note="The gate parameter sets rotation_rad; control_scale rescales the realized angle.",
        ),
        _catalog_entry(
            name="ry",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Parametric single-qubit XY pulse with configurable envelope and quadrature phase shift.",
            hardware_keys=_single_qubit_shape_hardware_keys(cfg),
            shared_recipe_group="single_qubit_xy_configurable",
            note="The gate parameter sets rotation_rad; control_scale rescales the realized angle.",
        ),
        _catalog_entry(
            name="z",
            arity=1,
            duration_ns=0.0,
            steps=_z_steps(cfg),
            summary="Virtual single-qubit Z rotation implemented as a frame update with no emitted pulse.",
            hardware_keys=[],
            shared_recipe_group="single_qubit_virtual_z",
            note="Lowering emits no pulse and only updates the per-qubit XY frame phase.",
        ),
        _catalog_entry(
            name="rz",
            arity=1,
            duration_ns=0.0,
            steps=_z_steps(cfg),
            summary="Virtual parametric Z rotation implemented as a frame update with no emitted pulse.",
            hardware_keys=[],
            shared_recipe_group="single_qubit_virtual_z",
            note="Lowering emits no pulse and only updates the per-qubit XY frame phase.",
        ),
        _catalog_entry(
            name="cz",
            arity=2,
            duration_ns=2.0 * gate_dur,
            steps=_cz_steps(cfg),
            summary="Two-qubit coupler pulse on TC_*.",
            hardware_keys=["gate_duration_ns", "rect_edge_ns"],
        ),
        _catalog_entry(
            name="cx",
            arity=2,
            duration_ns=2.0 * gate_dur,
            steps=_cx_steps(cfg),
            summary="Two XY DRAG pulses plus one coupler pulse.",
            hardware_keys=["gate_duration_ns", "rect_edge_ns", "xy_freq_Hz"],
        ),
        _catalog_entry(
            name="measure",
            arity="1+",
            duration_ns=measure_dur,
            steps=_measure_steps(cfg),
            summary="Readout pulse on RO_* for each measured qubit.",
            hardware_keys=["measure_duration_ns", "measure_amp", "readout_edge_ns", "ro_freq_Hz"],
            note="Consecutive measure instructions are aligned in parallel by lowering.",
        ),
        _catalog_entry(
            name="reset",
            arity="1+",
            duration_ns=reset_total,
            steps=_reset_steps(cfg),
            summary="Measurement-driven active reset with depletion, latency, and optional feedback pi.",
            hardware_keys=[
                "reset_measure_duration_ns",
                "reset_deplete_duration_ns",
                "reset_latency_duration_ns",
                "reset_pi_duration_ns",
                "reset_measure_amp",
                "reset_deplete_amp",
                "reset_pi_amp",
                "reset_cond_on",
                "reset_apply_feedback",
                "readout_edge_ns",
                "xy_freq_Hz",
                "ro_freq_Hz",
            ],
            note="Consecutive reset instructions are aligned in parallel by lowering.",
        ),
        _catalog_entry(
            name="barrier",
            arity="any",
            duration_ns=0.0,
            steps=[],
            summary="No-op in pulse lowering.",
            hardware_keys=[],
            note="No pulse is emitted and the time cursor does not advance.",
        ),
    ]
    return {
        "schema": PULSE_GATE_MAP_SCHEMA,
        "resolved_hardware": cfg,
        "operations": operations,
    }


def instantiate_operation_recipe(
    gate_name: str,
    qubits: list[int],
    *,
    gate_params: list[float] | None = None,
    start_ns: float,
    hw: dict[str, Any] | None = None,
    tc_index: int | None = None,
    reset_feedback_offset_ns: float = 0.0,
) -> tuple[list[tuple[str, PulseSpec]], float, list[dict[str, Any]]]:
    """Instantiate one operation into scheduled pulses and events."""
    cfg = resolve_lowering_hardware(hw)
    gate = str(gate_name).lower()
    pulses: list[tuple[str, PulseSpec]] = []
    events: list[dict[str, Any]] = []

    def add(channel: str, t0_ns: float, t1_ns: float, amp: float, shape: str, params: dict[str, Any], carrier: dict[str, float] | None) -> None:
        pulses.append(
            (
                channel,
                PulseSpec(
                    t0_s=float(t0_ns) * NS_TO_S,
                    t1_s=float(t1_ns) * NS_TO_S,
                    amp=amp,
                    shape=shape,
                    params=dict(params),
                    carrier=Carrier(freq=float(carrier["freq"]), phase=float(carrier.get("phase", 0.0))) if carrier is not None else None,
                ),
            )
        )

    gate_dur = float(cfg["gate_duration_ns"])
    gate_dur_s = gate_dur * NS_TO_S
    if gate in {"x", "sx", "rx", "ry"}:
        if gate in {"rx", "ry"}:
            rotation_rad = float(list(gate_params or [0.0])[0])
        else:
            rotation_rad = _single_qubit_rotation_rad(gate)
        shape, params = _single_qubit_shape_params(
            cfg,
            rotation_rad=float(rotation_rad),
            rotation_axis="y" if gate == "ry" else "x",
        )
        amp = _xy_rotation_amp_rad_s(
            shape=shape,
            duration_s=gate_dur_s,
            params=params,
            rotation_rad=float(params["rotation_rad"]),
        )
        for q in qubits:
            add(
                f"XY_{q}",
                start_ns,
                start_ns + gate_dur,
                amp,
                shape,
                params,
                _xy_carrier(cfg, phase=_single_qubit_xy_phase_rad(gate)),
            )
        return pulses, gate_dur, events

    if gate == "h":
        rotation_rad = 0.5 * math.pi
        shape, params = _single_qubit_shape_params(
            cfg,
            rotation_rad=rotation_rad,
            rotation_axis="y",
        )
        amp = _xy_rotation_amp_rad_s(
            shape=shape,
            duration_s=gate_dur_s,
            params=params,
            rotation_rad=float(params["rotation_rad"]),
        )
        for q in qubits:
            add(
                f"XY_{q}",
                start_ns,
                start_ns + gate_dur,
                amp,
                shape,
                params,
                _xy_carrier(cfg, phase=0.5 * math.pi),
            )
        return pulses, gate_dur, events

    if gate in {"rz", "z"}:
        return pulses, 0.0, events

    if gate == "cz":
        edge_s = float(cfg["rect_edge_ns"]) * NS_TO_S
        duration = 2.0 * gate_dur
        duration_s = duration * NS_TO_S
        amp = -math.pi / max(duration_s, 1e-18)
        add(
            f"TC_{0 if tc_index is None else int(tc_index)}",
            start_ns,
            start_ns + duration,
            amp,
            "rect",
            {"rise_s": edge_s, "fall_s": edge_s, "target_conditional_phase_rad": math.pi},
            None,
        )
        return pulses, duration, events

    if gate == "cx":
        qs = qubits or [0, 1]
        duration = 2.0 * gate_dur
        gate_sigma_s = gate_dur_s / 4.0
        edge_s = float(cfg["rect_edge_ns"]) * NS_TO_S
        add(f"XY_{qs[0]}", start_ns, start_ns + duration, 1.2, "drag", {"beta": 0.35, "sigma_s": gate_sigma_s}, _xy_carrier(cfg, phase=0.0))
        add(f"XY_{qs[-1]}", start_ns, start_ns + duration, 1.2, "drag", {"beta": 0.35, "sigma_s": gate_sigma_s}, _xy_carrier(cfg, phase=0.2))
        add(f"TC_{0 if tc_index is None else int(tc_index)}", start_ns, start_ns + duration, 0.75, "rect", {"rise_s": edge_s, "fall_s": edge_s}, None)
        return pulses, duration, events

    if gate == "measure":
        segments = list(cfg.get("measure_segments", []) or [])
        if not segments:
            segments = [
                {
                    "duration_ns": float(cfg["measure_duration_ns"]),
                    "amp": float(cfg["measure_amp"]),
                    "edge_ns": float(cfg["readout_edge_ns"]),
                    "shape": "readout",
                }
            ]
        duration = float(sum(float(seg.get("duration_ns", 0.0) or 0.0) for seg in segments))
        for q in qubits:
            offset_ns = 0.0
            for idx, seg in enumerate(segments):
                seg_duration = float(seg.get("duration_ns", 0.0) or 0.0)
                if seg_duration <= 0.0:
                    continue
                seg_rise_ns = float(seg.get("rise_ns", seg.get("edge_ns", cfg["readout_edge_ns"])) or 0.0)
                seg_fall_ns = float(seg.get("fall_ns", seg.get("edge_ns", cfg["readout_edge_ns"])) or 0.0)
                add(
                    f"RO_{q}",
                    start_ns + offset_ns,
                    start_ns + offset_ns + seg_duration,
                    float(seg.get("amp", cfg["measure_amp"]) or cfg["measure_amp"]),
                    str(seg.get("shape", "readout") or "readout"),
                    {
                        "rise_s": seg_rise_ns * NS_TO_S,
                        "fall_s": seg_fall_ns * NS_TO_S,
                        "measure_segment_index": idx,
                        "measure_segment_count": len(segments),
                        **breakable_params(
                            keep_head_s=DEFAULT_BREAK_KEEP_HEAD_S,
                            keep_tail_s=DEFAULT_BREAK_KEEP_TAIL_S,
                            break_kind="readout",
                            break_stage="measure",
                        ),
                    },
                    _ro_carrier(cfg),
                )
                offset_ns += seg_duration
        return pulses, duration, events

    if gate == "reset":
        qs = qubits or [0]
        t0 = start_ns
        t1 = t0 + float(cfg["reset_measure_duration_ns"])
        t2 = t1 + float(cfg["reset_deplete_duration_ns"])
        t3 = t2 + float(cfg["reset_latency_duration_ns"]) + max(0.0, float(reset_feedback_offset_ns))
        t4 = t3 + (float(cfg["reset_pi_duration_ns"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
        edge_s = float(cfg["readout_edge_ns"]) * NS_TO_S
        for q in qs:
            add(
                f"RO_{q}",
                t0,
                t1,
                float(cfg["reset_measure_amp"]),
                "readout",
                {
                    "stage": "reset_measure",
                    "rise_s": edge_s,
                    "fall_s": edge_s,
                    **breakable_params(
                        keep_head_s=DEFAULT_BREAK_KEEP_HEAD_S,
                        keep_tail_s=DEFAULT_BREAK_KEEP_TAIL_S,
                        break_kind="reset",
                        break_stage="reset_measure",
                    ),
                },
                _ro_carrier(cfg),
            )
            add(
                f"RO_{q}",
                t1,
                t2,
                float(cfg["reset_deplete_amp"]),
                "rect",
                {
                    "stage": "reset_deplete",
                    "rise_s": edge_s,
                    "fall_s": edge_s,
                    **breakable_params(
                        keep_head_s=DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_S,
                        keep_tail_s=DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_S,
                        break_kind="reset",
                        break_stage="reset_deplete",
                    ),
                },
                _ro_carrier(cfg),
            )
            if bool(cfg["reset_apply_feedback"]) and t4 > t3:
                reset_pi_duration_s = float(cfg["reset_pi_duration_ns"]) * NS_TO_S
                params = {
                    "stage": "reset_conditional_pi",
                    "sigma_s": max(reset_pi_duration_s / 6.0, 1e-18),
                    "conditional": True,
                    "cond_on": int(cfg["reset_cond_on"]),
                    "rotation_rad": math.pi,
                }
                amp = _xy_rotation_amp_rad_s(
                    shape="gaussian",
                    duration_s=max(t4 - t3, 0.0) * NS_TO_S,
                    params=params,
                    rotation_rad=float(params["rotation_rad"]),
                )
                add(
                    f"XY_{q}",
                    t3,
                    t4,
                    amp,
                    "gaussian",
                    params,
                    _xy_carrier(cfg),
                )
            events.append(
                {
                    "qubit": int(q),
                    "t0": float(t0),
                    "t_meas_end": float(t1),
                    "t_deplete_end": float(t2),
                    "t_feedback_end": float(t3),
                    "t1": float(t4),
                    "conditional_on": int(cfg["reset_cond_on"]),
                    "apply_feedback": bool(cfg["reset_apply_feedback"]),
                    "feedback_offset_ns": float(max(0.0, float(reset_feedback_offset_ns))),
                }
            )
        return pulses, t4 - t0, events

    if gate == "barrier":
        return pulses, 0.0, events

    return pulses, gate_dur, events
