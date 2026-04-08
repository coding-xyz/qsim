"""Helpers for annotating and reasoning about Trajectory state semantics."""

from __future__ import annotations

from qsim.common.schemas import Trajectory


def _complex_scalar(value) -> complex:
    if isinstance(value, complex):
        return value
    if isinstance(value, dict) and "__qsim_complex__" in value:
        pair = list(value.get("__qsim_complex__", []) or [])
        if len(pair) >= 2:
            return complex(float(pair[0]), float(pair[1]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return complex(float(value[0]), float(value[1]))
    return complex(float(value), 0.0)


def _state_payload(trajectory: Trajectory) -> tuple[str, dict]:
    classical = dict(getattr(trajectory, "classical", {}) or {})
    for key in ("per_qubit_excited_probability", "basis_population", "state_observables"):
        payload = classical.get(key, None)
        if isinstance(payload, dict) and isinstance(payload.get("values"), list) and payload.get("values"):
            return key, payload
    return "", {}


def state_rows(trajectory: Trajectory) -> list[list[float]]:
    """Return the primary classical state-like trajectory rows."""
    _key, payload = _state_payload(trajectory)
    if not payload:
        density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
        wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
        qstate = density_matrix or wave_function
        actual_kind = str(qstate.get("actual_kind", "")).strip().lower()
        snapshots = list(qstate.get("snapshots", []) or [])
        rows: list[list[float]] = []
        for snapshot in snapshots:
            if actual_kind == "density_matrix":
                row = []
                for i, item in enumerate(snapshot):
                    if i < len(item):
                        row.append(max(0.0, float(_complex_scalar(item[i]).real)))
                rows.append(row)
            elif actual_kind == "wave_function":
                rows.append([abs(_complex_scalar(v)) ** 2 for v in snapshot])
        return rows
    rows: list[list[float]] = []
    for row in list(payload.get("values", []) or []):
        if isinstance(row, list):
            rows.append([float(v) for v in row])
    return rows


def state_channel_name(trajectory: Trajectory) -> str:
    """Return the canonical primary classical state-like channel name."""
    key, _payload = _state_payload(trajectory)
    return key


def _first_row(trajectory: Trajectory) -> list[float]:
    for row in state_rows(trajectory):
        if row:
            return row
    return []


def _rows_sum_to_one(trajectory: Trajectory, *, atol: float = 1e-6) -> bool:
    rows = [row for row in state_rows(trajectory) if row]
    if not rows:
        return False
    return all(abs(sum(float(v) for v in row) - 1.0) <= atol for row in rows)


def infer_state_encoding(
    trajectory: Trajectory,
    *,
    num_qubits: int | None = None,
    dimension: int | None = None,
    engine_name: str | None = None,
) -> str:
    """Infer a safe, explicit state encoding label for a Trajectory.

    The labels intentionally prefer ``ambiguous_*`` over aggressive guesses when
    multiple interpretations are plausible.
    """
    row = _first_row(trajectory)
    if not row:
        return "unknown"

    n = len(row)
    num_qubits = int(num_qubits) if num_qubits else None
    dimension = int(dimension) if dimension else None
    name = str(engine_name or trajectory.engine or "").strip().lower()
    sums_to_one = _rows_sum_to_one(trajectory)

    if name.startswith("qutip") and num_qubits and n == num_qubits:
        return "per_qubit_excited_probability"

    if num_qubits == 1 and n == 2 and sums_to_one:
        return "basis_population_single_qubit"

    if dimension and n == dimension and sums_to_one:
        if num_qubits == 1:
            return "basis_population_single_qubit"
        return "basis_population"

    if num_qubits and n == num_qubits:
        if sums_to_one and num_qubits > 1:
            return "ambiguous_population_vector"
        return "per_qubit_excited_probability"

    return "unknown"


def annotate_trajectory_metadata(
    trajectory: Trajectory,
    *,
    num_qubits: int | None = None,
    dimension: int | None = None,
    engine_name: str | None = None,
) -> Trajectory:
    """Attach canonical state semantics metadata to a Trajectory in-place."""
    meta = dict(getattr(trajectory, "metadata", {}) or {})
    if num_qubits is None:
        raw = meta.get("num_qubits", None)
        num_qubits = int(raw) if raw is not None else None
    if dimension is None:
        raw = meta.get("model_dimension", None)
        dimension = int(raw) if raw is not None else None

    if num_qubits is not None:
        meta["num_qubits"] = int(num_qubits)
    if dimension is not None:
        meta["model_dimension"] = int(dimension)

    encoding = str(meta.get("state_encoding", "")).strip().lower()
    if not encoding:
        encoding = infer_state_encoding(
            trajectory,
            num_qubits=num_qubits,
            dimension=dimension,
            engine_name=(engine_name or trajectory.engine),
        )
    meta["state_encoding"] = encoding
    trajectory.metadata = meta
    return trajectory


def state_encoding(trajectory: Trajectory) -> str:
    """Return the canonical state encoding for a trajectory."""
    meta = dict(getattr(trajectory, "metadata", {}) or {})
    encoding = str(meta.get("state_encoding", "")).strip().lower()
    if encoding:
        return encoding
    raw_num_qubits = meta.get("num_qubits", None)
    raw_dimension = meta.get("model_dimension", None)
    num_qubits = int(raw_num_qubits) if raw_num_qubits is not None else None
    dimension = int(raw_dimension) if raw_dimension is not None else None
    return infer_state_encoding(
        trajectory,
        num_qubits=num_qubits,
        dimension=dimension,
        engine_name=str(getattr(trajectory, "engine", "") or ""),
    )


def extract_p1_series(trajectory: Trajectory) -> list[float]:
    """Extract a semantically safe single-qubit ``p1(t)`` series from a trajectory.

    Supported encodings:
    - ``per_qubit_excited_probability``: use ``row[0]`` for single-qubit case.
    - ``basis_population_single_qubit``: use ``row[1]``.

    Returns:
        A list of ``p1`` values aligned with ``trajectory.times``.

    Raises:
        ValueError: If the trajectory encoding cannot be safely interpreted as a
            single-qubit p1(t) series.
    """
    enc = state_encoding(trajectory)
    rows = [row for row in state_rows(trajectory) if row]
    if not rows:
        return []

    if enc == "per_qubit_excited_probability":
        if any(len(row) < 1 for row in rows):
            raise ValueError("invalid per_qubit_excited_probability rows")
        if any(len(row) > 1 for row in rows):
            raise ValueError("per_qubit_excited_probability is not single-qubit")
        return [float(row[0]) for row in rows]

    if enc == "basis_population_single_qubit":
        if any(len(row) < 2 for row in rows):
            raise ValueError("invalid basis_population_single_qubit rows")
        return [float(row[1]) for row in rows]

    raise ValueError(f"trajectory encoding does not support single-qubit p1 extraction: {enc}")


def pointwise_compare_compatibility(ref: Trajectory, other: Trajectory) -> tuple[bool, str]:
    """Return whether two traces support pointwise numeric comparison."""
    ref_enc = state_encoding(ref)
    other_enc = state_encoding(other)
    if ref_enc != other_enc:
        return False, f"state encoding mismatch: {ref_enc} vs {other_enc}"
    if ref_enc != "per_qubit_excited_probability":
        return False, f"state encoding not pointwise comparable: {ref_enc}"

    ref_row = _first_row(ref)
    other_row = _first_row(other)
    if ref_row and other_row and len(ref_row) != len(other_row):
        return False, f"state dimension mismatch: {len(ref_row)} vs {len(other_row)}"
    return True, ""


__all__ = [
    "annotate_trajectory_metadata",
    "extract_p1_series",
    "infer_state_encoding",
    "pointwise_compare_compatibility",
    "state_channel_name",
    "state_encoding",
    "state_rows",
]

