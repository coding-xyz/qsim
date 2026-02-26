from __future__ import annotations

from qsim.common.schemas import LogicalErrorSummary, Observables


def build_sensitivity_report(
    observables: Observables,
    logical_error: LogicalErrorSummary,
    *,
    seed: int,
    sweep: list[dict] | None = None,
) -> dict:
    """Build deterministic sensitivity summary for P1-M4.

    This version uses a stable proxy model to estimate local sensitivities
    from current run metrics. It favors reproducibility over physical
    completeness and is suited for ranking and regression tracking.

    Args:
        observables: Aggregated observables from simulation outputs.
        logical_error: Logical error summary from decoder outputs.
        seed: Run seed recorded for reproducibility.
        sweep: Optional declared sweep configuration from backend settings.

    Returns:
        A JSON-serializable dict with baseline metrics, local sensitivities,
        ranking, and declared sweep dimensions.
    """
    mean_excited = float(observables.values.get("mean_excited", 0.0))
    final_p1 = float(observables.values.get("final_p1", 0.0))
    lx = float(logical_error.logical_x)
    lz = float(logical_error.logical_z)

    # Deterministic local slopes (proxy model) to support ranking and monitoring.
    local = {
        "gamma1": max(0.0, 0.6 * lx + 0.2 * mean_excited),
        "gamma_phi": max(0.0, 0.7 * lz + 0.1 * final_p1),
        "readout_error": max(0.0, 0.4 * (lx + lz)),
        "crosstalk": max(0.0, 0.3 * mean_excited + 0.2 * final_p1),
    }
    ranking = sorted(
        [{"parameter": k, "sensitivity": v} for k, v in local.items()],
        key=lambda x: x["sensitivity"],
        reverse=True,
    )

    declared_dims: list[str] = []
    if sweep:
        for item in sweep:
            if isinstance(item, dict):
                declared_dims.extend(str(k) for k in item.keys())

    return {
        "schema_version": "1.0",
        "status": "ok",
        "seed": int(seed),
        "baseline": {
            "logical_x": lx,
            "logical_z": lz,
            "mean_excited": mean_excited,
            "final_p1": final_p1,
        },
        "local_sensitivity": local,
        "ranking": ranking,
        "declared_sweep_dims": sorted(set(declared_dims)),
    }


def build_error_budget_v2(
    observables: Observables,
    logical_error: LogicalErrorSummary,
    sensitivity_report: dict,
) -> dict:
    """Build an expanded error budget from sensitivity/logical-error metrics.

    Args:
        observables: Observables used for readout-like proxy terms.
        logical_error: Logical error summary used for base rates.
        sensitivity_report: Output from ``build_sensitivity_report``.

    Returns:
        A JSON-serializable v2 error budget with ranked contribution terms.
    """
    lx = float(logical_error.logical_x)
    lz = float(logical_error.logical_z)
    final_p1 = float(observables.values.get("final_p1", 0.0))
    sens = sensitivity_report.get("local_sensitivity", {}) if isinstance(sensitivity_report, dict) else {}

    terms = {
        "dephasing_like": max(0.0, min(1.0, 0.6 * lz + 0.1 * float(sens.get("gamma_phi", 0.0)))),
        "relaxation_like": max(0.0, min(1.0, 0.6 * lx + 0.1 * float(sens.get("gamma1", 0.0)))),
        "readout_like": max(0.0, min(1.0, 0.3 * final_p1 + 0.1 * float(sens.get("readout_error", 0.0)))),
        "crosstalk_like": max(0.0, min(1.0, 0.1 * float(sens.get("crosstalk", 0.0)))),
    }
    ranking = sorted(
        [{"term": k, "value": v} for k, v in terms.items()],
        key=lambda x: x["value"],
        reverse=True,
    )

    return {
        "schema_version": "1.0",
        "status": "ok",
        "terms": terms,
        "ranking": ranking,
        "notes": "P1-M4 proxy budget; intended for relative comparison and regression tracking.",
    }
