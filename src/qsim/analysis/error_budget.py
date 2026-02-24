from __future__ import annotations

from qsim.common.schemas import Observables, Report


def build_report(observables: Observables) -> Report:
    """Build a lightweight error-budget report from observables."""
    final_p1 = float(observables.values.get("final_p1", 0.0))
    leakage = max(0.0, min(1.0, final_p1 * 0.1))
    dephasing = max(0.0, min(1.0, 1.0 - float(observables.values.get("final_p0", 1.0))))
    return Report(
        summary={"status": "ok", "fidelity_proxy": 1.0 - dephasing},
        error_budget={"dephasing": dephasing, "leakage": leakage},
    )
