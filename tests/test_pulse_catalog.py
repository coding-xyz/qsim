from __future__ import annotations

from qsim.backend.lowering import DefaultLowering
from qsim.common.schemas import BackendConfig, CircuitGate, CircuitIR
from qsim.pulse.catalog import build_gate_mapping_catalog, instantiate_operation_recipe


def test_build_gate_mapping_catalog_exposes_reset_stages_and_barrier():
    payload = build_gate_mapping_catalog()
    ops = {item["op_name"]: item for item in payload["operations"]}

    assert payload["schema"] == "qsim.pulse-gate-map.v1"
    assert ops["x"]["shared_recipe_group"] == "single_qubit_xy_gaussian"
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


def test_lowering_and_catalog_instantiation_stay_in_sync_for_mixed_circuit():
    circuit = CircuitIR(
        num_qubits=2,
        gates=[
            CircuitGate(name="x", qubits=[0]),
            CircuitGate(name="cz", qubits=[0, 1]),
            CircuitGate(name="measure", qubits=[0]),
            CircuitGate(name="measure", qubits=[1]),
            CircuitGate(name="reset", qubits=[0]),
        ],
    )

    pulse_ir, executable = DefaultLowering().lower(circuit, hw={}, cfg=BackendConfig())
    by_channel = {ch.name: ch.pulses for ch in pulse_ir.channels}

    assert pulse_ir.t_end == 950.0
    assert len(executable.metadata["reset_events"]) == 1
    assert by_channel["XY_0"][0].shape == "gaussian"
    assert by_channel["TC_0"][0].t1 - by_channel["TC_0"][0].t0 == 40.0
    assert [pulse.shape for pulse in by_channel["RO_0"]] == ["readout", "readout", "rect"]
    assert by_channel["XY_0"][-1].params["stage"] == "reset_conditional_pi"


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
    assert pulse_ir.t_end == 40.0
    assert by_channel["TC_0"][0].t0 == 0.0
    assert by_channel["TC_1"][0].t0 == 0.0
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
    assert pulse_ir.t_end == 100.0
    assert by_channel["TC_0"][0].t0 == 0.0
    assert by_channel["TC_1"][0].t0 == 0.0
    assert by_channel["XY_0"][0].t0 == 40.0
    assert by_channel["XY_2"][0].t0 == 40.0
    assert by_channel["TC_0"][1].t0 == 60.0
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
    assert pulse_ir.t_end == 710.0
    assert by_channel["RO_0"][0].t0 == 0.0
    assert by_channel["RO_1"][0].t0 == 0.0
    assert by_channel["XY_0"][0].t0 == 670.0
    assert by_channel["XY_1"][0].t0 == 690.0
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
    assert pulse_ir.t_end == 730.0
    assert by_channel["XY_0"][0].params["stage"] == "reset_conditional_pi"
    assert by_channel["XY_1"][0].params["stage"] == "reset_conditional_pi"
    assert by_channel["XY_0"][0].t0 == 670.0
    assert by_channel["XY_1"][0].t0 == 690.0
    assert by_channel["XY_0"][1].t0 == 710.0


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

    assert pulse_ir.t_end == 40.0
    debug = executable.metadata["schedule_debug"]
    assert [item["start_ns"] for item in debug] == [0.0, 20.0, 0.0]
    assert debug[1]["blocked_by_resources"] == ["Q0"]
    assert debug[0]["layer_id"] == 0 and debug[1]["layer_id"] == 0 and debug[2]["layer_id"] == 0
