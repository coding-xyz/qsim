from __future__ import annotations

from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np

from qsim.common.schemas import Trajectory
from qsim.schemas.model import ModelRun, ModelSpec, RunArtifacts, RunIdentity
from qsim.schemas.results import AnalysisOutput, MetricSeries, MetricsOutput, RunProvenance, RunResult
from qsim.schemas.solver import FrameSpec, SolverSpec, TimeSpec
from qsim.schemas.system import SystemSpec
from qsim.ui.result_summary import attach_compare_status, collect_pulse_metrics, summarize_workflow_result


def test_collect_pulse_metrics_reads_npz(tmp_path: Path):
    np.savez(
        tmp_path / "pulse_samples.npz",
        XY_0_t=np.array([0.0, 1.0, 2.0]),
        XY_0_y=np.array([0.0, 1.0, 0.0]),
    )

    metrics = collect_pulse_metrics(tmp_path)

    assert metrics["XY_0_samples"] == 3.0
    assert metrics["XY_0_duration"] == 2.0
    assert metrics["XY_0_peak"] == 1.0
    assert metrics["XY_0_abs_area"] == 1.0


def test_summarize_workflow_result_uses_model_runs_and_model_level_analyses(tmp_path: Path):
    np.savez(
        tmp_path / "pulse_samples.npz",
        RO_0_t=np.array([0.0, 2.0]),
        RO_0_y=np.array([0.0, 1.0]),
    )

    run_id = "solver_0"
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[0.9 + 0.0j, 0.0j], [0.0j, 0.1 + 0.0j]],
                [[0.2 + 0.0j, 0.0j], [0.0j, 0.8 + 0.0j]],
            ],
        },
        metadata={
            "num_qubits": 1,
            "model_dimension": 2,
            "details": {"solver_impl": "mesolve", "native_solver": True},
        },
    )
    model = SimpleNamespace(
        runs={
            run_id: ModelRun(
                identity=RunIdentity(run_id=run_id, solver_id=run_id),
                runtime_task=None,
                artifacts=RunArtifacts(
                    model_spec=ModelSpec(
                        solver=SolverSpec(engine="qutip", mode="me"),
                        time=TimeSpec(dt_s=1.0, t_end_s=1.0),
                        frame=FrameSpec(),
                        system=SystemSpec(num_qubits=1, dimension=2),
                    )
                ),
                result=RunResult(
                    result_id=run_id,
                    trajectory=trajectory,
                    provenance=RunProvenance(solver_id=run_id),
                    runtime_metadata={"solver_mode": "me", "details": {"solver_impl": "mesolve", "native_solver": True}},
                ),
            )
        },
        analyses={
            "analyser_0": SimpleNamespace(
                analysis_id="analyser_0",
                analyser_id="analyser_0",
                input_run_ids=[run_id],
                output=AnalysisOutput(
                    metrics=MetricsOutput(
                        metric_items={
                            "population": MetricSeries(),
                            "mean_excited": MetricSeries(values=[0.1, 0.45]),
                            "variance": MetricSeries(values=[0.0, 0.02]),
                        }
                    )
                ),
            )
        },
        out_dir=str(tmp_path),
    )
    model.find_analysis_for_run = MethodType(
        lambda self, wanted_run_id: next(
            (analysis for analysis in self.analyses.values() if wanted_run_id in analysis.input_run_ids),
            None,
        ),
        model,
    )

    row = summarize_workflow_result(
        model,
        task_tag="task1",
        task_title="Task 1",
        case_tag="baseline",
        engine="qutip",
        device={"qubit_freqs_Hz": [5.0e9]},
        noise={"model": "markovian_lindblad"},
        note="demo",
    )

    assert row["task"] == "task1"
    assert row["task_title"] == "Task 1"
    assert row["case"] == "baseline"
    assert row["solver_impl"] == "mesolve"
    assert row["solver"] == "me"
    assert row["RO_0_duration"] == 2.0


def test_attach_compare_status_marks_semantic_review_for_mixed_encodings():
    import pandas as pd

    df = pd.DataFrame(
        [
            {"task": "task1", "case": "case1", "state_encoding": "per_qubit_excited_probability"},
            {"task": "task1", "case": "case1", "state_encoding": "basis_population_single_qubit"},
        ]
    )

    annotated = attach_compare_status(df)

    assert set(annotated["compare_status"]) == {"semantic-review-needed"}
