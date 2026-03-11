from __future__ import annotations

import json
from pathlib import Path

import pytest

from qsim.ui.cli import build_parser
from qsim.workflow import run_task_files
from qsim.workflow.task_io import (
    load_hardware_config_file,
    load_solver_config_file,
    load_task_config_file,
)


def _write_basic_solver_and_hardware(tmp_path: Path) -> tuple[Path, Path]:
    solver_cfg = {
        "template": "qutip_default",
        "backend": {"level": "qubit", "analysis_pipeline": "default", "truncation": {}},
        "run": {"engine": "qutip", "solver_mode": "me", "seed": 7, "sweep": []},
    }
    hardware_cfg = {
        "template": "transmon_default",
        "noise": {"model": "markovian_lindblad", "t1": 1e-5, "t2": 8e-6},
    }
    solver_path = tmp_path / "solver.json"
    hardware_path = tmp_path / "hardware.json"
    solver_path.write_text(json.dumps(solver_cfg, ensure_ascii=False), encoding="utf-8")
    hardware_path.write_text(json.dumps(hardware_cfg, ensure_ascii=False), encoding="utf-8")
    return solver_path, hardware_path


def test_load_task_config_file_three_way_schema(tmp_path: Path):
    qasm_path = tmp_path / "task.qasm"
    qasm_path.write_text("OPENQASM 3; qubit[1] q;", encoding="utf-8")
    solver_path, hardware_path = _write_basic_solver_and_hardware(tmp_path)

    cfg = {
        "schema_version": "2.0",
        "target": ["decoder_eval_report"],
        "input": {
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "hardware_config": str(hardware_path.name),
            "param_bindings": {"theta": 0.1},
        },
        "features": {"decoder_eval": True, "eval_parallelism": 2},
        "output": {
            "out_dir": "runs/demo",
            "persist_artifacts": False,
            "artifact_mode": "targeted",
            "export_plots": False,
            "session_dir": "runs/session",
            "session_auto_commit": True,
        },
    }
    cfg_path = tmp_path / "task.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    task = load_task_config_file(cfg_path)
    assert "OPENQASM 3" in task.input.qasm_text
    assert task.input.solver_config_path == str(solver_path.resolve())
    assert task.input.hardware_config_path == str(hardware_path.resolve())
    assert task.output.out_dir == str((tmp_path / "runs" / "demo").resolve())
    assert task.features.decoder_eval is True
    assert task.output.persist_artifacts is False
    assert task.output.artifact_mode == "targeted"
    assert task.output.session_auto_commit is True
    assert task.output.session_dir == str((tmp_path / "runs" / "session").resolve())
    assert task.target == ["decoder_eval_report"]


def test_task_config_requires_target_and_input(tmp_path: Path):
    cfg_path = tmp_path / "bad_task.json"
    cfg_path.write_text(json.dumps({"input": {"qasm_text": "OPENQASM 3; qubit[1] q;"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="requires `target`"):
        load_task_config_file(cfg_path)


def test_task_config_requires_exactly_one_qasm_source(tmp_path: Path):
    solver_path, hardware_path = _write_basic_solver_and_hardware(tmp_path)
    task_with_both = {
        "target": "trace",
        "input": {
            "qasm_text": "OPENQASM 3; qubit[1] q;",
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "hardware_config": str(hardware_path.name),
        },
        "output": {"out_dir": "runs/demo"},
    }
    task_with_none = {
        "target": "trace",
        "input": {
            "solver_config": str(solver_path.name),
            "hardware_config": str(hardware_path.name),
        },
        "output": {"out_dir": "runs/demo"},
    }
    (tmp_path / "task.qasm").write_text("OPENQASM 3; qubit[1] q;", encoding="utf-8")

    both_path = tmp_path / "both.json"
    both_path.write_text(json.dumps(task_with_both), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_task_config_file(both_path)

    none_path = tmp_path / "none.json"
    none_path.write_text(json.dumps(task_with_none), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_task_config_file(none_path)


def test_task_config_rejects_features_not_supported_by_target(tmp_path: Path):
    solver_path, hardware_path = _write_basic_solver_and_hardware(tmp_path)
    cfg = {
        "target": "trace",
        "input": {
            "qasm_text": "OPENQASM 3; qubit[1] q;",
            "solver_config": str(solver_path.name),
            "hardware_config": str(hardware_path.name),
        },
        "output": {"out_dir": "runs/demo"},
        "features": {"decoder_eval": True},
    }
    p = tmp_path / "bad_feature.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="not supported by selected target"):
        load_task_config_file(p)


def test_solver_config_engine_dependency_validation(tmp_path: Path):
    cfg = {
        "backend": {"level": "qubit"},
        "run": {
            "engine": "qutip",
            "julia_bin": "julia",
        },
    }
    p = tmp_path / "solver_bad.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError, match="not supported by selected engine"):
        load_solver_config_file(p)


def test_hardware_config_loads_with_template(tmp_path: Path):
    p = tmp_path / "hardware.yaml"
    p.write_text(
        "template: transmon_default\nnoise:\n  model: markovian_lindblad\n  t1: 1.0e-5\n",
        encoding="utf-8",
    )
    hw = load_hardware_config_file(p)
    assert hw.hardware is None or isinstance(hw.hardware, dict)
    assert isinstance(hw.noise, dict)


def test_cli_parser_supports_task_and_optional_overrides():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-task",
            "--task-config",
            "tasks/demo.yaml",
            "--solver-config",
            "solvers/qutip.yaml",
            "--hardware-config",
            "hardware/default.yaml",
        ]
    )
    assert args.cmd == "run-task"
    assert args.task_config == "tasks/demo.yaml"
    assert args.solver_config == "solvers/qutip.yaml"
    assert args.hardware_config == "hardware/default.yaml"


def test_cli_parser_rejects_removed_run_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--qasm", "a", "--backend", "b", "--out", "c"])


def test_run_task_files_accepts_task_with_embedded_solver_hardware_refs(tmp_path: Path):
    qasm_path = tmp_path / "task.qasm"
    qasm_path.write_text("OPENQASM 3;\nqubit[1] q;\nbit[1] c;\nmeasure q[0] -> c[0];\n", encoding="utf-8")
    solver_path, hardware_path = _write_basic_solver_and_hardware(tmp_path)

    task_cfg = {
        "target": "trace",
        "input": {
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "hardware_config": str(hardware_path.name),
        },
        "output": {"out_dir": "runs/direct_path", "persist_artifacts": False, "export_plots": False, "export_dxf": False},
    }
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task_cfg, ensure_ascii=False), encoding="utf-8")

    result = run_task_files(task_config=task_path)
    assert isinstance(result, dict)
    assert "runtime" in result and "out_dir" in result["runtime"]
