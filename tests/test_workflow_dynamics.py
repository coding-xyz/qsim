import json
import shutil
import uuid
from pathlib import Path

import pytest

from qsim.common.schemas import Trace
from qsim.ui.notebook import _collect_runtime_dependencies, run_workflow


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
        result = run_workflow(
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
        actual_out = Path(result["out_dir"])
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
        result = run_workflow(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            persist_artifacts=True,
            export_dxf=False,
            export_plots=False,
            compare_engines=["qutip"],
            allow_mock_fallback=False,
        )
        actual_out = Path(result["out_dir"])
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


def test_workflow_cross_engine_pairwise_metrics_with_mock_fallback():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_dyn_cmp_pair_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        try:
            result = run_workflow(
                qasm_text=qasm_text,
                backend_path="examples/backend.yaml",
                out_dir=str(out_dir),
                persist_artifacts=True,
                export_dxf=False,
                export_plots=False,
                compare_engines=["julia_qoptics"],
                allow_mock_fallback=True,
            )
        except RuntimeError as exc:
            pytest.skip(f"julia runtime unavailable for compare test: {exc}")
        actual_out = Path(result["out_dir"])
        report = json.loads((actual_out / "cross_engine_compare.json").read_text(encoding="utf-8"))
        settings = json.loads((actual_out / "settings_report.json").read_text(encoding="utf-8"))

        assert report["status"] == "ok"
        assert len(report["runs"]) >= 2
        assert len(report["pairwise"]) >= 1
        pair = report["pairwise"][0]
        assert pair["samples_compared"] >= 1
        assert "mse" in pair and "mae" in pair
        assert settings["workflow"]["allow_mock_fallback"] is True
        assert "julia_qoptics" in settings["workflow"]["compare_engines_requested"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        if actual_out != out_dir:
            shutil.rmtree(actual_out, ignore_errors=True)


def test_workflow_solver_mode_mcwf_persisted_in_outputs():
    qasm_text = Path("examples/bell.qasm").read_text(encoding="utf-8")
    out_dir = Path("runs") / f"pytest_dyn_mcwf_{uuid.uuid4().hex[:8]}"
    actual_out = out_dir
    try:
        result = run_workflow(
            qasm_text=qasm_text,
            backend_path="examples/backend.yaml",
            out_dir=str(out_dir),
            solver_mode="mcwf",
            compare_engines=["qutip"],
            persist_artifacts=True,
            export_dxf=False,
            export_plots=False,
        )
        actual_out = Path(result["out_dir"])
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

    deps = _collect_runtime_dependencies(trace, "julia_qtoolbox")

    assert deps["julia"] == "1.12.5"
    assert deps["julia_backend:QuantumToolbox"] == "0.31.0"
