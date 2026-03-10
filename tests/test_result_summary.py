from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

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


def test_summarize_workflow_result_builds_flat_row(tmp_path: Path):
    np.savez(
        tmp_path / "pulse_samples.npz",
        RO_0_t=np.array([0.0, 2.0]),
        RO_0_y=np.array([0.0, 1.0]),
    )
    trace = SimpleNamespace(
        engine="qutip",
        times=[0.0, 1.0],
        states=[[0.1], [0.8]],
        metadata={
            "num_qubits": 1,
            "state_encoding": "per_qubit_excited_probability",
            "solver": "me",
            "native_solver": True,
            "details": {"solver_impl": "mesolve"},
        },
    )
    result = {
        "trace": trace,
        "analysis": {"observables": {"values": {"final_p1": 0.8, "final_p0": 0.2, "mean_excited": 0.45}}},
        "solver_mode": "me",
        "out_dir": str(tmp_path),
    }

    row = summarize_workflow_result(
        result,
        task_tag="task1",
        task_title="Task 1",
        case_tag="baseline",
        engine="qutip",
        hardware={"gate_duration": 20.0},
        noise={"model": "markovian_lindblad"},
        note="demo",
    )

    assert row["task"] == "task1"
    assert row["task_title"] == "Task 1"
    assert row["case"] == "baseline"
    assert row["state_encoding"] == "per_qubit_excited_probability"
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
