"""Optional workflow plugin branches."""

from __future__ import annotations

from qsim.analysis.error_budget_pauli import build_component_budget
from qsim.analysis.pauli_plus import build_component_error_model, run_scaling_sweep
from qsim.qec.eval import run_decoder_eval
from qsim.workflow.engines import run_cross_engine_compare


def run_decoder_eval_plugin(
    *,
    enabled: bool,
    decoder_input,
    out,
    cfg_seed: int,
    decoder: str,
    eval_decoders: list[str] | None,
    eval_seeds: list[int] | None,
    eval_option_grid: list[dict] | None,
    eval_parallelism: int,
    eval_retries: int,
    eval_resume: bool,
):
    """Run optional decoder benchmark sweep branch."""
    if not enabled:
        return {
            "decoder_eval_report": None,
            "decoder_eval_rows": [],
            "decoder_eval_batch_manifest": None,
            "failed_eval_tasks": [],
            "decoder_eval_resume_state": None,
            "decoder_eval_table_rel": "",
        }

    requested_decoders = eval_decoders or [decoder, "bp"]
    seen: set[str] = set()
    decs = [d for d in requested_decoders if not (d in seen or seen.add(d))]
    seeds = eval_seeds or [int(cfg_seed)]
    resume_path = out / "resume_state.json"
    (
        decoder_eval_report,
        decoder_eval_rows,
        decoder_eval_batch_manifest,
        failed_eval_tasks,
        decoder_eval_resume_state,
    ) = run_decoder_eval(
        decoder_input,
        decoders=decs,
        seeds=[int(s) for s in seeds],
        option_grid=eval_option_grid,
        parallelism=int(max(1, eval_parallelism)),
        retries=int(max(0, eval_retries)),
        resume=bool(eval_resume),
        resume_state_path=resume_path,
    )
    return {
        "decoder_eval_report": decoder_eval_report,
        "decoder_eval_rows": decoder_eval_rows,
        "decoder_eval_batch_manifest": decoder_eval_batch_manifest,
        "failed_eval_tasks": failed_eval_tasks,
        "decoder_eval_resume_state": decoder_eval_resume_state,
        "decoder_eval_table_rel": "",
    }


def run_pauli_plus_plugin(
    *,
    enabled: bool,
    logical_error_obj,
    observables_obj,
    qec_engine: str,
    pauli_plus_code_distances: list[int] | None,
    pauli_plus_shots: int,
    cfg_seed: int,
):
    """Run optional Pauli+ scaling and component budget branch."""
    if not enabled:
        return {
            "scaling_report": None,
            "error_budget_pauli_plus": None,
            "component_model": None,
            "component_ablation_rel": "",
        }

    component_model = build_component_error_model(
        logical_x=float(logical_error_obj.logical_x),
        logical_z=float(logical_error_obj.logical_z),
        mean_excited=float(observables_obj.values.get("mean_excited", 0.0)),
        final_p1=float(observables_obj.values.get("final_p1", 0.0)),
    )
    dists = [int(d) for d in (pauli_plus_code_distances or [3, 5])]
    scaling_report = run_scaling_sweep(
        qec_engine=qec_engine,
        component_errors=component_model,
        code_distances=dists,
        shots=int(max(1, pauli_plus_shots)),
        seed=int(cfg_seed),
        options={"error_scale": 1.0, "mode": "baseline"},
    )
    ablation_scaling: dict[str, dict] = {}
    for comp in sorted(component_model.keys()):
        ablated = dict(component_model)
        ablated[comp] = 0.0
        ablation_scaling[comp] = run_scaling_sweep(
            qec_engine=qec_engine,
            component_errors=ablated,
            code_distances=dists,
            shots=int(max(1, pauli_plus_shots)),
            seed=int(cfg_seed),
            options={"error_scale": 1.0, "mode": "component_off", "component": comp},
        )
    scaling_report["ablation_mode"] = "component_off"
    scaling_report["components"] = sorted(component_model.keys())
    error_budget_pauli_plus = build_component_budget(
        baseline_scaling=scaling_report,
        component_model=component_model,
        ablation_scaling=ablation_scaling,
    )
    return {
        "scaling_report": scaling_report,
        "error_budget_pauli_plus": error_budget_pauli_plus,
        "component_model": component_model,
        "component_ablation_rel": "",
    }


def run_cross_engine_compare_plugin(
    *,
    compare_engines: list[str] | None,
    model_spec,
    engine: str,
    cfg_seed: int,
    allow_mock_fallback: bool,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
):
    """Run optional cross-engine compare branch."""
    if not compare_engines:
        return None
    return run_cross_engine_compare(
        model_spec,
        engines=[engine, *list(compare_engines)],
        seed=int(cfg_seed),
        allow_mock_fallback=bool(allow_mock_fallback),
        julia_bin=julia_bin,
        julia_depot_path=julia_depot_path,
        julia_timeout_s=float(julia_timeout_s),
        mcwf_ntraj=int(max(1, mcwf_ntraj)),
    )


__all__ = [
    "run_cross_engine_compare_plugin",
    "run_decoder_eval_plugin",
    "run_pauli_plus_plugin",
]
