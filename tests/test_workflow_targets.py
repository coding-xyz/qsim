from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from qsim.workflow import WorkflowInput, WorkflowOutputOptions, WorkflowRunOptions, WorkflowTask, run_task


def test_template_simulate_emits_trace_only_core_chain():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_targets_sim_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = run_task(
            WorkflowTask(
                input=WorkflowInput(
                    qasm_text=qasm_text,
                    backend_path="examples/backend.yaml",
                ),
                template="simulate",
                output=WorkflowOutputOptions(
                    out_dir=str(out_dir),
                    persist_artifacts=True,
                    artifact_mode="targeted",
                    export_dxf=False,
                    export_plots=False,
                ),
            )
        )
        actual_out = Path(result["runtime"]["out_dir"])
        assert (actual_out / "trace.h5").exists()
        assert not (actual_out / "logical_error.json").exists()
        assert not (actual_out / "sensitivity_report.json").exists()

        manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))
        assert "trace" in manifest["outputs"]
        assert "logical_error" not in manifest["outputs"]
        assert "sensitivity_report" not in manifest["outputs"]
        assert result["qec"]["logical_error"] is None
        assert result["analysis"]["sensitivity_report"] is None
        assert result["runtime"]["execution_plan"]["targets"] == ["trace"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_cross_engine_target_without_compare_engines_fails():
    with pytest.raises(ValueError, match="run.compare_engines"):
        run_task(
            WorkflowTask(
                input=WorkflowInput(
                    qasm_text="OPENQASM 3; qubit[1] q; bit[1] c; measure q[0] -> c[0];",
                    backend_path="examples/backend.yaml",
                ),
                targets=["cross_engine_compare"],
                run=WorkflowRunOptions(compare_engines=None),
                output=WorkflowOutputOptions(
                    out_dir=f"runs/pytest_targets_fail_{uuid.uuid4().hex[:8]}",
                    persist_artifacts=False,
                ),
            )
        )
