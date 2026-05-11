from __future__ import annotations

from pathlib import Path

import pytest

from qsim.workflow import (
    DefaultAnalyserConfig,
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowTask,
    build_execution_plan,
    create_model,
)


def test_create_model_runs_trajectory_target_from_example_task1():
    base = Path("examples/noise_simulation_tests/task1").resolve()
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))
    model.run()

    assert "solver_0" in model.runs
    assert "analyser_0" in model.analyses
    assert model.analyses["analyser_0"].output.metrics is not None
    assert "population" in model.analyses["analyser_0"].output.metrics.metric_items


def test_cross_engine_target_without_compare_engines_fails():
    with pytest.raises(ValueError, match="run.compare_engines"):
        build_execution_plan(
            WorkflowTask(
                input=WorkflowInput(
                    qasm_text="OPENQASM 3; qubit[1] q; bit[1] c; measure q[0] -> c[0];",
                    backend_path="examples/backend.yaml",
                    analyser={"trajectory": {"save_times": "all"}},
                ),
                targets=["cross_engine_compare"],
                run=WorkflowRunOptions(compare_engines=None),
                output=WorkflowOutputOptions(out_dir="runs/pytest_targets_fail", persist_artifacts=False),
            )
        )
