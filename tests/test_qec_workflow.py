import json
import shutil
import uuid
from pathlib import Path

from qsim.common.schemas import DecoderInput, PriorModel, SyndromeFrame
from qsim.qec.eval import run_decoder_eval
from qsim.workflow import WorkflowFeatureFlags, WorkflowInput, WorkflowOutputOptions, WorkflowRunOptions, WorkflowTask, run_task


_INPUT_KEYS = {"hardware", "schedule_policy", "reset_feedback_policy", "noise", "param_bindings"}
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


def test_workflow_emits_qec_core_artifacts():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_qec_core_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
        )
        actual_out = Path(result["runtime"]["out_dir"])

        expected = [
            "syndrome_frame.json",
            "prior_model.json",
            "prior_report.json",
            "prior_samples.npz",
            "decoder_input.json",
            "decoder_output.json",
            "decoder_report.json",
            "logical_error.json",
            "sensitivity_report.json",
            "error_budget_v2.json",
            "figures/sensitivity_heatmap.png",
            "run_manifest.json",
        ]
        for name in expected:
            assert (actual_out / name).exists(), f"missing artifact: {name}"

        manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))
        for key in [
            "syndrome_frame",
            "prior_model",
            "prior_report",
            "prior_samples",
            "decoder_input",
            "decoder_output",
            "decoder_report",
            "logical_error",
            "sensitivity_report",
            "error_budget_v2",
            "sensitivity_heatmap",
        ]:
            assert key in manifest["outputs"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_prior_stim_fallback_and_bp_decoder():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_qec_m23_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
            prior_backend="stim",
            decoder="bp",
            decoder_options={"max_iter": 4, "damping": 0.4},
        )
        actual_out = Path(result["runtime"]["out_dir"])

        prior_report = json.loads((actual_out / "prior_report.json").read_text(encoding="utf-8"))
        decoder_output = json.loads((actual_out / "decoder_output.json").read_text(encoding="utf-8"))
        decoder_report = json.loads((actual_out / "decoder_report.json").read_text(encoding="utf-8"))
        assert (actual_out / "prior_samples.npz").exists()

        assert prior_report["builder"] == "stim_prior"
        assert prior_report["status"] in {"ok", "fallback"}
        assert decoder_output["decoder_name"] == "bp"
        assert decoder_report["decoder_name"] == "bp"
        assert "elapsed_s" in decoder_report
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_emits_decoder_eval_outputs():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_qec_eval_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
            decoder_eval=True,
            eval_decoders=["mwpm", "bp"],
            eval_seeds=[11, 12],
            eval_option_grid=[{}, {"max_iter": 2, "damping": 0.4}],
            eval_parallelism=2,
            eval_retries=1,
            eval_resume=True,
        )
        actual_out = Path(result["runtime"]["out_dir"])

        for name in [
            "decoder_eval_report.json",
            "decoder_eval_table.csv",
            "figures/decoder_pareto.png",
            "batch_manifest.json",
            "resume_state.json",
            "failed_tasks.jsonl",
            "run_manifest.json",
        ]:
            assert (actual_out / name).exists(), f"missing artifact: {name}"

        report = json.loads((actual_out / "decoder_eval_report.json").read_text(encoding="utf-8"))
        batch_manifest = json.loads((actual_out / "batch_manifest.json").read_text(encoding="utf-8"))
        resume_state = json.loads((actual_out / "resume_state.json").read_text(encoding="utf-8"))
        manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))
        table_text = (actual_out / "decoder_eval_table.csv").read_text(encoding="utf-8-sig")

        assert report["schema_version"] == "1.0"
        assert report["status"] in {"ok", "partial"}
        assert int(report["total_runs"]) == 8
        assert batch_manifest["schema_version"] == "1.0"
        assert int(batch_manifest["total_tasks"]) == 8
        assert resume_state["schema_version"] == "1.0"
        assert "decoder_eval_report" in manifest["outputs"]
        assert "decoder_eval_table" in manifest["outputs"]
        assert "decoder_pareto" in manifest["outputs"]
        assert "batch_manifest" in manifest["outputs"]
        assert "resume_state" in manifest["outputs"]
        assert "failed_tasks" in manifest["outputs"]
        assert "decoder,decoder_rev,seed,status" in table_text
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_decoder_eval_resume_skips_completed_tasks():
    out_dir = Path("runs") / f"pytest_qec_resume_{uuid.uuid4().hex[:8]}"
    resume_path = out_dir / "resume_state.json"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        decoder_input = DecoderInput(
            syndrome=SyndromeFrame(rounds=3, detectors=[[0, 1], [1, 0], [0, 0]], observables=[0, 1]),
            prior=PriorModel(nodes=[{"id": 0}, {"id": 1}], edges=[{"u": 0, "v": 1, "weight": 1.0}]),
        )

        first_report, *_ = run_decoder_eval(
            decoder_input,
            decoders=["mwpm", "bp"],
            seeds=[21, 22],
            option_grid=[{}],
            resume=True,
            resume_state_path=resume_path,
        )
        assert int(first_report["total_runs"]) == 4
        second_report, *_ = run_decoder_eval(
            decoder_input,
            decoders=["mwpm", "bp"],
            seeds=[21, 22],
            option_grid=[{}],
            resume=True,
            resume_state_path=resume_path,
        )
        assert int(second_report["skipped_runs"]) >= 4
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_workflow_emits_pauli_plus_budget_outputs():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_qec_pp_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = _run_task_from_kwargs(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
            decoder="mock",
            pauli_plus_analysis=True,
            qec_engine="auto",
            pauli_plus_code_distances=[3, 5],
            pauli_plus_shots=1000,
        )
        actual_out = Path(result["runtime"]["out_dir"])

        for name in ["scaling_report.json", "error_budget_pauli_plus.json", "component_ablation.csv", "run_manifest.json"]:
            assert (actual_out / name).exists(), f"missing artifact: {name}"

        scaling = json.loads((actual_out / "scaling_report.json").read_text(encoding="utf-8"))
        budget = json.loads((actual_out / "error_budget_pauli_plus.json").read_text(encoding="utf-8"))
        manifest = json.loads((actual_out / "run_manifest.json").read_text(encoding="utf-8"))
        ablation_csv = (actual_out / "component_ablation.csv").read_text(encoding="utf-8-sig")

        assert scaling["schema_version"] == "1.0"
        assert "epsilon_3" in scaling and "epsilon_5" in scaling and "lambda_3_5" in scaling
        assert "native_runs_ratio" in scaling
        assert 0.0 <= float(scaling["native_runs_ratio"]) <= 1.0
        assert budget["schema_version"] == "1.0"
        assert "contributions" in budget and isinstance(budget["contributions"], dict)
        assert "ablations" in budget and isinstance(budget["ablations"], dict)
        assert "delta_inverse_lambda" in ablation_csv
        assert "scaling_report" in manifest["outputs"]
        assert "error_budget_pauli_plus" in manifest["outputs"]
        assert "component_ablation" in manifest["outputs"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)
