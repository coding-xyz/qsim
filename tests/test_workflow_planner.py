from __future__ import annotations

import pytest

from qsim.workflow import (
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowTask,
    build_execution_plan,
)


def _base_task() -> WorkflowTask:
    return WorkflowTask(
        input=WorkflowInput(
            qasm_text="OPENQASM 3; qubit[1] q; bit[1] c; measure q[0] -> c[0];",
            backend_path="examples/backend.yaml",
        ),
        run=WorkflowRunOptions(decoder="mwpm"),
        output=WorkflowOutputOptions(out_dir="runs/planner_test"),
    )


def test_default_plan_uses_full_template_qec_path():
    plan = build_execution_plan(_base_task())
    assert plan.template == "full"
    assert plan.targets == ["logical_error", "sensitivity_report"]
    assert plan.run_decode is True
    assert plan.run_analysis is True
    assert plan.run_decoder_eval is False
    assert plan.run_pauli_plus is False
    assert plan.run_cross_engine_compare is False


def test_simulate_template_skips_decode_and_analysis():
    task = _base_task()
    task.template = "simulate"
    plan = build_execution_plan(task)
    assert plan.targets == ["trace"]
    assert plan.run_decode is False
    assert plan.run_analysis is False


def test_trace_target_allows_missing_decoder():
    task = _base_task()
    task.template = "simulate"
    task.run.decoder = None
    plan = build_execution_plan(task)
    assert plan.run_decode is False


def test_qec_targets_require_decoder():
    task = _base_task()
    task.run.decoder = None
    with pytest.raises(ValueError, match="run.decoder"):
        build_execution_plan(task)


def test_cross_engine_target_requires_compare_engines():
    task = _base_task()
    task.targets = ["cross_engine_compare"]
    with pytest.raises(ValueError, match="run.compare_engines"):
        build_execution_plan(task)


def test_decoder_eval_target_enables_decoder_branch():
    task = _base_task()
    task.targets = ["decoder_eval_report"]
    plan = build_execution_plan(task)
    assert plan.run_decode is True
    assert plan.run_decoder_eval is True


def test_minimal_artifact_mode_normalizes_to_targeted():
    task = _base_task()
    task.template = "simulate"
    task.output = WorkflowOutputOptions(artifact_mode="minimal")
    plan = build_execution_plan(task)
    assert plan.artifact_mode == "targeted"
