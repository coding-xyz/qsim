import json
from pathlib import Path
import uuid

from qsim.common.schemas import Trace
from qsim.pulse.visualize import load_trace_h5
from qsim.workflow.output import write_trace_h5


def test_trace_h5_roundtrip_preserves_metadata():
    trace = Trace(
        engine="qutip",
        times=[0.0, 1.0],
        states=[[0.1], [0.2]],
        metadata={
            "state_encoding": "per_qubit_excited_probability",
            "num_qubits": 1,
            "model_dimension": 18,
            "readout_observables": {
                "schema_version": "1.0",
                "a_out": [[0.1, -0.2], [0.3, -0.4]],
                "feedback": {"enabled": True, "mode": "predictor_corrector"},
            },
            "quantum_state_trace": {
                "requested_kind": "wave_function",
                "actual_kind": "wave_function",
                "encoding": "complex_pairs",
                "snapshots": [[[1.0, 0.0]], [[0.0, 1.0]]],
            },
        },
    )

    out_dir = Path(".pytest_tmp_trace_io")
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"trace_{uuid.uuid4().hex}.h5"
    write_trace_h5(trace, out)
    loaded = load_trace_h5(out)

    assert loaded.engine == trace.engine
    assert loaded.times == trace.times
    assert loaded.states == trace.states
    assert loaded.metadata["state_encoding"] == "per_qubit_excited_probability"
    assert loaded.metadata["readout_observables"]["feedback"]["enabled"] is True
    assert loaded.metadata["quantum_state_trace"]["actual_kind"] == "wave_function"

    # Keep one direct JSON assertion so nested metadata layout is stable for notebooks.
    payload = json.loads(json.dumps(loaded.metadata, ensure_ascii=False))
    assert payload["readout_observables"]["a_out"][1] == [0.3, -0.4]
