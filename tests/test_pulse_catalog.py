from __future__ import annotations

import math

import pytest

from qsim.backend.lowering import DefaultLowering
from qsim.common.schemas import BackendConfig, CircuitGate, CircuitIR
from qsim.pulse.catalog import build_gate_mapping_catalog, instantiate_operation_recipe


def test_build_gate_mapping_catalog_exposes_reset_stages_and_barrier():
    payload = build_gate_mapping_catalog()
    ops = {item["op_name"]: item for item in payload["operations"]}

    assert payload["schema"] == "qsim.pulse-gate-map.v1"
    assert ops["x"]["shared_recipe_group"] == "single_qubit_xy_configurable"
    assert ops["rx"]["shared_recipe_group"] == "single_qubit_xy_configurable"
    assert ops["ry"]["shared_recipe_group"] == "single_qubit_xy_configurable"
    assert ops["h"]["shared_recipe_group"] == "single_qubit_hadamard_virtual_z"
    assert ops["h"]["duration_ns"] == 20.0
    assert ops["z"]["shared_recipe_group"] == "single_qubit_virtual_z"
    assert ops["rz"]["duration_ns"] == 0.0
    assert [step["stage"] for step in ops["reset"]["steps"] if "stage" in step] == [
        "reset_measure",
        "reset_deplete",
        "feedback_latency",
        "reset_conditional_pi",
    ]
    assert ops["barrier"]["duration_ns"] == 0.0
    assert ops["barrier"]["steps"] == []


def test_instantiate_operation_recipe_reset_matches_documented_steps():
    pulses, duration, events = instantiate_operation_recipe("reset", [2], start_ns=50.0)

    assert duration == 690.0
    assert [channel for channel, _pulse in pulses] == ["RO_2", "RO_2", "XY_2"]
    assert [pulse.params.get("stage") for _channel, pulse in pulses] == [
        "reset_measure",
        "reset_deplete",
        "reset_conditional_pi",
    ]
    assert events[0]["qubit"] == 2
    assert events[0]["t0"] == 50.0
    assert events[0]["t1"] == 740.0
    assert pulses[0][1].params["breakable"] is True
    assert pulses[0][1].params["break_stage"] == "reset_measure"
    assert pulses[1][1].params["breakable"] is True
    assert pulses[1][1].params["break_stage"] == "reset_deplete"
    assert "breakable" not in pulses[2][1].params


def test_measure_recipe_marks_readout_as_breakable():
    pulses, duration, _events = instantiate_operation_recipe("measure", [1], start_ns=0.0)

    assert duration == 200.0
    assert pulses[0][0] == "RO_1"
    assert pulses[0][1].params["breakable"] is True
    assert pulses[0][1].params["break_kind"] == "readout"


def test_parametric_rx_and_ry_recipes_encode_rotation_angle_and_phase():
    rx_pulses, rx_duration, _events = instantiate_operation_recipe("rx", [0], gate_params=[math.pi / 2.0], start_ns=0.0)
    ry_pulses, ry_duration, _events = instantiate_operation_recipe("ry", [0], gate_params=[-math.pi / 2.0], start_ns=0.0)
    x_pulses, _x_duration, _events = instantiate_operation_recipe("x", [0], start_ns=0.0)

    assert rx_duration == 20.0
    assert ry_duration == 20.0
    assert rx_pulses[0][1].params["rotation_axis"] == "x"
    assert ry_pulses[0][1].params["rotation_axis"] == "y"
    assert rx_pulses[0][1].params["rotation_rad"] == pytest.approx(math.pi / 2.0)
    assert ry_pulses[0][1].params["rotation_rad"] == pytest.approx(-math.pi / 2.0)
    assert rx_pulses[0][1].carrier is not None
    assert ry_pulses[0][1].carrier is not None
    assert rx_pulses[0][1].carrier.phase == pytest.approx(0.0)
    assert ry_pulses[0][1].carrier.phase == pytest.approx(math.pi / 2.0)
    assert abs(x_pulses[0][1].amp) == pytest.approx(2.0 * abs(rx_pulses[0][1].amp), rel=1e-6)


def test_single_qubit_shape_config_supports_rect_and_drag():
    rect_pulses, rect_duration, _events = instantiate_operation_recipe(
        "x",
        [0],
        start_ns=0.0,
        hw={"single_qubit_shape": "rect", "single_qubit_rect_edge_ns": 1.5},
    )
    drag_pulses, drag_duration, _events = instantiate_operation_recipe(
        "ry",
        [0],
        gate_params=[math.pi / 2.0],
        start_ns=0.0,
        hw={
            "single_qubit_shape": "drag",
            "single_qubit_drag_beta": 0.42,
            "single_qubit_sigma_fraction": 0.2,
        },
    )

    assert rect_duration == 20.0
    assert rect_pulses[0][1].shape == "rect"
    assert rect_pulses[0][1].params["rise_s"] == pytest.approx(1.5e-9)
    assert rect_pulses[0][1].params["fall_s"] == pytest.approx(1.5e-9)
    assert drag_duration == 20.0
    assert drag_pulses[0][1].shape == "drag"
    assert drag_pulses[0][1].params["beta"] == pytest.approx(0.42)
    assert drag_pulses[0][1].params["sigma_s"] == pytest.approx(4.0e-9)
    assert drag_pulses[0][1].params["rotation_axis"] == "y"


def test_h_recipe_emits_only_y_half_pi_pulse_and_virtual_z_is_handled_by_lowering():
    pulses, duration, _events = instantiate_operation_recipe("h", [0], start_ns=0.0)

    assert duration == 20.0
    assert [channel for channel, _pulse in pulses] == ["XY_0"]
    assert pulses[0][1].params["rotation_axis"] == "y"
    assert pulses[0][1].params["rotation_rad"] == pytest.approx(math.pi / 2.0)
    assert pulses[0][1].carrier is not None
    assert pulses[0][1].carrier.phase == pytest.approx(math.pi / 2.0)
    assert pulses[0][1].t0_ns == pytest.approx(0.0)
    assert pulses[0][1].t1_ns == pytest.approx(20.0)


def test_virtual_z_recipe_emits_no_pulse_and_zero_duration():
    z_pulses, z_duration, _events = instantiate_operation_recipe("z", [0], start_ns=0.0)
    rz_pulses, rz_duration, _events = instantiate_operation_recipe("rz", [0], gate_params=[math.pi / 3.0], start_ns=0.0)

    assert z_pulses == []
    assert rz_pulses == []
    assert z_duration == 0.0
    assert rz_duration == 0.0


def test_lowering_and_catalog_instantiation_stay_in_sync_for_mixed_circuit():
    circuit = CircuitIR(
        num_qubits=2,
        gates=[
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="h", qubits=[1]),
            CircuitGate(name="cz", qubits=[0, 1]),
            CircuitGate(name="measure", qubits=[0]),
            CircuitGate(name="measure", qubits=[1]),
            CircuitGate(name="reset", qubits=[0]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={}, cfg=BackendConfig())
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert pulse_ir.t_end_ns == 970.0
    assert len(executable.metadata["reset_events"]) == 1
    assert by_channel["XY_0"][0].shape == "gaussian"
    assert by_channel["XY_1"][0].params["rotation_axis"] == "y"
    assert by_channel["XY_1"][0].carrier.phase == pytest.approx(math.pi / 2.0)
    assert "Z_1" not in by_channel
    assert by_channel["TC_0"][0].duration_ns == 40.0
    assert [pulse.shape for pulse in by_channel["RO_0"]] == ["readout", "readout", "rect"]
    assert by_channel["XY_0"][-1].params["stage"] == "reset_conditional_pi"


def test_virtual_z_lowering_updates_following_xy_frame_without_adding_duration():
    circuit = CircuitIR(
        num_qubits=1,
        gates=[
            CircuitGate(name="h", qubits=[0]),
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="rz", qubits=[0], params=[math.pi / 2.0]),
            CircuitGate(name="sx", qubits=[0]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={}, cfg=BackendConfig())
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}
    xy_pulses = by_channel["XY_0"]

    assert pulse_ir.t_end_ns == 60.0
    assert len(xy_pulses) == 3
    assert xy_pulses[0].t0_ns == pytest.approx(0.0)
    assert xy_pulses[0].carrier.phase == pytest.approx(math.pi / 2.0)
    assert xy_pulses[1].t0_ns == pytest.approx(20.0)
    assert xy_pulses[1].carrier.phase == pytest.approx(math.pi)
    assert xy_pulses[2].t0_ns == pytest.approx(40.0)
    assert xy_pulses[2].carrier.phase == pytest.approx(1.5 * math.pi)
    debug = executable.metadata["schedule_debug"]
    assert debug[0]["virtual_z_phase_after_rad"] == {0: pytest.approx(math.pi)}
    assert debug[2]["virtual_z_phase_after_rad"] == {0: pytest.approx(1.5 * math.pi)}


def test_parallel_policy_allows_disjoint_cz_to_overlap():
    circuit = CircuitIR(
        num_qubits=4,
        gates=[
            CircuitGate(name="cz", qubits=[0, 1]),
            CircuitGate(name="cz", qubits=[2, 3]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={"schedule_policy": "parallel"}, cfg=BackendConfig())
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert executable.metadata["schedule_policy"] == "parallel"
    assert pulse_ir.t_end_ns == 40.0
    assert by_channel["TC_0"][0].t0_ns == 0.0
    assert by_channel["TC_1"][0].t0_ns == 0.0
    assert executable.metadata["schedule_debug"][0]["layer_id"] == 0
    assert executable.metadata["schedule_debug"][1]["layer_id"] == 0
    assert executable.metadata["schedule_debug"][0]["blocked_by_resources"] == []
    assert executable.metadata["schedule_debug"][1]["blocked_by_resources"] == []


def test_hybrid_policy_parallelizes_consecutive_same_family_only():
    circuit = CircuitIR(
        num_qubits=4,
        gates=[
            CircuitGate(name="cz", qubits=[0, 1]),
            CircuitGate(name="cz", qubits=[2, 3]),
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="x", qubits=[2]),
            CircuitGate(name="cz", qubits=[0, 1]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={"schedule_policy": "hybrid"}, cfg=BackendConfig())
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert executable.metadata["schedule_policy"] == "hybrid"
    assert pulse_ir.t_end_ns == 100.0
    assert by_channel["TC_0"][0].t0_ns == 0.0
    assert by_channel["TC_1"][0].t0_ns == 0.0
    assert by_channel["XY_0"][0].t0_ns == 40.0
    assert by_channel["XY_2"][0].t0_ns == 40.0
    assert by_channel["TC_0"][1].t0_ns == 60.0
    debug = executable.metadata["schedule_debug"]
    assert [item["layer_id"] for item in debug] == [0, 0, 1, 1, 2]


def test_serial_global_reset_feedback_keeps_measurement_parallel_but_staggers_feedback():
    circuit = CircuitIR(
        num_qubits=2,
        gates=[
            CircuitGate(name="reset", qubits=[0]),
            CircuitGate(name="reset", qubits=[1]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(
        circuit,
        hw={"schedule_policy": "serial", "reset_feedback_policy": "serial_global"},
        cfg=BackendConfig(),
    )
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert executable.metadata["reset_feedback_policy"] == "serial_global"
    assert pulse_ir.t_end_ns == 710.0
    assert by_channel["RO_0"][0].t0_ns == 0.0
    assert by_channel["RO_1"][0].t0_ns == 0.0
    assert by_channel["XY_0"][0].t0_ns == 670.0
    assert by_channel["XY_1"][0].t0_ns == 690.0
    assert executable.metadata["reset_events"][0]["feedback_offset_ns"] == 0.0
    assert executable.metadata["reset_events"][1]["feedback_offset_ns"] == 20.0
    assert executable.metadata["schedule_debug"][0]["reset_feedback_mode"] == "serial_global"
    assert executable.metadata["schedule_debug"][1]["reset_feedback_mode"] == "serial_global"


def test_hybrid_reset_feedback_policy_serial_global_is_respected():
    circuit = CircuitIR(
        num_qubits=2,
        gates=[
            CircuitGate(name="reset", qubits=[0]),
            CircuitGate(name="reset", qubits=[1]),
            CircuitGate(name="x", qubits=[0]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(
        circuit,
        hw={"schedule_policy": "hybrid", "reset_feedback_policy": "serial_global"},
        cfg=BackendConfig(),
    )
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert executable.metadata["schedule_policy"] == "hybrid"
    assert pulse_ir.t_end_ns == 730.0
    assert by_channel["XY_0"][0].params["stage"] == "reset_conditional_pi"
    assert by_channel["XY_1"][0].params["stage"] == "reset_conditional_pi"
    assert by_channel["XY_0"][0].t0_ns == 670.0
    assert by_channel["XY_1"][0].t0_ns == 690.0
    assert by_channel["XY_0"][1].t0_ns == 710.0


def test_parallel_conflict_reason_is_recorded_for_shared_qubit_gate():
    circuit = CircuitIR(
        num_qubits=3,
        gates=[
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="x", qubits=[2]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={"schedule_policy": "parallel"}, cfg=BackendConfig())

    assert pulse_ir.t_end_ns == 40.0
    debug = executable.metadata["schedule_debug"]
    assert [item["start_ns"] for item in debug] == [0.0, 20.0, 0.0]
    assert debug[1]["blocked_by_resources"] == ["Q0"]
    assert debug[0]["layer_id"] == 0 and debug[1]["layer_id"] == 0 and debug[2]["layer_id"] == 0
