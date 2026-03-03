"""Catalog and instantiation helpers for gate-to-pulse mappings."""

from __future__ import annotations

from typing import Any

from qsim.common.schemas import Carrier, PulseSpec

PULSE_GATE_MAP_SCHEMA = "qsim.pulse-gate-map.v1"
DEFAULT_BREAK_KEEP_HEAD_NS = 60.0
DEFAULT_BREAK_KEEP_TAIL_NS = 60.0
DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_NS = 30.0
DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_NS = 30.0


def breakable_params(
    *,
    keep_head_ns: float,
    keep_tail_ns: float,
    break_kind: str,
    break_stage: str | None = None,
) -> dict[str, Any]:
    """Return standard breakability metadata stored on pulse params."""
    out: dict[str, Any] = {
        "breakable": True,
        "break_keep_head_ns": float(keep_head_ns),
        "break_keep_tail_ns": float(keep_tail_ns),
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
    keep_head_ns = float(params.get("break_keep_head_ns", DEFAULT_BREAK_KEEP_HEAD_NS))
    keep_tail_ns = float(params.get("break_keep_tail_ns", DEFAULT_BREAK_KEEP_TAIL_NS))
    t0 = float(pulse.t0)
    t1 = float(pulse.t1)
    b0 = t0 + max(0.0, keep_head_ns)
    b1 = t1 - max(0.0, keep_tail_ns)
    return (b0, b1) if b1 > b0 else None


def resolve_lowering_hardware(hw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize lowering hardware knobs into one resolved config."""
    hw = hw or {}
    gate_dur = float(hw.get("gate_duration", 20.0))
    measure_dur = float(hw.get("measure_duration", 200.0))
    edge_ns = float(hw.get("rect_edge_ns", 2.0))
    return {
        "xy_freq_hz": float(hw.get("xy_freq_hz", 5.0e9)),
        "ro_freq_hz": float(hw.get("ro_freq_hz", 6.5e9)),
        "schedule_policy": str(hw.get("schedule_policy", "serial")).strip().lower() or "serial",
        "gate_duration": gate_dur,
        "measure_duration": measure_dur,
        "rect_edge_ns": edge_ns,
        "readout_edge_ns": float(hw.get("readout_edge_ns", edge_ns)),
        "reset_measure_duration": float(hw.get("reset_measure_duration", max(measure_dur, 400.0))),
        "reset_deplete_duration": float(hw.get("reset_deplete_duration", 150.0)),
        "reset_latency_duration": float(hw.get("reset_latency_duration", 120.0)),
        "reset_pi_duration": float(hw.get("reset_pi_duration", gate_dur)),
        "reset_measure_amp": float(hw.get("reset_measure_amp", 0.8)),
        "reset_deplete_amp": float(hw.get("reset_deplete_amp", 0.15)),
        "reset_pi_amp": float(hw.get("reset_pi_amp", 1.0)),
        "reset_cond_on": int(hw.get("reset_cond_on", 1)),
        "reset_apply_feedback": bool(hw.get("reset_apply_feedback", True)),
        "reset_feedback_policy": str(hw.get("reset_feedback_policy", "parallel")).strip().lower() or "parallel",
    }


def _xy_carrier(cfg: dict[str, Any], phase: float = 0.0) -> dict[str, float]:
    return {"freq": float(cfg["xy_freq_hz"]), "phase": float(phase)}


def _ro_carrier(cfg: dict[str, Any], phase: float = 0.0) -> dict[str, float]:
    return {"freq": float(cfg["ro_freq_hz"]), "phase": float(phase)}


def _shared_single_qubit_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration"])
    return [
        {
            "kind": "pulse",
            "role": "each_qubit",
            "channel_template": "XY_{q}",
            "start_ns": 0.0,
            "end_ns": gate_dur,
            "duration_ns": gate_dur,
            "shape": "gaussian",
            "amp": 1.0,
            "params": {"sigma": gate_dur / 6.0},
            "carrier": _xy_carrier(cfg),
            "hardware_keys": ["gate_duration", "xy_freq_hz"],
        }
    ]


def _z_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration"])
    edge_ns = float(cfg["rect_edge_ns"])
    return [
        {
            "kind": "pulse",
            "role": "each_qubit",
            "channel_template": "Z_{q}",
            "start_ns": 0.0,
            "end_ns": gate_dur,
            "duration_ns": gate_dur,
            "shape": "rect",
            "amp": 0.2,
            "params": {"rise_ns": edge_ns, "fall_ns": edge_ns},
            "carrier": None,
            "hardware_keys": ["gate_duration", "rect_edge_ns"],
        }
    ]


def _cz_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration"])
    edge_ns = float(cfg["rect_edge_ns"])
    duration = 2.0 * gate_dur
    return [
        {
            "kind": "pulse",
            "role": "pair_coupler",
            "channel_template": "TC_{pair_index}",
            "start_ns": 0.0,
            "end_ns": duration,
            "duration_ns": duration,
            "shape": "rect",
            "amp": 0.75,
            "params": {"rise_ns": edge_ns, "fall_ns": edge_ns},
            "carrier": None,
            "hardware_keys": ["gate_duration", "rect_edge_ns"],
        }
    ]


def _cx_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    gate_dur = float(cfg["gate_duration"])
    edge_ns = float(cfg["rect_edge_ns"])
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
            "params": {"beta": 0.35, "sigma": gate_dur / 4.0},
            "carrier": _xy_carrier(cfg, phase=0.0),
            "hardware_keys": ["gate_duration", "xy_freq_hz"],
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
            "params": {"beta": 0.35, "sigma": gate_dur / 4.0},
            "carrier": _xy_carrier(cfg, phase=0.2),
            "hardware_keys": ["gate_duration", "xy_freq_hz"],
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
            "params": {"rise_ns": edge_ns, "fall_ns": edge_ns},
            "carrier": None,
            "hardware_keys": ["gate_duration", "rect_edge_ns"],
        },
    ]


def _measure_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    measure_dur = float(cfg["measure_duration"])
    edge_ns = float(cfg["readout_edge_ns"])
    return [
        {
            "kind": "pulse",
            "role": "each_qubit",
            "channel_template": "RO_{q}",
            "start_ns": 0.0,
            "end_ns": measure_dur,
            "duration_ns": measure_dur,
            "shape": "readout",
            "amp": 0.8,
            "params": {
                "rise_ns": edge_ns,
                "fall_ns": edge_ns,
                **breakable_params(
                    keep_head_ns=DEFAULT_BREAK_KEEP_HEAD_NS,
                    keep_tail_ns=DEFAULT_BREAK_KEEP_TAIL_NS,
                    break_kind="readout",
                    break_stage="measure",
                ),
            },
            "carrier": _ro_carrier(cfg),
            "hardware_keys": ["measure_duration", "readout_edge_ns", "ro_freq_hz"],
        }
    ]


def _reset_steps(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    t1 = float(cfg["reset_measure_duration"])
    t2 = t1 + float(cfg["reset_deplete_duration"])
    t3 = t2 + float(cfg["reset_latency_duration"])
    t4 = t3 + (float(cfg["reset_pi_duration"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
    edge_ns = float(cfg["readout_edge_ns"])
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
                "rise_ns": edge_ns,
                "fall_ns": edge_ns,
                **breakable_params(
                    keep_head_ns=DEFAULT_BREAK_KEEP_HEAD_NS,
                    keep_tail_ns=DEFAULT_BREAK_KEEP_TAIL_NS,
                    break_kind="reset",
                    break_stage="reset_measure",
                ),
            },
            "carrier": _ro_carrier(cfg),
            "hardware_keys": ["reset_measure_duration", "reset_measure_amp", "readout_edge_ns", "ro_freq_hz"],
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
                "rise_ns": edge_ns,
                "fall_ns": edge_ns,
                **breakable_params(
                    keep_head_ns=DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_NS,
                    keep_tail_ns=DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_NS,
                    break_kind="reset",
                    break_stage="reset_deplete",
                ),
            },
            "carrier": _ro_carrier(cfg),
            "hardware_keys": ["reset_deplete_duration", "reset_deplete_amp", "readout_edge_ns", "ro_freq_hz"],
        },
        {
            "kind": "wait",
            "stage": "feedback_latency",
            "role": "each_qubit",
            "channel_template": None,
            "start_ns": t2,
            "end_ns": t3,
            "duration_ns": t3 - t2,
            "hardware_keys": ["reset_latency_duration"],
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
                    "sigma": max(float(cfg["reset_pi_duration"]) / 6.0, 1e-9),
                    "conditional": True,
                    "cond_on": int(cfg["reset_cond_on"]),
                },
                "carrier": _xy_carrier(cfg),
                "hardware_keys": ["reset_pi_duration", "reset_pi_amp", "reset_cond_on", "xy_freq_hz"],
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
    gate_dur = float(cfg["gate_duration"])
    measure_dur = float(cfg["measure_duration"])
    reset_total = (
        float(cfg["reset_measure_duration"])
        + float(cfg["reset_deplete_duration"])
        + float(cfg["reset_latency_duration"])
        + (float(cfg["reset_pi_duration"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
    )
    operations = [
        _catalog_entry(
            name="x",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Single-qubit XY Gaussian pulse.",
            hardware_keys=["gate_duration", "xy_freq_hz"],
            shared_recipe_group="single_qubit_xy_gaussian",
            note="Current lowering uses the same recipe as sx and h.",
        ),
        _catalog_entry(
            name="sx",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Single-qubit XY Gaussian pulse.",
            hardware_keys=["gate_duration", "xy_freq_hz"],
            shared_recipe_group="single_qubit_xy_gaussian",
            note="Current lowering uses the same recipe as x and h.",
        ),
        _catalog_entry(
            name="h",
            arity=1,
            duration_ns=gate_dur,
            steps=_shared_single_qubit_steps(cfg),
            summary="Single-qubit XY Gaussian pulse.",
            hardware_keys=["gate_duration", "xy_freq_hz"],
            shared_recipe_group="single_qubit_xy_gaussian",
            note="Current lowering uses the same recipe as x and sx.",
        ),
        _catalog_entry(
            name="z",
            arity=1,
            duration_ns=gate_dur,
            steps=_z_steps(cfg),
            summary="Single-qubit rectangular Z pulse.",
            hardware_keys=["gate_duration", "rect_edge_ns"],
            shared_recipe_group="single_qubit_z_rect",
            note="Current lowering uses the same recipe as rz.",
        ),
        _catalog_entry(
            name="rz",
            arity=1,
            duration_ns=gate_dur,
            steps=_z_steps(cfg),
            summary="Single-qubit rectangular Z pulse.",
            hardware_keys=["gate_duration", "rect_edge_ns"],
            shared_recipe_group="single_qubit_z_rect",
            note="Current lowering uses the same recipe as z.",
        ),
        _catalog_entry(
            name="cz",
            arity=2,
            duration_ns=2.0 * gate_dur,
            steps=_cz_steps(cfg),
            summary="Two-qubit coupler pulse on TC_*.",
            hardware_keys=["gate_duration", "rect_edge_ns"],
        ),
        _catalog_entry(
            name="cx",
            arity=2,
            duration_ns=2.0 * gate_dur,
            steps=_cx_steps(cfg),
            summary="Two XY DRAG pulses plus one coupler pulse.",
            hardware_keys=["gate_duration", "rect_edge_ns", "xy_freq_hz"],
        ),
        _catalog_entry(
            name="measure",
            arity="1+",
            duration_ns=measure_dur,
            steps=_measure_steps(cfg),
            summary="Readout pulse on RO_* for each measured qubit.",
            hardware_keys=["measure_duration", "readout_edge_ns", "ro_freq_hz"],
            note="Consecutive measure instructions are aligned in parallel by lowering.",
        ),
        _catalog_entry(
            name="reset",
            arity="1+",
            duration_ns=reset_total,
            steps=_reset_steps(cfg),
            summary="Measurement-driven active reset with depletion, latency, and optional feedback pi.",
            hardware_keys=[
                "reset_measure_duration",
                "reset_deplete_duration",
                "reset_latency_duration",
                "reset_pi_duration",
                "reset_measure_amp",
                "reset_deplete_amp",
                "reset_pi_amp",
                "reset_cond_on",
                "reset_apply_feedback",
                "readout_edge_ns",
                "xy_freq_hz",
                "ro_freq_hz",
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

    def add(channel: str, t0: float, t1: float, amp: float, shape: str, params: dict[str, Any], carrier: dict[str, float] | None) -> None:
        pulses.append(
            (
                channel,
                PulseSpec(
                    t0=t0,
                    t1=t1,
                    amp=amp,
                    shape=shape,
                    params=dict(params),
                    carrier=Carrier(freq=float(carrier["freq"]), phase=float(carrier.get("phase", 0.0))) if carrier is not None else None,
                ),
            )
        )

    gate_dur = float(cfg["gate_duration"])
    if gate in {"x", "sx", "h"}:
        for q in qubits:
            add(f"XY_{q}", start_ns, start_ns + gate_dur, 1.0, "gaussian", {"sigma": gate_dur / 6.0}, _xy_carrier(cfg))
        return pulses, gate_dur, events

    if gate in {"rz", "z"}:
        edge_ns = float(cfg["rect_edge_ns"])
        for q in qubits:
            add(f"Z_{q}", start_ns, start_ns + gate_dur, 0.2, "rect", {"rise_ns": edge_ns, "fall_ns": edge_ns}, None)
        return pulses, gate_dur, events

    if gate == "cz":
        edge_ns = float(cfg["rect_edge_ns"])
        duration = 2.0 * gate_dur
        add(f"TC_{0 if tc_index is None else int(tc_index)}", start_ns, start_ns + duration, 0.75, "rect", {"rise_ns": edge_ns, "fall_ns": edge_ns}, None)
        return pulses, duration, events

    if gate == "cx":
        qs = qubits or [0, 1]
        duration = 2.0 * gate_dur
        edge_ns = float(cfg["rect_edge_ns"])
        add(f"XY_{qs[0]}", start_ns, start_ns + duration, 1.2, "drag", {"beta": 0.35, "sigma": gate_dur / 4.0}, _xy_carrier(cfg, phase=0.0))
        add(f"XY_{qs[-1]}", start_ns, start_ns + duration, 1.2, "drag", {"beta": 0.35, "sigma": gate_dur / 4.0}, _xy_carrier(cfg, phase=0.2))
        add(f"TC_{0 if tc_index is None else int(tc_index)}", start_ns, start_ns + duration, 0.75, "rect", {"rise_ns": edge_ns, "fall_ns": edge_ns}, None)
        return pulses, duration, events

    if gate == "measure":
        duration = float(cfg["measure_duration"])
        edge_ns = float(cfg["readout_edge_ns"])
        for q in qubits:
            add(
                f"RO_{q}",
                start_ns,
                start_ns + duration,
                0.8,
                "readout",
                {
                    "rise_ns": edge_ns,
                    "fall_ns": edge_ns,
                    **breakable_params(
                        keep_head_ns=DEFAULT_BREAK_KEEP_HEAD_NS,
                        keep_tail_ns=DEFAULT_BREAK_KEEP_TAIL_NS,
                        break_kind="readout",
                        break_stage="measure",
                    ),
                },
                _ro_carrier(cfg),
            )
        return pulses, duration, events

    if gate == "reset":
        qs = qubits or [0]
        t0 = start_ns
        t1 = t0 + float(cfg["reset_measure_duration"])
        t2 = t1 + float(cfg["reset_deplete_duration"])
        t3 = t2 + float(cfg["reset_latency_duration"]) + max(0.0, float(reset_feedback_offset_ns))
        t4 = t3 + (float(cfg["reset_pi_duration"]) if bool(cfg["reset_apply_feedback"]) else 0.0)
        edge_ns = float(cfg["readout_edge_ns"])
        for q in qs:
            add(
                f"RO_{q}",
                t0,
                t1,
                float(cfg["reset_measure_amp"]),
                "readout",
                {
                    "stage": "reset_measure",
                    "rise_ns": edge_ns,
                    "fall_ns": edge_ns,
                    **breakable_params(
                        keep_head_ns=DEFAULT_BREAK_KEEP_HEAD_NS,
                        keep_tail_ns=DEFAULT_BREAK_KEEP_TAIL_NS,
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
                    "rise_ns": edge_ns,
                    "fall_ns": edge_ns,
                    **breakable_params(
                        keep_head_ns=DEFAULT_RESET_DEPL_BREAK_KEEP_HEAD_NS,
                        keep_tail_ns=DEFAULT_RESET_DEPL_BREAK_KEEP_TAIL_NS,
                        break_kind="reset",
                        break_stage="reset_deplete",
                    ),
                },
                _ro_carrier(cfg),
            )
            if bool(cfg["reset_apply_feedback"]) and t4 > t3:
                add(
                    f"XY_{q}",
                    t3,
                    t4,
                    float(cfg["reset_pi_amp"]),
                    "gaussian",
                    {"stage": "reset_conditional_pi", "sigma": max(float(cfg["reset_pi_duration"]) / 6.0, 1e-9), "conditional": True, "cond_on": int(cfg["reset_cond_on"])},
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
