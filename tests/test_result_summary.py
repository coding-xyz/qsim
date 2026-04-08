from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import numpy as np

from qsim.common.schemas import ModelSpec, Trajectory
from qsim.ui.result_summary import attach_compare_status, collect_pulse_metrics, summarize_workflow_result
from qsim.workflow.model import AnalysisResult, ModelResults, SolverRunResult


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


def test_summarize_workflow_result_builds_flat_row(tmp_path: Path):
    np.savez(
        tmp_path / "pulse_samples.npz",
        RO_0_t=np.array([0.0, 2.0]),
        RO_0_y=np.array([0.0, 1.0]),
    )
    model = SimpleNamespace(
        results=ModelResults(
            solver_runs={
                "solver_0": SolverRunResult(
                    trajectory=Trajectory(
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
                    ),
                    analyses={
                        "analyser_0": AnalysisResult(
                            metrics={
                                "population": {"values": {"0": [0.9, 0.2], "1": [0.1, 0.8]}},
                                "mean_excited": {"values": [0.1, 0.45]},
                                "variance": {"values": [0.0, 0.02]},
                            },
                            report={},
                        )
                    },
                    runtime_metadata={"solver_mode": "me", "details": {"solver_impl": "mesolve", "native_solver": True}},
                    model_spec=ModelSpec(solver="me", dimension=2, t_end=1.0, dt=1.0, payload={"num_qubits": 1}),
                )
            }
        ),
        out_dir=str(tmp_path),
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
    assert row["state_encoding"] == "basis_population_single_qubit"
    assert row["final_p1_obs"] == 0.8
    assert row["solver_impl"] == "mesolve"
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
