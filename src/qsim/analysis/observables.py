from __future__ import annotations

from qsim.common.schemas import Observables, Trace


def compute_observables(trace: Trace) -> Observables:
    """Compute summary observables from a simulation trace.

    Args:
        trace: Time-ordered state/population samples produced by an engine.

    Returns:
        ``Observables`` containing summary scalars used by downstream reports.
        Common keys include ``samples``, ``final_p0``, ``final_p1``, and
        ``mean_excited``. For multi-qubit rows, per-qubit terminal values are
        exposed as ``final_q{i}_excited``.
    """
    if not trace.states:
        return Observables(values={"samples": 0.0})

    final = trace.states[-1]
    values: dict[str, float] = {"samples": float(len(trace.states))}

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
