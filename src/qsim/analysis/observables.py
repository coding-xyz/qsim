"""Observable extraction helpers for simulation traces."""

from __future__ import annotations

from qsim.analysis.trace_semantics import state_encoding
from qsim.common.schemas import Observables, Trace


def compute_observables(trace: Trace) -> Observables:
    """Compute summary observables from a simulation trace.

    Args:
        trace: Time-ordered state/population samples produced by an engine.

    Returns:
        ``Observables`` containing summary scalars used by downstream reports.
        Common keys include ``samples``, ``final_p0``, ``final_p1``, and
        ``mean_excited`` when the trace encoding is known. For traces marked as
        basis populations or ambiguous population vectors, only semantically
        safe fields are emitted.
    """
    if not trace.states:
        return Observables(values={"samples": 0.0})

    final = trace.states[-1]
    values: dict[str, float] = {
        "samples": float(len(trace.states)),
        "state_dim": float(len(final)),
    }
    encoding = state_encoding(trace)

    if encoding == "per_qubit_excited_probability":
        if len(final) >= 1:
            values["final_p1"] = float(final[0])
            values["final_p0"] = float(1.0 - final[0])
        else:
            values["final_p0"] = 0.0
            values["final_p1"] = 0.0

        if len(final) > 1:
            for i, val in enumerate(final):
                values[f"final_q{i}_excited"] = float(val)
            mean_all = sum(sum(row) / max(1, len(row)) for row in trace.states) / len(trace.states)
            values["mean_excited"] = float(mean_all)
        else:
            values["mean_excited"] = float(sum(row[0] if row else 0.0 for row in trace.states) / len(trace.states))
        return Observables(values=values)

    if encoding == "basis_population_single_qubit" and len(final) >= 2:
        values["final_basis_0_population"] = float(final[0])
        values["final_basis_1_population"] = float(final[1])
        values["final_p0"] = float(final[0])
        values["final_p1"] = float(final[1])
        values["mean_excited"] = float(sum(float(row[1]) for row in trace.states if len(row) >= 2) / len(trace.states))
        return Observables(values=values)

    if final:
        values["final_state_sum"] = float(sum(final))

    return Observables(values=values)
