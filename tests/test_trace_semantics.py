from qsim.analysis.observables import compute_observables
import pytest

from qsim.analysis.trace_semantics import (
    annotate_trace_metadata,
    extract_p1_series,
    pointwise_compare_compatibility,
    state_encoding,
)
from qsim.common.schemas import Trace


def test_annotate_qutip_trace_as_per_qubit_probabilities():
    trace = Trace(
        engine="qutip",
        times=[0.0, 1.0],
        states=[[0.1, 0.2], [0.3, 0.4]],
        metadata={"num_qubits": 2},
    )

    annotate_trace_metadata(trace)

    assert state_encoding(trace) == "per_qubit_excited_probability"


def test_annotate_julia_single_qubit_trace_as_basis_population():
    trace = Trace(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        states=[[1.0, 0.0], [0.4, 0.6]],
        metadata={"num_qubits": 1},
    )

    annotate_trace_metadata(trace)

    assert state_encoding(trace) == "basis_population_single_qubit"


def test_compute_observables_does_not_invent_second_qubit_for_single_qubit_basis_population():
    trace = Trace(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        states=[[1.0, 0.0], [0.25, 0.75]],
        metadata={"num_qubits": 1},
    )
    annotate_trace_metadata(trace)

    obs = compute_observables(trace).values

    assert obs["final_p0"] == 0.25
    assert obs["final_p1"] == 0.75
    assert "final_q1_excited" not in obs


def test_compute_observables_marks_ambiguous_multi_qubit_population_vector_as_safe_only():
    trace = Trace(
        engine="julia-quantumoptics",
        times=[0.0, 1.0],
        states=[[1.0, 0.0], [0.4, 0.6]],
        metadata={"num_qubits": 2},
    )
    annotate_trace_metadata(trace)

    obs = compute_observables(trace).values

    assert state_encoding(trace) == "ambiguous_population_vector"
    assert "final_p1" not in obs
    assert "final_q0_excited" not in obs
    assert obs["final_state_sum"] == 1.0


def test_pointwise_compare_requires_matching_safe_encoding():
    ref = Trace(
        engine="qutip",
        times=[0.0, 1.0],
        states=[[0.0], [0.5]],
        metadata={"num_qubits": 1},
    )
    other = Trace(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        states=[[1.0, 0.0], [0.5, 0.5]],
        metadata={"num_qubits": 1},
    )
    annotate_trace_metadata(ref)
    annotate_trace_metadata(other)

    comparable, reason = pointwise_compare_compatibility(ref, other)

    assert comparable is False
    assert "state encoding mismatch" in reason


def test_extract_p1_series_from_single_qubit_basis_population():
    trace = Trace(
        engine="julia-quantumoptics",
        times=[0.0, 1.0, 2.0],
        states=[[1.0, 0.0], [0.6, 0.4], [0.2, 0.8]],
        metadata={"num_qubits": 1},
    )
    annotate_trace_metadata(trace)

    p1 = extract_p1_series(trace)

    assert p1 == [0.0, 0.4, 0.8]


def test_extract_p1_series_from_single_qubit_per_qubit_probability():
    trace = Trace(
        engine="qutip",
        times=[0.0, 1.0, 2.0],
        states=[[0.1], [0.2], [0.3]],
        metadata={"num_qubits": 1},
    )
    annotate_trace_metadata(trace)

    p1 = extract_p1_series(trace)

    assert p1 == [0.1, 0.2, 0.3]


def test_extract_p1_series_rejects_non_single_qubit_trace():
    trace = Trace(
        engine="qutip",
        times=[0.0, 1.0],
        states=[[0.1, 0.2], [0.3, 0.4]],
        metadata={"num_qubits": 2},
    )
    annotate_trace_metadata(trace)

    with pytest.raises(ValueError, match="not single-qubit"):
        extract_p1_series(trace)
