"""Observable extraction helpers for simulation traces."""

from __future__ import annotations

from qsim.analysis.trajectory_semantics import state_encoding, state_rows
from qsim.common.schemas import Observables, Trajectory


def compute_observables(trajectory: Trajectory) -> Observables:
    """Compute summary observables from a simulation Trajectory.

    Args:
        trajectory: Time-ordered state/population samples produced by an engine.

    Returns:
        ``Observables`` containing summary scalars used by downstream reports.
        Common keys include ``samples``, ``final_p0``, ``final_p1``, and
        ``mean_excited`` when the Trajectory encoding is known. For traces marked as
        basis populations or ambiguous population vectors, only semantically
        safe fields are emitted.
    """
    rows = state_rows(trajectory)
    if not rows:
        return Observables(values={"samples": 0.0})

    final = rows[-1]
    values: dict[str, float] = {
        "samples": float(len(rows)),
        "state_dim": float(len(final)),
    }
    encoding = state_encoding(trajectory)

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
            mean_all = sum(sum(row) / max(1, len(row)) for row in rows) / len(rows)
            values["mean_excited"] = float(mean_all)
        else:
            values["mean_excited"] = float(sum(row[0] if row else 0.0 for row in rows) / len(rows))
        return Observables(values=values)

    if encoding == "basis_population_single_qubit" and len(final) >= 2:
        values["final_basis_0_population"] = float(final[0])
        values["final_basis_1_population"] = float(final[1])
        values["final_p0"] = float(final[0])
        values["final_p1"] = float(final[1])
        values["mean_excited"] = float(sum(float(row[1]) for row in rows if len(row) >= 2) / len(rows))
        return Observables(values=values)

    if final:
        values["final_state_sum"] = float(sum(final))

    return Observables(values=values)

