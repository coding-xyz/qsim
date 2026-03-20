import json
import shutil
import uuid
from pathlib import Path

import pytest

from qsim.common.schemas import Trace
from qsim.workflow import WorkflowFeatureFlags, WorkflowInput, WorkflowOutputOptions, WorkflowRunOptions, WorkflowTask, run_task
from qsim.workflow.engines import collect_runtime_dependencies


_INPUT_KEYS = {"device", "pulse", "schedule_policy", "reset_feedback_policy", "noise", "param_bindings"}
_RUN_KEYS = {
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
}
_FEATURE_KEYS = {
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
}
_OUTPUT_KEYS = {
    "out_dir",
    "persist_artifacts",
    "artifact_mode",
    "export_dxf",
    "export_plots",
    "session_dir",
    "session_auto_commit",
    "session_commit_kinds",
}


def _run_task_from_kwargs(*, qasm_text: str, backend_path: str, out_dir: str, **kwargs) -> dict:
    input_kwargs = {"qasm_text": qasm_text, "backend_path": backend_path}
    run_kwargs = {}
    feature_kwargs = {}
    output_kwargs = {"out_dir": out_dir}
    for key, value in kwargs.items():
        if key in _INPUT_KEYS:
            input_kwargs[key] = value
            continue
        if key in _RUN_KEYS:
            run_kwargs[key] = value
            continue
        if key in _FEATURE_KEYS:
            feature_kwargs[key] = value
            continue
        if key in _OUTPUT_KEYS:
            output_kwargs[key] = value
            continue
        raise KeyError(f"unsupported workflow kwarg in test helper: {key}")
    run_kwargs.setdefault("decoder", "mwpm")
    task = WorkflowTask(
        input=WorkflowInput(**input_kwargs),
        run=WorkflowRunOptions(**run_kwargs),
        features=WorkflowFeatureFlags(**feature_kwargs),
        output=WorkflowOutputOptions(**output_kwargs),
    )
    return run_task(task)


def test_workflow_accepts_solver_mode_and_param_bindings():
    qasm_text = """
OPENQASM 3;
qubit[1] q;
bit[1] c;
rz(theta) q[0];
measure q[0] -> c[0];
"""
    out_dir = Path("runs") / f"pytest_dyn_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            solver_mode="me",
            param_bindings={"theta": 0.3},
            persist_artifacts=True,
            export_dxf=False,
            export_plots=False,
            decoder="mock",
        )
        actual_out = Path(result["runtime"]["out_dir"])
        settings = json.loads((actual_out / "settings_report.json").read_text(encoding="utf-8"))
        circuit = json.loads((actual_out / "circuit.json").read_text(encoding="utf-8"))

        assert settings["workflow"]["solver"] == "me"
        assert settings["workflow"]["solver_mode_requested"] == "me"
        assert float(settings["workflow"]["param_bindings"]["theta"]) == 0.3
        assert circuit["gates"][0]["name"] == "rz"
        assert float(circuit["gates"][0]["params"][0]) == 0.3
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_emits_cross_engine_compare_artifact():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_dyn_cmp_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
            export_plots=False,
            compare_engines=["qutip"],
            allow_mock_fallback=False,
        )
        actual_out = Path(result["runtime"]["out_dir"])
        assert (actual_out / "cross_engine_compare.json").exists()
        report = json.loads((actual_out / "cross_engine_compare.json").read_text(encoding="utf-8"))
        settings = json.loads((actual_out / "settings_report.json").read_text(encoding="utf-8"))
        manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))

        assert report["schema_version"] == "1.0"
        assert report["status"] == "ok"
        assert isinstance(report["runs"], list) and len(report["runs"]) >= 1
        assert "cross_engine_compare" in manifest["outputs"]
        assert settings["workflow"]["allow_mock_fallback"] is False
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_cross_engine_pairwise_metrics_for_qoptics():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_dyn_cmp_pair_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        try:
            result = _run_task_from_kwargs(
                qasm_text=qasm_text,
                backend_path="examples/backend.yaml",
                out_dir=str(out_dir),
                persist_artifacts=True,
                export_dxf=False,
                export_plots=False,
                compare_engines=["qoptics"],
                allow_mock_fallback=False,
            )
        except Exception as exc:
            pytest.skip(f"julia runtime unavailable for compare test: {exc}")
        actual_out = Path(result["runtime"]["out_dir"])
        report = json.loads((actual_out / "cross_engine_compare.json").read_text(encoding="utf-8"))
        settings = json.loads((actual_out / "settings_report.json").read_text(encoding="utf-8"))

        assert report["status"] == "ok"
        assert len(report["runs"]) >= 2
        assert len(report["pairwise"]) >= 1
        pair = report["pairwise"][0]
        assert pair["comparable"] is True
        assert int(pair["samples_compared"]) > 0
        assert float(pair["mse"]) >= 0.0
        assert settings["workflow"]["allow_mock_fallback"] is False
        assert "qoptics" in settings["workflow"]["compare_engines_requested"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_emits_state_encoding_metadata_in_outputs():
    qasm_text = """
OPENQASM 3;
qubit[1] q;
bit[1] c;
x q[0];
measure q[0] -> c[0];
"""
    out_dir = Path("runs") / f"pytest_dyn_stateenc_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        try:
            result = _run_task_from_kwargs(
                qasm_text=qasm_text,
                backend_path="examples/backend.yaml",
                out_dir=str(out_dir),
                engine="qtoolbox",
                persist_artifacts=True,
                export_dxf=False,
                export_plots=False,
                decoder="mock",
            )
        except Exception as exc:
            pytest.skip(f"julia runtime unavailable for state-encoding test: {exc}")
        actual_out = Path(result["runtime"]["out_dir"])
        trace = result["core"]["trace"]
        observables = json.loads((actual_out / "observables.json").read_text(encoding="utf-8"))

        assert trace.metadata["state_encoding"] == "per_qubit_excited_probability"
        assert "final_q1_excited" not in observables["values"]
        assert float(observables["values"]["final_p1"]) >= 0.0
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_solver_mode_mcwf_persisted_in_outputs():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_dyn_mcwf_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            solver_mode="mcwf",
            compare_engines=["qutip"],
            persist_artifacts=True,
            export_dxf=False,
            export_plots=False,
        )
        actual_out = Path(result["runtime"]["out_dir"])
        settings = json.loads((actual_out / "settings_report.json").read_text(encoding="utf-8"))
        compare = json.loads((actual_out / "cross_engine_compare.json").read_text(encoding="utf-8"))
        assert settings["workflow"]["solver"] == "mcwf"
        assert settings["workflow"]["solver_mode_requested"] == "mcwf"
        assert compare["solver_mode"] == "mcwf"
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_collect_runtime_dependencies_extracts_julia_versions():
    trace = Trace(
        engine="julia-quantumtoolbox",
        metadata={
            "julia_version": "1.12.5",
            "julia_backend": "QuantumToolbox",
            "julia_backend_version": "0.31.0",
        },
    )

    deps = collect_runtime_dependencies(trace, "qtoolbox")

    assert deps["julia"] == "1.12.5"
    assert deps["julia_backend:QuantumToolbox"] == "0.31.0"
