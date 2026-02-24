from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from qsim.common.schemas import (
    BackendConfig,
    Carrier,
    ChannelSpec,
    CircuitIR,
    ExecutableModel,
    PulseIR,
    PulseSpec,
)


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
        hw = hw or {}
        freq = float(hw.get("xy_freq_hz", 5.0e9))
        readout_freq = float(hw.get("ro_freq_hz", 6.5e9))

        ch_map: dict[str, list[PulseSpec]] = defaultdict(list)
        cursor = 0.0
        gate_dur = float(hw.get("gate_duration", 20.0))
        measure_dur = float(hw.get("measure_duration", 200.0))
        edge_ns = float(hw.get("rect_edge_ns", 2.0))
        readout_edge_ns = float(hw.get("readout_edge_ns", edge_ns))
        tc_pair_to_idx: dict[tuple[int, int], int] = {}
        reset_events: list[dict] = []
        reset_measure_dur = float(hw.get("reset_measure_duration", max(measure_dur, 400.0)))
        reset_deplete_dur = float(hw.get("reset_deplete_duration", 150.0))
        reset_latency_dur = float(hw.get("reset_latency_duration", 120.0))
        reset_pi_dur = float(hw.get("reset_pi_duration", gate_dur))
        reset_measure_amp = float(hw.get("reset_measure_amp", 0.8))
        reset_deplete_amp = float(hw.get("reset_deplete_amp", 0.15))
        reset_pi_amp = float(hw.get("reset_pi_amp", 1.0))
        reset_cond_on = int(hw.get("reset_cond_on", 1))
        reset_apply_feedback = bool(hw.get("reset_apply_feedback", True))

        gates = list(schedule_or_circuit.gates)
        n_gates = len(gates)
        for i, gate in enumerate(gates):
            if gate.name in {"x", "sx", "h"}:
                for q in gate.qubits:
                    ch_map[f"XY_{q}"].append(
                        PulseSpec(t0=cursor, t1=cursor + gate_dur, amp=1.0, shape="gaussian", params={"sigma": gate_dur / 6.0}, carrier=Carrier(freq=freq, phase=0.0))
                    )
                cursor += gate_dur
            elif gate.name in {"rz", "z"}:
                for q in gate.qubits:
                    ch_map[f"Z_{q}"].append(
                        PulseSpec(
                            t0=cursor,
                            t1=cursor + gate_dur,
                            amp=0.2,
                            shape="rect",
                            params={"rise_ns": edge_ns, "fall_ns": edge_ns},
                        )
                    )
                cursor += gate_dur
            elif gate.name == "cz":
                qs = gate.qubits or [0, 1]
                q0, q1 = int(min(qs)), int(max(qs))
                pair = (q0, q1)
                if pair not in tc_pair_to_idx:
                    tc_pair_to_idx[pair] = len(tc_pair_to_idx)
                tc_idx = tc_pair_to_idx[pair]
                ch_map[f"TC_{tc_idx}"].append(
                    PulseSpec(
                        t0=cursor,
                        t1=cursor + 2 * gate_dur,
                        amp=0.75,
                        shape="rect",
                        params={"rise_ns": edge_ns, "fall_ns": edge_ns},
                    )
                )
                cursor += 2 * gate_dur
            elif gate.name == "cx":
                qs = gate.qubits or [0, 1]
                q0, q1 = int(min(qs)), int(max(qs))
                pair = (q0, q1)
                if pair not in tc_pair_to_idx:
                    tc_pair_to_idx[pair] = len(tc_pair_to_idx)
                tc_idx = tc_pair_to_idx[pair]
                ch_map[f"XY_{qs[0]}"].append(
                    PulseSpec(t0=cursor, t1=cursor + 2 * gate_dur, amp=1.2, shape="drag", params={"beta": 0.35, "sigma": gate_dur / 4.0}, carrier=Carrier(freq=freq, phase=0.0))
                )
                ch_map[f"XY_{qs[-1]}"].append(
                    PulseSpec(t0=cursor, t1=cursor + 2 * gate_dur, amp=1.2, shape="drag", params={"beta": 0.35, "sigma": gate_dur / 4.0}, carrier=Carrier(freq=freq, phase=0.2))
                )
                ch_map[f"TC_{tc_idx}"].append(
                    PulseSpec(
                        t0=cursor,
                        t1=cursor + 2 * gate_dur,
                        amp=0.75,
                        shape="rect",
                        params={"rise_ns": edge_ns, "fall_ns": edge_ns},
                    )
                )
                cursor += 2 * gate_dur
            elif gate.name == "measure":
                for q in gate.qubits:
                    ch_map[f"RO_{q}"].append(
                        PulseSpec(
                            t0=cursor,
                            t1=cursor + measure_dur,
                            amp=0.8,
                            shape="readout",
                            params={"rise_ns": readout_edge_ns, "fall_ns": readout_edge_ns},
                            carrier=Carrier(freq=readout_freq, phase=0.0),
                        )
                    )
                next_is_measure = (i + 1 < n_gates) and (gates[i + 1].name == "measure")
                if not next_is_measure:
                    cursor += measure_dur
            elif gate.name == "reset":
                qs = gate.qubits or [0]
                t0 = cursor
                t1 = t0 + reset_measure_dur
                t2 = t1 + reset_deplete_dur
                t3 = t2 + reset_latency_dur
                t4 = t3 + (reset_pi_dur if reset_apply_feedback else 0.0)
                for q in qs:
                    ch_map[f"RO_{q}"].append(
                        PulseSpec(
                            t0=t0,
                            t1=t1,
                            amp=reset_measure_amp,
                            shape="readout",
                            params={"stage": "reset_measure", "rise_ns": readout_edge_ns, "fall_ns": readout_edge_ns},
                            carrier=Carrier(freq=readout_freq, phase=0.0),
                        )
                    )
                    ch_map[f"RO_{q}"].append(
                        PulseSpec(
                            t0=t1,
                            t1=t2,
                            amp=reset_deplete_amp,
                            shape="rect",
                            params={"stage": "reset_deplete", "rise_ns": readout_edge_ns, "fall_ns": readout_edge_ns},
                            carrier=Carrier(freq=readout_freq, phase=0.0),
                        )
                    )
                    if reset_apply_feedback and t4 > t3:
                        ch_map[f"XY_{q}"].append(
                            PulseSpec(
                                t0=t3,
                                t1=t4,
                                amp=reset_pi_amp,
                                shape="gaussian",
                                params={
                                    "stage": "reset_conditional_pi",
                                    "sigma": max(reset_pi_dur / 6.0, 1e-9),
                                    "conditional": True,
                                    "cond_on": reset_cond_on,
                                },
                                carrier=Carrier(freq=freq, phase=0.0),
                            )
                        )
                    reset_events.append(
                        {
                            "qubit": int(q),
                            "t0": float(t0),
                            "t_meas_end": float(t1),
                            "t_deplete_end": float(t2),
                            "t_feedback_end": float(t3),
                            "t1": float(t4),
                            "conditional_on": reset_cond_on,
                            "apply_feedback": bool(reset_apply_feedback),
                        }
                    )
                next_is_reset = (i + 1 < n_gates) and (gates[i + 1].name == "reset")
                if not next_is_reset:
                    cursor = t4
            elif gate.name == "barrier":
                continue
            else:
                cursor += gate_dur

        channels = [ChannelSpec(name=k, pulses=v) for k, v in sorted(ch_map.items())]
        pulse_ir = PulseIR(t_end=cursor, channels=channels)

        executable = ExecutableModel(
            level=cfg.level,
            solver=cfg.solver,
            h_terms=[{"type": "drive", "source": "pulse_ir", "channels": [c.name for c in channels]}],
            noise_terms=[{"type": cfg.noise}],
            metadata={
                "num_qubits": schedule_or_circuit.num_qubits,
                "truncation": dict(cfg.truncation),
                "reset_events": reset_events,
            },
        )
        return pulse_ir, executable
