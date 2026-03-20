from __future__ import annotations

import json
from pathlib import Path

import pytest

from qsim.ui.cli import build_parser
from qsim.workflow import run_task_files
from qsim.workflow.task_io import (
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
    load_task_config_file,
)


def _write_basic_solver_device_and_pulse(tmp_path: Path) -> tuple[Path, Path, Path]:
    solver_cfg = {
        "template": "qutip_default",
        "backend": {"level": "qubit", "analysis_pipeline": "default", "truncation": {}},
        "run": {"engine": "qutip", "solver_mode": "me", "seed": 7, "sweep": []},
        "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
    }
    device_cfg = {
        "template": "transmon_default",
        "device": {"simulation_level": "qubit", "qubits": [{"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8}]},
        "noise": {"model": "markovian_lindblad", "T1_s": 1e-5, "T2_s": 8e-6},
    }
    pulse_cfg = {"template": "single_qubit_default"}
    solver_path = tmp_path / "solver.json"
    device_path = tmp_path / "device.json"
    pulse_path = tmp_path / "pulse.json"
    solver_path.write_text(json.dumps(solver_cfg, ensure_ascii=False), encoding="utf-8")
    device_path.write_text(json.dumps(device_cfg, ensure_ascii=False), encoding="utf-8")
    pulse_path.write_text(json.dumps(pulse_cfg, ensure_ascii=False), encoding="utf-8")
    return solver_path, device_path, pulse_path


def test_load_task_config_file_three_way_schema(tmp_path: Path):
    qasm_path = tmp_path / "task.qasm"
    qasm_path.write_text("OPENQASM 3; qubit[1] q;", encoding="utf-8")
    solver_path, device_path, pulse_path = _write_basic_solver_device_and_pulse(tmp_path)

    cfg = {
        "schema_version": "2.0",
        "target": ["decoder_eval_report"],
        "input": {
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "device_config": str(device_path.name),
            "pulse_config": str(pulse_path.name),
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
    assert task.input.device_config_path == str(device_path.resolve())
    assert task.input.pulse_config_path == str(pulse_path.resolve())
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
    solver_path, device_path, _pulse_path = _write_basic_solver_device_and_pulse(tmp_path)
    task_with_both = {
        "target": "trace",
        "input": {
            "qasm_text": "OPENQASM 3; qubit[1] q;",
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "device_config": str(device_path.name),
        },
        "output": {"out_dir": "runs/demo"},
    }
    task_with_none = {
        "target": "trace",
        "input": {
            "solver_config": str(solver_path.name),
            "device_config": str(device_path.name),
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
    solver_path, device_path, _pulse_path = _write_basic_solver_device_and_pulse(tmp_path)
    cfg = {
        "target": "trace",
        "input": {
            "qasm_text": "OPENQASM 3; qubit[1] q;",
            "solver_config": str(solver_path.name),
            "device_config": str(device_path.name),
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


def test_solver_config_loads_frame_options(tmp_path: Path):
    cfg = {
        "backend": {"level": "qubit"},
        "run": {"engine": "qutip", "solver_mode": "me"},
        "frame": {
            "mode": "rotating",
            "reference": "explicit",
            "rwa": True,
            "qubit_reference_freqs_Hz": [5.0e9],
        },
    }
    p = tmp_path / "solver_frame.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    solver = load_solver_config_file(p)

    assert solver.frame.mode == "rotating"
    assert solver.frame.reference == "explicit"
    assert solver.frame.rwa is True
    assert solver.frame.qubit_reference_freqs_Hz == [5.0e9]


def test_solver_config_loads_timing_controls(tmp_path: Path):
    cfg = {
        "backend": {"level": "qubit"},
        "run": {
            "engine": "qutip",
            "solver_mode": "me",
            "dt_s": 1.0e-9,
            "t_end_s": 3.0e-7,
            "t_padding_s": 2.0e-8,
        },
    }
    p = tmp_path / "solver_timing.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")

    solver = load_solver_config_file(p)

    assert solver.run.dt_s == 1.0e-9
    assert solver.run.t_end_s == 3.0e-7
    assert solver.run.t_padding_s == 2.0e-8


def test_device_config_loads_with_template(tmp_path: Path):
    p = tmp_path / "device.yaml"
    p.write_text(
        "template: transmon_default\ndevice:\n  simulation_level: qubit\nnoise:\n  model: markovian_lindblad\n  T1_s: 1.0e-5\n",
        encoding="utf-8",
    )
    cfg = load_device_config_file(p)
    assert cfg.device is None or isinstance(cfg.device, dict)
    assert isinstance(cfg.noise, dict)


def test_pulse_config_loads_with_template(tmp_path: Path):
    p = tmp_path / "pulse.yaml"
    p.write_text("template: single_qubit_default\npulse:\n  gate_duration_ns: 24.0\n", encoding="utf-8")
    pulse = load_pulse_config_file(p)
    assert pulse["gate_duration_ns"] == 24.0
    assert pulse["xy_freq_Hz"] == 5.0e9


def test_device_config_with_qubits_is_accepted(tmp_path: Path):
    p = tmp_path / "device.json"
    p.write_text(
        json.dumps(
            {
                "device": {
                    "simulation_level": "qubit",
                    "qubits": [{"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8, "T1_s": 1.2e-4, "T2_s": 9.0e-5}]
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_device_config_file(p)

    assert cfg.device is not None
    assert cfg.device["qubits"][0]["freq_Hz"] == 5.0e9


def test_cli_parser_supports_task_and_optional_overrides():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-task",
            "--task-config",
            "tasks/demo.yaml",
            "--solver-config",
            "solvers/qutip.yaml",
            "--device-config",
            "device/default.yaml",
            "--pulse-config",
            "pulses/default.yaml",
        ]
    )
    assert args.cmd == "run-task"
    assert args.task_config == "tasks/demo.yaml"
    assert args.solver_config == "solvers/qutip.yaml"
    assert args.device_config == "device/default.yaml"
    assert args.pulse_config == "pulses/default.yaml"


def test_cli_parser_rejects_removed_run_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--qasm", "a", "--backend", "b", "--out", "c"])


def test_run_task_files_accepts_task_with_embedded_solver_device_refs(tmp_path: Path):
    qasm_path = tmp_path / "task.qasm"
    qasm_path.write_text("OPENQASM 3;\nqubit[1] q;\nbit[1] c;\nmeasure q[0] -> c[0];\n", encoding="utf-8")
    solver_path, device_path, pulse_path = _write_basic_solver_device_and_pulse(tmp_path)

    task_cfg = {
        "target": "trace",
        "input": {
            "qasm_path": "task.qasm",
            "solver_config": str(solver_path.name),
            "device_config": str(device_path.name),
            "pulse_config": str(pulse_path.name),
        },
        "output": {"out_dir": "runs/direct_path", "persist_artifacts": False, "export_plots": False, "export_dxf": False},
    }
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps(task_cfg, ensure_ascii=False), encoding="utf-8")

    result = run_task_files(task_config=task_path)
    assert isinstance(result, dict)
    assert "runtime" in result and "out_dir" in result["runtime"]


def test_run_task_files_accepts_solver_device_and_pulse_overrides_for_task_without_embedded_refs(tmp_path: Path):
    qasm_path = tmp_path / "task.qasm"
    qasm_path.write_text("OPENQASM 3;\nqubit[1] q;\nbit[1] c;\nmeasure q[0] -> c[0];\n", encoding="utf-8")
    solver_path, device_path, pulse_path = _write_basic_solver_device_and_pulse(tmp_path)

    task_cfg = {
        "target": "trace",
        "input": {
            "qasm_path": "task.qasm",
        },
        "output": {"out_dir": "runs/override_path", "persist_artifacts": False, "export_plots": False, "export_dxf": False},
    }
    task_path = tmp_path / "task_override.json"
    task_path.write_text(json.dumps(task_cfg, ensure_ascii=False), encoding="utf-8")

    result = run_task_files(
        task_config=task_path,
        solver_config=solver_path,
        device_config=device_path,
        pulse_config=pulse_path,
    )
    assert isinstance(result, dict)
    assert "runtime" in result and "out_dir" in result["runtime"]
