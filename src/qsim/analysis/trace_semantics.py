"""Helpers for annotating and reasoning about trace state semantics."""

from __future__ import annotations

from qsim.common.schemas import Trace


def _first_row(trace: Trace) -> list[float]:
    for row in trace.states:
        if row:
            return row
    return []


def _rows_sum_to_one(trace: Trace, *, atol: float = 1e-6) -> bool:
    rows = [row for row in trace.states if row]
    if not rows:
        return False
    return all(abs(sum(float(v) for v in row) - 1.0) <= atol for row in rows)


def infer_state_encoding(
    trace: Trace,
    *,
    num_qubits: int | None = None,
    dimension: int | None = None,
    engine_name: str | None = None,
) -> str:
    """Infer a safe, explicit state encoding label for a trace.

    The labels intentionally prefer ``ambiguous_*`` over aggressive guesses when
    multiple interpretations are plausible.
    """
    row = _first_row(trace)
    if not row:
        return "unknown"

    n = len(row)
    num_qubits = int(num_qubits) if num_qubits else None
    dimension = int(dimension) if dimension else None
    name = str(engine_name or trace.engine or "").strip().lower()
    sums_to_one = _rows_sum_to_one(trace)

    if name.startswith("qutip"):
        if num_qubits and n == num_qubits:
            return "per_qubit_excited_probability"
        return "unknown"

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


def annotate_trace_metadata(
    trace: Trace,
    *,
    num_qubits: int | None = None,
    dimension: int | None = None,
    engine_name: str | None = None,
) -> Trace:
    """Attach canonical state semantics metadata to a trace in-place."""
    meta = dict(getattr(trace, "metadata", {}) or {})
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
            trace,
            num_qubits=num_qubits,
            dimension=dimension,
            engine_name=(engine_name or trace.engine),
        )
    meta["state_encoding"] = encoding
    trace.metadata = meta
    return trace


def state_encoding(trace: Trace) -> str:
    """Return the canonical state encoding for a trace."""
    meta = dict(getattr(trace, "metadata", {}) or {})
    return str(meta.get("state_encoding", "unknown")).strip().lower() or "unknown"


def extract_p1_series(trace: Trace) -> list[float]:
    """Extract a semantically safe single-qubit ``p1(t)`` series from a trace.

    Supported encodings:
    - ``per_qubit_excited_probability``: use ``row[0]`` for single-qubit case.
    - ``basis_population_single_qubit``: use ``row[1]``.

    Returns:
        A list of ``p1`` values aligned with ``trace.times``.

    Raises:
        ValueError: If the trace encoding cannot be safely interpreted as
        single-qubit ``p1(t)``.
    """
    enc = state_encoding(trace)
    rows = [row for row in trace.states if row]
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

    raise ValueError(f"trace encoding does not support single-qubit p1 extraction: {enc}")


def pointwise_compare_compatibility(ref: Trace, other: Trace) -> tuple[bool, str]:
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
