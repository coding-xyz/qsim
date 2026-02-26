from __future__ import annotations

from qsim.common.schemas import Observables, Report


def build_report(observables: Observables) -> Report:
    """Build a lightweight error-budget report from observables.

    The current model is heuristic and deterministic. It is intended as a
    stable baseline for regression checks before introducing richer physical
    decomposition models.

    Args:
        observables: Aggregated observables from a simulation trace.

    Returns:
        A ``Report`` with:
        - ``summary``: high-level status and fidelity proxy.
        - ``error_budget``: dephasing/leakage-like terms in ``[0, 1]``.
    """
    final_p1 = float(observables.values.get("final_p1", 0.0))
    leakage = max(0.0, min(1.0, final_p1 * 0.1))
    dephasing = max(0.0, min(1.0, 1.0 - float(observables.values.get("final_p0", 1.0))))
    return Report(
        summary={"status": "ok", "fidelity_proxy": 1.0 - dephasing},
        error_budget={"dephasing": dephasing, "leakage": leakage},
    )
