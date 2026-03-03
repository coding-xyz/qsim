"""Lowering from normalized circuits into pulse-level instructions."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from qsim.common.schemas import (
    BackendConfig,
    ChannelSpec,
    CircuitIR,
    ExecutableModel,
    PulseIR,
)
from qsim.pulse.catalog import instantiate_operation_recipe, resolve_lowering_hardware
from qsim.backend.scheduling import build_gate_schedule


class ILowering(Protocol):
    """Protocol for converting circuit/schedule into pulse-level model."""

    def lower(self, schedule_or_circuit: CircuitIR, hw: dict | None, cfg: BackendConfig) -> tuple[PulseIR, ExecutableModel]:
        ...


class DefaultLowering:
    """Default gate-to-pulse lowering with simple serial scheduling."""

    def lower(self, schedule_or_circuit: CircuitIR, hw: dict | None, cfg: BackendConfig) -> tuple[PulseIR, ExecutableModel]:
        """Lower ``CircuitIR`` to ``PulseIR`` and ``ExecutableModel``.

        Reset lowering uses a measurement-driven sequence:
        1) reset readout pulse (`RO_*`, stage=`reset_measure`)
        2) resonator depletion pulse (`RO_*`, stage=`reset_deplete`)
        3) feedback latency window
        4) optional conditional pi pulse (`XY_*`, stage=`reset_conditional_pi`)

        Notes:
        - The feedback pulse is a conditional pi, not a pi/2 pulse.
        - Consecutive reset instructions are aligned in parallel by default.
        - `barrier` is treated as a no-op (no pulse, no time advance).

        Hardware knobs:
        - `reset_measure_duration`, `reset_deplete_duration`, `reset_latency_duration`
        - `reset_pi_duration`, `reset_measure_amp`, `reset_deplete_amp`, `reset_pi_amp`
        - `reset_cond_on`, `reset_apply_feedback`
        """
        resolved_hw = resolve_lowering_hardware(hw)
        ch_map = defaultdict(list)
        reset_events: list[dict] = []
        scheduled_gates = build_gate_schedule(schedule_or_circuit, resolved_hw)
        schedule_debug: list[dict] = []
        t_end = 0.0
        for item in scheduled_gates:
            gate = item["gate"]
            pulses, duration, events = instantiate_operation_recipe(
                gate.name,
                gate.qubits,
                start_ns=float(item["start_ns"]),
                hw=resolved_hw,
                tc_index=item["tc_index"],
                reset_feedback_offset_ns=float(item.get("reset_feedback_offset_ns", 0.0)),
            )
            for channel, pulse in pulses:
                ch_map[channel].append(pulse)
            reset_events.extend(events)
            t_end = max(t_end, float(item["start_ns"]) + float(duration))
            schedule_debug.append(
                {
                    "gate_index": int(item["index"]),
                    "gate_name": str(gate.name),
                    "qubits": [int(q) for q in gate.qubits],
                    "family": str(item["family"]),
                    "layer_id": int(item.get("layer_id", 0)),
                    "start_ns": float(item["start_ns"]),
                    "end_ns": float(item["end_ns"]),
                    "duration_ns": float(duration),
                    "tc_index": None if item["tc_index"] is None else int(item["tc_index"]),
                    "blocked_by_resources": list(item.get("blocked_by_resources", [])),
                    "reset_feedback_mode": item.get("reset_feedback_mode"),
                    "reset_feedback_offset_ns": float(item.get("reset_feedback_offset_ns", 0.0)),
                }
            )

        channels = [ChannelSpec(name=k, pulses=v) for k, v in sorted(ch_map.items())]
        pulse_ir = PulseIR(t_end=t_end, channels=channels)

        executable = ExecutableModel(
            level=cfg.level,
            solver=cfg.solver,
            h_terms=[{"type": "drive", "source": "pulse_ir", "channels": [c.name for c in channels]}],
            noise_terms=[{"type": cfg.noise}],
            metadata={
                "num_qubits": schedule_or_circuit.num_qubits,
                "truncation": dict(cfg.truncation),
                "reset_events": reset_events,
                "schedule_policy": str(resolved_hw["schedule_policy"]),
                "reset_feedback_policy": str(resolved_hw["reset_feedback_policy"]),
                "schedule_debug": schedule_debug,
            },
        )
        return pulse_ir, executable
