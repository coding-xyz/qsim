from __future__ import annotations

import json
from pathlib import Path

from qsim.workflow import WorkflowFeatureFlags, WorkflowInput, WorkflowOutputOptions, WorkflowRunOptions, WorkflowTask, run_task


def _run_task_from_kwargs(*, qasm_text: str, backend_path: str, out_dir: str, **kwargs) -> dict:
    input_kwargs = {"qasm_text": qasm_text, "backend_path": backend_path}
    run_kwargs = {}
    feature_kwargs = {}
    output_kwargs = {"out_dir": out_dir}
    for key, value in kwargs.items():
        if key in {"hardware", "schedule_policy", "reset_feedback_policy", "noise", "param_bindings"}:
            input_kwargs[key] = value
            continue
        if key in {
            "engine",
            "solver_mode",
            "compare_engines",
            "allow_mock_fallback",
            "julia_bin",
            "julia_depot_path",
            "julia_timeout_s",
            "mcwf_ntraj",
            "prior_backend",
            "decoder",
            "decoder_options",
            "qec_engine",
        }:
            run_kwargs[key] = value
            continue
        if key in {
            "pauli_plus_analysis",
            "pauli_plus_code_distances",
            "pauli_plus_shots",
            "decoder_eval",
            "eval_decoders",
            "eval_seeds",
            "eval_option_grid",
            "eval_parallelism",
            "eval_retries",
            "eval_resume",
        }:
            feature_kwargs[key] = value
            continue
        if key in {
            "out_dir",
            "persist_artifacts",
            "artifact_mode",
            "export_dxf",
            "export_plots",
            "session_dir",
            "session_auto_commit",
            "session_commit_kinds",
        }:
            output_kwargs[key] = value
            continue
        raise KeyError(f"unsupported workflow kwarg in test helper: {key}")
    run_kwargs.setdefault("decoder", "mwpm")

    return run_task(
        WorkflowTask(
            input=WorkflowInput(**input_kwargs),
            run=WorkflowRunOptions(**run_kwargs),
            features=WorkflowFeatureFlags(**feature_kwargs),
            output=WorkflowOutputOptions(**output_kwargs),
        )
    )


def test_workflow_session_auto_commit_writes_report_and_manifest(tmp_path: Path):
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = tmp_path / "run_out"
    session_dir = tmp_path / "session_store"

    result = _run_task_from_kwargs(
        qasm_text=qasm_text,
        backend_path="examples/backend.yaml",
        out_dir=str(out_dir),
        persist_artifacts=True,
        export_dxf=False,
        export_plots=False,
        session_dir=str(session_dir),
        session_auto_commit=True,
        session_commit_kinds=["settings", "timings", "logical_error"],
    )

    actual_out = Path(result["runtime"]["out_dir"])
    assert result["optional"]["session_commit_report"] is not None
    report = result["optional"]["session_commit_report"]
    assert report["run_out_dir"] == str(actual_out)
    assert len(report["commits"]) >= 3

    report_path = actual_out / "session_commit_report.json"
    assert report_path.exists()
    report_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(report_disk["commits"]) >= 3

    session_manifest = json.loads((session_dir / "session_manifest.json").read_text(encoding="utf-8"))
    assert len(session_manifest["revisions"]) >= 3

    run_manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))
    assert "session_commit_report" in run_manifest["outputs"]
