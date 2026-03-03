"""Pauli-plus error-budget aggregation and ablation export helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def build_component_budget(
    *,
    baseline_scaling: dict[str, Any],
    component_model: dict[str, float],
    ablation_scaling: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build Pauli+ component error budget from baseline vs component-off ablations.

    Contribution for each component is defined as:
    ``delta_inverse_lambda = (1/lambda_baseline) - (1/lambda_component_off)``.
    """
    lam = float(baseline_scaling.get("lambda_3_5", 0.0))
    inv_baseline = (1.0 / lam) if lam > 1e-12 else 0.0
    contributions: dict[str, float] = {}
    ablations: dict[str, dict[str, float]] = {}
    for k in sorted(component_model.keys()):
        ab = ablation_scaling.get(k, {}) if isinstance(ablation_scaling, dict) else {}
        lam_ab = float(ab.get("lambda_3_5", 0.0))
        inv_ab = (1.0 / lam_ab) if lam_ab > 1e-12 else 0.0
        delta = max(0.0, inv_baseline - inv_ab)
        contributions[k] = float(delta)
        ablations[k] = {
            "lambda_3_5_component_off": lam_ab,
            "inverse_lambda_component_off": inv_ab,
            "delta_inverse_lambda": delta,
            "epsilon_3_component_off": float(ab.get("epsilon_3", 0.0)),
            "epsilon_5_component_off": float(ab.get("epsilon_5", 0.0)),
        }
    ranking = sorted(
        [{"component": k, "contribution": v} for k, v in contributions.items()],
        key=lambda x: x["contribution"],
        reverse=True,
    )
    return {
        "schema_version": "1.0",
        "status": "ok",
        "metric": "inverse_lambda_3_5",
        "lambda_3_5": lam,
        "inverse_lambda_3_5": inv_baseline,
        "contributions": contributions,
        "ablations": ablations,
        "ranking": ranking,
        "notes": "M3 ablation budget: contribution is delta(1/lambda_3_5) between baseline and component-off runs.",
    }


def write_component_ablation_csv(
    *,
    component_model: dict[str, float],
    budget: dict[str, Any],
    out_path: str | Path,
) -> Path:
    """Write component-level ablation table for quick inspection/export."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    contrib = budget.get("contributions", {}) if isinstance(budget, dict) else {}
    ablations = budget.get("ablations", {}) if isinstance(budget, dict) else {}
    headers = [
        "component",
        "base_error",
        "contribution",
        "lambda_3_5_component_off",
        "inverse_lambda_component_off",
        "delta_inverse_lambda",
        "epsilon_3_component_off",
        "epsilon_5_component_off",
    ]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for k in sorted(component_model.keys()):
            w.writerow(
                {
                    "component": k,
                    "base_error": float(component_model.get(k, 0.0)),
                    "contribution": float(contrib.get(k, 0.0)),
                    "lambda_3_5_component_off": float((ablations.get(k, {}) or {}).get("lambda_3_5_component_off", 0.0)),
                    "inverse_lambda_component_off": float((ablations.get(k, {}) or {}).get("inverse_lambda_component_off", 0.0)),
                    "delta_inverse_lambda": float((ablations.get(k, {}) or {}).get("delta_inverse_lambda", 0.0)),
                    "epsilon_3_component_off": float((ablations.get(k, {}) or {}).get("epsilon_3_component_off", 0.0)),
                    "epsilon_5_component_off": float((ablations.get(k, {}) or {}).get("epsilon_5_component_off", 0.0)),
                }
            )
    return out
