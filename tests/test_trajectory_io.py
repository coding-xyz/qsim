import json
from pathlib import Path
import uuid

from qsim.common.schemas import Trajectory
from qsim.pulse.visualize import load_trajectory_h5
from qsim.workflow.output import write_trajectory_h5


def test_trajectory_h5_roundtrip_preserves_metadata():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        wave_function={
            "requested_kind": "wave_function",
            "actual_kind": "wave_function",
            "encoding": "complex",
            "snapshots": [[1.0 + 0.0j], [0.0 + 1.0j]],
        },
        classical={
            "readout": {
                "schema_version": "1.0",
                "a_out": [[0.1, -0.2], [0.3, -0.4]],
                "feedback": {"enabled": True, "mode": "predictor_corrector"},
            },
        },
        metadata={"num_qubits": 1, "model_dimension": 18},
    )

    out_dir = Path(".pytest_tmp_trajectory_io")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"trajectory_{uuid.uuid4().hex}.h5"
    write_trajectory_h5(trajectory, out)
    loaded = load_trajectory_h5(out)

    assert loaded.engine == trajectory.engine
    assert loaded.times == trajectory.times
    assert loaded.classical["readout"]["feedback"]["enabled"] is True
    assert loaded.wave_function["actual_kind"] == "wave_function"
    assert loaded.wave_function["encoding"] == "complex"
    assert loaded.wave_function["snapshots"][1][0] == 1j

    payload = json.loads(json.dumps(loaded.classical, ensure_ascii=False))
    assert payload["readout"]["a_out"][1] == [0.3, -0.4]


def test_trajectory_h5_omits_absent_optional_sections():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[0.8 + 0.0j, 0.0j], [0.0j, 0.2 + 0.0j]],
            ],
        },
    )

    out_dir = Path(".pytest_tmp_trajectory_io")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"trajectory_sparse_{uuid.uuid4().hex}.h5"
    write_trajectory_h5(trajectory, out)

    import h5py

    with h5py.File(out, "r") as h5:
        assert "density_matrix_json" in h5
        assert "wave_function_json" not in h5
        assert "measurements_json" not in h5

