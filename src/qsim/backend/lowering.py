"""Lowering from normalized circuits into pulse-level instructions."""

from __future__ import annotations

from collections import defaultdict
import math
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

    @staticmethod
    def _apply_virtual_z_phase(pulses: list[tuple[str, object]], phase_by_qubit: dict[int, float]) -> None:
        for channel, pulse in pulses:
            if not channel.startswith("XY_") or pulse.carrier is None:
                continue
            try:
                qubit = int(channel.split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            pulse.carrier.phase = float(pulse.carrier.phase) + float(phase_by_qubit.get(qubit, 0.0))

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
        - `reset_measure_duration_ns`, `reset_deplete_duration_ns`, `reset_latency_duration_ns`
        - `reset_pi_duration_ns`, `reset_measure_amp`, `reset_deplete_amp`, `reset_pi_amp`
        - `reset_cond_on`, `reset_apply_feedback`
        """
        resolved_hw = resolve_lowering_hardware(hw)
        ch_map = defaultdict(list)
        reset_events: list[dict] = []
        virtual_z_phase_by_qubit: dict[int, float] = defaultdict(float)
        scheduled_gates = build_gate_schedule(schedule_or_circuit, resolved_hw)
        schedule_debug: list[dict] = []
        t_end = 0.0
        for item in scheduled_gates:
            gate = item["gate"]
            gate_name = str(gate.name).lower()
            gate_qubits = [int(q) for q in gate.qubits]
            phase_before = {q: float(virtual_z_phase_by_qubit[q]) for q in gate_qubits}
            pulses, duration, events = instantiate_operation_recipe(
                gate.name,
                gate.qubits,
                gate_params=gate.params,
                start_ns=float(item["start_ns"]),
                hw=resolved_hw,
                tc_index=item["tc_index"],
                reset_feedback_offset_ns=float(item.get("reset_feedback_offset_ns", 0.0)),
            )
            self._apply_virtual_z_phase(pulses, phase_before)
            for channel, pulse in pulses:
                ch_map[channel].append(pulse)
            reset_events.extend(events)
            if gate_name == "h":
                for q in gate_qubits:
                    virtual_z_phase_by_qubit[q] = float(virtual_z_phase_by_qubit[q]) + math.pi
            elif gate_name == "z":
                for q in gate_qubits:
                    virtual_z_phase_by_qubit[q] = float(virtual_z_phase_by_qubit[q]) + math.pi
            elif gate_name == "rz":
                phase_delta = float(list(gate.params or [0.0])[0])
                for q in gate_qubits:
                    virtual_z_phase_by_qubit[q] = float(virtual_z_phase_by_qubit[q]) + phase_delta
            phase_after = {q: float(virtual_z_phase_by_qubit[q]) for q in gate_qubits}
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
                    "virtual_z_phase_before_rad": phase_before,
                    "virtual_z_phase_after_rad": phase_after,
                }
            )

        if not scheduled_gates and int(getattr(schedule_or_circuit, "num_qubits", 0) or 0) == 0:
            measure_start_delay_ns = float(resolved_hw.get("measure_start_delay_ns", 0.0) or 0.0)
            pulses, duration, events = instantiate_operation_recipe(
                "measure",
                [0],
                start_ns=measure_start_delay_ns,
                hw=resolved_hw,
                tc_index=None,
                reset_feedback_offset_ns=0.0,
            )
            for channel, pulse in pulses:
                ch_map[channel].append(pulse)
            reset_events.extend(events)
            t_end = max(t_end, measure_start_delay_ns + float(duration))
            schedule_debug.append(
                {
                    "gate_index": -1,
                    "gate_name": "measure",
                    "qubits": [],
                    "family": "classical_readout",
                    "layer_id": 0,
                    "start_ns": measure_start_delay_ns,
                    "end_ns": measure_start_delay_ns + float(duration),
                    "duration_ns": float(duration),
                    "tc_index": None,
                    "blocked_by_resources": [],
                    "reset_feedback_mode": None,
                    "reset_feedback_offset_ns": 0.0,
                }
            )

        channels = [ChannelSpec(name=k, pulses=v) for k, v in sorted(ch_map.items())]
        pulse_ir = PulseIR(t_end_s=float(t_end) * 1e-9, channels=channels)

        executable = ExecutableModel(
            level=cfg.level,
            solver=cfg.solver,
            h_terms=[{"type": "drive", "source": "pulse_ir", "channels": [c.name for c in channels]}],
            noise_terms=[{"type": cfg.noise}],
            metadata={
                "num_qubits": schedule_or_circuit.num_qubits,
                "truncation": dict(cfg.truncation),
                "t_end_s": float(t_end) * 1e-9,
                "t_end_ns": float(t_end),
                "reset_events": reset_events,
                "schedule_policy": str(resolved_hw["schedule_policy"]),
                "reset_feedback_policy": str(resolved_hw["reset_feedback_policy"]),
                "schedule_debug": schedule_debug,
            },
        )
        return pulse_ir, executable
