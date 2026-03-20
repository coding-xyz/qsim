"""Gate scheduling policies for pulse lowering."""

from __future__ import annotations

from typing import Any

from qsim.common.schemas import CircuitGate, CircuitIR


def _gate_family(name: str) -> str:
    gate = str(name).lower()
    if gate in {"x", "sx", "h", "z", "rz"}:
        return "single_qubit"
    if gate in {"cz", "cx"}:
        return "two_qubit"
    if gate == "measure":
        return "measure"
    if gate == "reset":
        return "reset"
    if gate == "barrier":
        return "barrier"
    return "other"


def _gate_duration_ns(gate: CircuitGate, hw: dict[str, Any]) -> float:
    name = str(gate.name).lower()
    gate_dur = float(hw["gate_duration_ns"])
    if name in {"x", "sx", "h", "z", "rz"}:
        return gate_dur
    if name in {"cz", "cx"}:
        return 2.0 * gate_dur
    if name == "measure":
        return float(hw["measure_duration_ns"])
    if name == "reset":
        return (
            float(hw["reset_measure_duration_ns"])
            + float(hw["reset_deplete_duration_ns"])
            + float(hw["reset_latency_duration_ns"])
            + (float(hw["reset_pi_duration_ns"]) if bool(hw["reset_apply_feedback"]) else 0.0)
        )
    if name == "barrier":
        return 0.0
    return gate_dur


def _reset_prefix_duration_ns(hw: dict[str, Any]) -> float:
    return (
        float(hw["reset_measure_duration_ns"])
        + float(hw["reset_deplete_duration_ns"])
        + float(hw["reset_latency_duration_ns"])
    )


def _reset_feedback_duration_ns(hw: dict[str, Any]) -> float:
    return float(hw["reset_pi_duration_ns"]) if bool(hw["reset_apply_feedback"]) else 0.0


def _pair_key(qubits: list[int]) -> tuple[int, int]:
    qs = qubits or [0, 1]
    return int(min(qs)), int(max(qs))


def _gate_resources(gate: CircuitGate, *, tc_index: int | None = None) -> set[str]:
    name = str(gate.name).lower()
    qs = [int(q) for q in (gate.qubits or [])]
    resources = {f"Q{q}" for q in qs}
    if name in {"measure", "reset"}:
        resources.update(f"RO{q}" for q in qs)
    if name in {"cz", "cx"} and tc_index is not None:
        resources.add(f"TC{int(tc_index)}")
    return resources


def _segment_gates(gates: list[dict[str, Any]], policy: str) -> list[list[dict[str, Any]]]:
    if policy == "parallel":
        segments: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for item in gates:
            if item["family"] == "barrier":
                if current:
                    segments.append(current)
                    current = []
                segments.append([item])
                continue
            current.append(item)
        if current:
            segments.append(current)
        return segments

    segments = []
    current = []
    current_family: str | None = None
    for item in gates:
        family = item["family"]
        if family == "barrier":
            if current:
                segments.append(current)
                current = []
                current_family = None
            segments.append([item])
            continue
        if current and family != current_family:
            segments.append(current)
            current = []
        current.append(item)
        current_family = family
    if current:
        segments.append(current)
    return segments


def _schedule_reset_segment(
    segment: list[dict[str, Any]],
    *,
    segment_start: float,
    hw: dict[str, Any],
    layer_id: int,
) -> tuple[list[dict[str, Any]], float]:
    feedback_policy = str(hw.get("reset_feedback_policy", "parallel")).strip().lower() or "parallel"
    if feedback_policy not in {"parallel", "serial_global"}:
        raise ValueError(f"Unsupported reset_feedback_policy: {feedback_policy}")

    prefix = _reset_prefix_duration_ns(hw)
    feedback = _reset_feedback_duration_ns(hw)
    scheduled: list[dict[str, Any]] = []
    segment_end = segment_start
    for i, item in enumerate(segment):
        feedback_offset = (i * feedback) if (feedback_policy == "serial_global" and feedback > 0.0) else 0.0
        duration = prefix + feedback_offset + feedback
        start_ns = segment_start
        end_ns = start_ns + duration
        segment_end = max(segment_end, end_ns)
        scheduled.append(
            {
                **item,
                "start_ns": start_ns,
                "end_ns": end_ns,
                "duration_ns": duration,
                "reset_feedback_offset_ns": feedback_offset,
                "layer_id": layer_id,
                "blocked_by_resources": [],
                "reset_feedback_mode": feedback_policy,
            }
        )
    return scheduled, segment_end


def build_gate_schedule(schedule_or_circuit: CircuitIR, hw: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a scheduled gate list according to the selected policy."""
    policy = str(hw.get("schedule_policy", "serial")).strip().lower() or "serial"
    if policy not in {"serial", "parallel", "hybrid"}:
        raise ValueError(f"Unsupported schedule_policy: {policy}")

    raw_gates = list(schedule_or_circuit.gates)
    pair_to_idx: dict[tuple[int, int], int] = {}
    gates: list[dict[str, Any]] = []
    for idx, gate in enumerate(raw_gates):
        tc_index = None
        if str(gate.name).lower() in {"cz", "cx"}:
            pair = _pair_key(gate.qubits)
            if pair not in pair_to_idx:
                pair_to_idx[pair] = len(pair_to_idx)
            tc_index = pair_to_idx[pair]
        gates.append(
            {
                "index": idx,
                "gate": gate,
                "family": _gate_family(gate.name),
                "duration_ns": _gate_duration_ns(gate, hw),
                "tc_index": tc_index,
            }
        )

    if policy == "serial":
        scheduled: list[dict[str, Any]] = []
        cursor = 0.0
        n = len(gates)
        layer_id = 0
        i = 0
        while i < n:
            item = gates[i]
            family = item["family"]
            if family == "barrier":
                i += 1
                continue
            if family == "reset":
                group = [item]
                j = i + 1
                while j < n and gates[j]["family"] == "reset":
                    group.append(gates[j])
                    j += 1
                group_scheduled, group_end = _schedule_reset_segment(group, segment_start=cursor, hw=hw, layer_id=layer_id)
                scheduled.extend(group_scheduled)
                cursor = group_end
                layer_id += 1
                i = j
                continue
            duration = float(item["duration_ns"])
            scheduled.append(
                {
                    **item,
                    "start_ns": cursor,
                    "end_ns": cursor + duration,
                    "reset_feedback_offset_ns": 0.0,
                    "layer_id": layer_id,
                    "blocked_by_resources": [],
                    "reset_feedback_mode": None,
                }
            )
            if family == "measure":
                next_same = (i + 1 < n) and (gates[i + 1]["family"] == "measure")
                if not next_same:
                    cursor += duration
                    layer_id += 1
            else:
                cursor += duration
                layer_id += 1
            i += 1
        return scheduled

    scheduled = []
    segment_start = 0.0
    for layer_id, segment in enumerate(_segment_gates(gates, policy)):
        if not segment:
            continue
        if segment[0]["family"] == "barrier":
            continue
        if all(item["family"] == "reset" for item in segment):
            group_scheduled, group_end = _schedule_reset_segment(segment, segment_start=segment_start, hw=hw, layer_id=layer_id)
            scheduled.extend(group_scheduled)
            segment_start = group_end
            continue
        resource_busy_until: dict[str, float] = {}
        segment_end = segment_start
        for item in segment:
            resources = _gate_resources(item["gate"], tc_index=item["tc_index"])
            blocking = sorted([r for r in resources if resource_busy_until.get(r, segment_start) > segment_start])
            start_ns = max([segment_start, *[resource_busy_until.get(r, segment_start) for r in resources]])
            end_ns = start_ns + float(item["duration_ns"])
            for resource in resources:
                resource_busy_until[resource] = end_ns
            segment_end = max(segment_end, end_ns)
            scheduled.append(
                {
                    **item,
                    "start_ns": start_ns,
                    "end_ns": end_ns,
                    "reset_feedback_offset_ns": 0.0,
                    "layer_id": layer_id,
                    "blocked_by_resources": blocking,
                    "reset_feedback_mode": None,
                }
            )
        segment_start = segment_end
    return scheduled
