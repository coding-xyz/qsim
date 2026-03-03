"""Sensitivity report builders and heatmap export helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

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


def write_sensitivity_heatmap(sensitivity_report: dict, out_path: str | Path) -> Path:
    """Render a compact heatmap for local sensitivity ranking."""
    import matplotlib.pyplot as plt

    local = sensitivity_report.get("local_sensitivity", {}) if isinstance(sensitivity_report, dict) else {}
    labels = list(local.keys())
    values = np.asarray([float(local[k]) for k in labels], dtype=float)
    data = values.reshape(1, max(1, len(values))) if values.size else np.zeros((1, 1), dtype=float)
    xlabels = labels if labels else ["none"]

    fig_w = max(4.0, 1.4 * len(xlabels))
    fig, ax = plt.subplots(figsize=(fig_w, 2.6))
    vmax = float(np.max(data)) if data.size else 1.0
    im = ax.imshow(data, cmap="Greys", aspect="auto", vmin=0.0, vmax=max(vmax, 1e-9))
    ax.set_xticks(np.arange(len(xlabels)))
    ax.set_xticklabels(xlabels, rotation=20, ha="right")
    ax.set_yticks([0])
    ax.set_yticklabels(["sensitivity"])
    ax.set_title("Sensitivity Heatmap")

    for col, value in enumerate(data[0]):
        ax.text(col, 0, f"{float(value):.3f}", ha="center", va="center", color="black", fontsize=8)

    fig.colorbar(im, ax=ax, fraction=0.05, pad=0.06, label="sensitivity")
    fig.tight_layout()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out
