from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from qsim.backend.lowering import DefaultLowering
from qsim.common.schemas import BackendConfig, ChannelSpec, CircuitGate, CircuitIR, PulseIR, PulseSpec
from qsim.pulse.visualize import auto_break_long_pulses, plot_pulses, pulse_ir_from_qasm


def _channel_labels(fig) -> list[str]:
    labels: list[str] = []
    for ax in fig.axes:
        for text in ax.texts:
            if text.get_gid() == "qsim_channel_label":
                labels.append(text.get_text())
    return labels


def test_plot_pulses_split_layout_keeps_xy_and_z_separate():
    pulse_ir = PulseIR(
        t_end=20.0,
        channels=[
            ChannelSpec(name="XY_0", pulses=[PulseSpec(t0=0.0, t1=10.0, amp=1.0, shape="rect")]),
            ChannelSpec(name="Z_0", pulses=[PulseSpec(t0=10.0, t1=20.0, amp=0.5, shape="rect")]),
            ChannelSpec(name="RO_0", pulses=[]),
        ],
    )

    fig = plot_pulses(pulse_ir, timing_layout=True, show_carrier=False, annotate_pulses=False)

    assert _channel_labels(fig) == ["XY_0", "Z_0", "RO_0"]


def test_plot_pulses_xyz_line_combine_merges_labels_and_preserves_metadata():
    pulse_ir = PulseIR(
        t_end=20.0,
        channels=[
            ChannelSpec(name="XY_0", pulses=[PulseSpec(t0=0.0, t1=10.0, amp=1.0, shape="rect")]),
            ChannelSpec(name="Z_0", pulses=[PulseSpec(t0=10.0, t1=20.0, amp=0.5, shape="rect")]),
            ChannelSpec(name="RO_0", pulses=[]),
        ],
    )

    fig = plot_pulses(
        pulse_ir,
        timing_layout=True,
        show_carrier=False,
        annotate_pulses=False,
        XYZ_line_combine=True,
    )

    assert _channel_labels(fig) == ["XYZ_0", "RO_0"]
    assert [item["channel"] for item in fig._qsim_pulse_metadata] == ["XY_0", "Z_0"]  # type: ignore[attr-defined]


def test_auto_break_long_pulses_requires_globally_idle_break_window():
    pulse_ir = PulseIR(
        t_end=2000.0,
        channels=[
            ChannelSpec(name="RO_0", pulses=[PulseSpec(t0=0.0, t1=2000.0, amp=1.0, shape="readout")]),
            ChannelSpec(name="XY_0", pulses=[PulseSpec(t0=900.0, t1=1100.0, amp=1.0, shape="gaussian")]),
        ],
    )

    breaks = auto_break_long_pulses(
        pulse_ir,
        min_pulse_ns=1000.0,
        keep_head_ns=120.0,
        keep_tail_ns=120.0,
    )

    assert breaks == []


def test_auto_break_long_pulses_requires_explicit_breakable_metadata():
    pulse_ir = PulseIR(
        t_end=2000.0,
        channels=[
            ChannelSpec(name="RO_0", pulses=[PulseSpec(t0=0.0, t1=2000.0, amp=1.0, shape="readout")]),
        ],
    )

    breaks = auto_break_long_pulses(
        pulse_ir,
        min_pulse_ns=1000.0,
        keep_head_ns=120.0,
        keep_tail_ns=120.0,
    )

    assert breaks == []


def test_auto_break_long_pulses_allows_break_when_other_channels_are_idle():
    pulse_ir = PulseIR(
        t_end=2000.0,
        channels=[
            ChannelSpec(
                name="RO_0",
                pulses=[
                    PulseSpec(
                        t0=0.0,
                        t1=2000.0,
                        amp=1.0,
                        shape="readout",
                        params={"breakable": True, "break_keep_head_ns": 120.0, "break_keep_tail_ns": 120.0},
                    )
                ],
            ),
            ChannelSpec(name="XY_0", pulses=[PulseSpec(t0=0.0, t1=50.0, amp=1.0, shape="gaussian")]),
        ],
    )

    breaks = auto_break_long_pulses(
        pulse_ir,
        min_pulse_ns=1000.0,
        keep_head_ns=120.0,
        keep_tail_ns=120.0,
    )

    assert breaks == [(120.0, 1880.0)]


def test_auto_break_long_pulses_uses_breakable_metadata_from_lowering():
    circuit = CircuitIR(num_qubits=1, gates=[CircuitGate(name="measure", qubits=[0])])
    pulse_ir, _exe = DefaultLowering().lower(circuit, hw={"measure_duration": 2000.0}, cfg=BackendConfig())

    breaks = auto_break_long_pulses(pulse_ir, min_pulse_ns=1000.0)

    assert breaks == [(60.0, 1940.0)]


def test_plot_pulses_auto_break_pulses_adds_breaks_from_semantic_hints():
    circuit = CircuitIR(num_qubits=1, gates=[CircuitGate(name="measure", qubits=[0])])
    pulse_ir, _exe = DefaultLowering().lower(circuit, hw={"measure_duration": 2000.0}, cfg=BackendConfig())

    fig = plot_pulses(
        pulse_ir,
        timing_layout=True,
        show_carrier=False,
        annotate_pulses=False,
        auto_break_pulses=True,
    )

    assert getattr(fig, "_qsim_pulse_metadata")[0]["shape"] == "readout"  # type: ignore[attr-defined]
    assert fig.axes[0].get_xlim()[1] < pulse_ir.t_end


def test_pulse_ir_from_qasm_accepts_reset_feedback_policy_explicitly():
    qasm_text = """
    OPENQASM 3;
    qubit[2] q;
    reset q[0];
    reset q[1];
    """

    pulse_ir = pulse_ir_from_qasm(
        qasm_text,
        backend_config=BackendConfig(),
        schedule_policy="serial",
        reset_feedback_policy="serial_global",
    )

    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}
    assert by_channel["XY_0"][0].t0 == 670.0
    assert by_channel["XY_1"][0].t0 == 690.0
