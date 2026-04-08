from qsim.analysis.observables import compute_observables
import pytest

from qsim.analysis.trajectory_semantics import (
    annotate_trajectory_metadata,
    extract_p1_series,
    pointwise_compare_compatibility,
    state_encoding,
)
from qsim.common.schemas import Trajectory, make_series_payload


def test_annotate_qutip_trace_as_per_qubit_probabilities():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        classical={
            "per_qubit_excited_probability": make_series_payload(
                [[0.1, 0.2], [0.3, 0.4]],
                quantity="per_qubit_excited_probability",
                description="Per-qubit excited-state probability <|1><1|>(t).",
                series_labels=["q0", "q1"],
            )
        },
        metadata={"num_qubits": 2},
    )

    annotate_trajectory_metadata(trajectory)

    assert state_encoding(trajectory) == "per_qubit_excited_probability"


def test_annotate_julia_single_qubit_trace_as_basis_population():
    trajectory = Trajectory(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        classical={
            "basis_population": make_series_payload(
                [[1.0, 0.0], [0.4, 0.6]],
                quantity="basis_population",
                description="Basis-state population time series aligned with the computational basis.",
                series_labels=["0", "1"],
            )
        },
        metadata={"num_qubits": 1},
    )

    annotate_trajectory_metadata(trajectory)

    assert state_encoding(trajectory) == "basis_population_single_qubit"


def test_compute_observables_does_not_invent_second_qubit_for_single_qubit_basis_population():
    trajectory = Trajectory(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        classical={
            "basis_population": make_series_payload(
                [[1.0, 0.0], [0.25, 0.75]],
                quantity="basis_population",
                description="Basis-state population time series aligned with the computational basis.",
                series_labels=["0", "1"],
            )
        },
        metadata={"num_qubits": 1},
    )
    annotate_trajectory_metadata(trajectory)

    obs = compute_observables(trajectory).values

    assert obs["final_p0"] == 0.25
    assert obs["final_p1"] == 0.75
    assert "final_q1_excited" not in obs


def test_compute_observables_marks_ambiguous_multi_qubit_population_vector_as_safe_only():
    trajectory = Trajectory(
        engine="julia-quantumoptics",
        times=[0.0, 1.0],
        classical={
            "basis_population": make_series_payload(
                [[1.0, 0.0], [0.4, 0.6]],
                quantity="basis_population",
                description="Basis-state population time series aligned with the computational basis.",
                series_labels=["0", "1"],
            )
        },
        metadata={"num_qubits": 2},
    )
    annotate_trajectory_metadata(trajectory)

    obs = compute_observables(trajectory).values

    assert state_encoding(trajectory) == "ambiguous_population_vector"
    assert "final_p1" not in obs
    assert "final_q0_excited" not in obs
    assert obs["final_state_sum"] == 1.0


def test_pointwise_compare_requires_matching_safe_encoding():
    ref = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        classical={
            "per_qubit_excited_probability": make_series_payload(
                [[0.0], [0.5]],
                quantity="per_qubit_excited_probability",
                description="Per-qubit excited-state probability <|1><1|>(t).",
                series_labels=["q0"],
            )
        },
        metadata={"num_qubits": 1},
    )
    other = Trajectory(
        engine="julia-quantumtoolbox",
        times=[0.0, 1.0],
        classical={
            "basis_population": make_series_payload(
                [[1.0, 0.0], [0.5, 0.5]],
                quantity="basis_population",
                description="Basis-state population time series aligned with the computational basis.",
                series_labels=["0", "1"],
            )
        },
        metadata={"num_qubits": 1},
    )
    annotate_trajectory_metadata(ref)
    annotate_trajectory_metadata(other)

    comparable, reason = pointwise_compare_compatibility(ref, other)

    assert comparable is False
    assert "state encoding mismatch" in reason


def test_extract_p1_series_from_single_qubit_basis_population():
    trajectory = Trajectory(
        engine="julia-quantumoptics",
        times=[0.0, 1.0, 2.0],
        classical={
            "basis_population": make_series_payload(
                [[1.0, 0.0], [0.6, 0.4], [0.2, 0.8]],
                quantity="basis_population",
                description="Basis-state population time series aligned with the computational basis.",
                series_labels=["0", "1"],
            )
        },
        metadata={"num_qubits": 1},
    )
    annotate_trajectory_metadata(trajectory)

    p1 = extract_p1_series(trajectory)

    assert p1 == [0.0, 0.4, 0.8]


def test_extract_p1_series_from_single_qubit_per_qubit_probability():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0, 2.0],
        classical={
            "per_qubit_excited_probability": make_series_payload(
                [[0.1], [0.2], [0.3]],
                quantity="per_qubit_excited_probability",
                description="Per-qubit excited-state probability <|1><1|>(t).",
                series_labels=["q0"],
            )
        },
        metadata={"num_qubits": 1},
    )
    annotate_trajectory_metadata(trajectory)

    p1 = extract_p1_series(trajectory)

    assert p1 == [0.1, 0.2, 0.3]


def test_extract_p1_series_rejects_non_single_qubit_trace():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        classical={
            "per_qubit_excited_probability": make_series_payload(
                [[0.1, 0.2], [0.3, 0.4]],
                quantity="per_qubit_excited_probability",
                description="Per-qubit excited-state probability <|1><1|>(t).",
                series_labels=["q0", "q1"],
            )
        },
        metadata={"num_qubits": 2},
    )
    annotate_trajectory_metadata(trajectory)

    with pytest.raises(ValueError, match="not single-qubit"):
        extract_p1_series(trajectory)

