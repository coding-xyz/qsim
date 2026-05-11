from __future__ import annotations

import json
from pathlib import Path

from qsim.workflow import create_model
from qsim.workflow.model_utils import compact_runtime_details


def _write_task_bundle(tmp_path: Path) -> Path:
    solver = tmp_path / "solver.json"
    solver.write_text(
        json.dumps(
            {
                "backend": {"level": "qubit", "analysis_pipeline": "default"},
                "run": {"engine": "qutip", "solver_mode": "me", "seed": 17},
            }
        ),
        encoding="utf-8",
    )
    device = tmp_path / "device.json"
    device.write_text(
        json.dumps(
            {
                "device": {"simulation_level": "qubit", "qubits": [{"freq_Hz": 5.0e9, "anharmonicity_Hz": -2.0e8}]},
                "noise": {"model": "markovian_lindblad", "T1_s": 1e-5, "T2_s": 8e-6},
            }
        ),
        encoding="utf-8",
    )
    pulse = tmp_path / "pulse.json"
    pulse.write_text(json.dumps({"pulse": {"gate_duration_ns": 20.0, "xy_freq_Hz": 5.0e9}}), encoding="utf-8")
    analyser = tmp_path / "analyser.json"
    analyser.write_text(
        json.dumps({"trajectory": {"save_times": "all", "save_final_state": True}, "metrics": ["population"]}),
        encoding="utf-8",
    )
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps(
            {
                "target": "trajectory",
                "input": {
                    "qasm_text": "OPENQASM 3; qubit[1] q; bit[1] c; rz(theta) q[0]; measure q[0] -> c[0];",
                    "solver_config": "solver.json",
                    "device_config": "device.json",
                    "pulse_config": "pulse.json",
                    "analyser_config": "analyser.json",
                    "param_bindings": {"theta": 0.3},
                },
                "output": {"out_dir": "runs/test_inline", "persist_artifacts": False, "export_plots": False, "export_dxf": False},
            }
        ),
        encoding="utf-8",
    )
    return task


def test_model_run_applies_param_bindings_and_records_run_scoped_artifacts(tmp_path: Path):
    task_path = _write_task_bundle(tmp_path)
    model = create_model(task_config=task_path)
    model.run()
    run = model.runs["solver_0"]

    assert run.artifacts.circuit is not None
    assert run.result is not None
    assert run.result.runtime_metadata is not None
    assert run.result.runtime_metadata["solver_mode"] == "me"
    assert run.artifacts.circuit.gates[0].name == "rz"
    assert float(run.artifacts.circuit.gates[0].params[0]) == 0.3


def test_compact_runtime_details_summarizes_large_payloads():
    compact = compact_runtime_details(
        {
            "solver_impl": "quantumoptics.timeevolution.master_dynamic",
            "collapse_counts": {"relaxation": 1, "dephasing": 1},
            "quantum_state_trajectory": {
                "requested_kind": "density_matrix",
                "actual_kind": "density_matrix",
                "snapshots": [[1], [2], [3]],
                "runs": [[[1], [2], [3]], [[4], [5], [6]]],
            },
            "measurement_records": [{"t": 0.0}, {"t": 1.0}],
        }
    )

    assert compact["solver_impl"] == "quantumoptics.timeevolution.master_dynamic"
    assert compact["collapse_counts"] == {"relaxation": 1, "dephasing": 1}
    assert compact["quantum_state_trajectory"]["snapshots"] == 3
    assert compact["quantum_state_trajectory"]["runs"] == 2
    assert "measurement_records" in compact
