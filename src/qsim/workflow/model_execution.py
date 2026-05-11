"""Execution logic for workflow models."""

from __future__ import annotations

import time
import numpy as np
from dataclasses import asdict
from typing import Any
from pathlib import Path

from qsim.workflow.contracts import (
    DefaultAnalyserConfig,
    WorkflowDeviceConfig,
    WorkflowSolverConfig,
    WorkflowTask,
    compose_workflow_task,
)
from qsim.workflow.output import resolve_writable_out_dir
from qsim.workflow.planner import build_execution_plan
from qsim.workflow.stages import (
    parse_compile_lower_model,
    run_analysis_stage,
    run_decode_stage,
    run_engine_stage,
)
from qsim.schemas.results import AnalysisScope, ModelAnalysis, RunProvenance, RunResult
from qsim.schemas.model import RunStatus, RunIdentity, ModelRun, RunArtifacts

from qsim.workflow.model_utils import (
    compact_runtime_details,
    public_value,
    safe_study_token,
    study_name,
    effective_analyser_payload,
    require_solver_id,
    require_analyser_id,
    format_study_id,
)

def get_study_entries(solver_cfg: WorkflowSolverConfig) -> list[tuple[int | None, dict[str, Any]]]:
    entries = [dict(step) for step in list(solver_cfg.study or []) if isinstance(step, dict)]
    if not entries:
        return [(None, {})]
    return [(idx, step) for idx, step in enumerate(entries)]

def clone_solver_cfg_with_single_study(
    solver_cfg: WorkflowSolverConfig,
    *,
    study: dict[str, Any],
) -> WorkflowSolverConfig:
    return WorkflowSolverConfig(
        backend=type(solver_cfg.backend)(**asdict(solver_cfg.backend)),
        run=type(solver_cfg.run)(**asdict(solver_cfg.run)),
        frame=type(solver_cfg.frame)(**asdict(solver_cfg.frame)),
        study=[dict(study)] if study else None,
    )

def find_run_id(
    model: Any,
    *,
    solver_id: str,
    study_name_val: str | None = None,
) -> str | None:
    candidates: list[tuple[str, ModelRun]] = [
        (run_id, run_obj)
        for run_id, run_obj in model.runs.items()
        if run_obj.identity.solver_id == solver_id and run_obj.result and run_obj.result.trajectory is not None
    ]
    if study_name_val is None:
        if len(candidates) == 1:
            return candidates[0][0]
        return None
    wanted = str(study_name_val).strip()
    for run_id, run_obj in candidates:
        if str(run_obj.identity.study_name or '').strip() == wanted:
            return run_id
    return None

def _nearest_centroid(point: complex, centroids: dict[str, complex]) -> str:
    if not centroids:
        return ""
    return min(centroids, key=lambda label: abs(point - centroids[label]))

def _get_study_label(bundle: Any, analysis: ModelAnalysis) -> str | None:
    study_name_val = str(bundle.identity.study_name or "").strip()
    if study_name_val:
        return study_name_val

    runtime_task = bundle.runtime_task
    if runtime_task is not None:
        task_input = getattr(runtime_task, "input", None)
        study_steps = list(getattr(task_input, "study", []) or []) if task_input is not None else []
        if study_steps:
            prep_state = dict(study_steps[0].get("prep_state", {}) or {})
            prep_label = str(prep_state.get("label", "") or "").strip()
            if prep_label:
                return prep_label
    
    iq_output = analysis.output.iq
    if iq_output:
        iq_payload = iq_output if isinstance(iq_output, dict) else asdict(iq_output)
        cm = iq_payload.get("confusion_matrix", {})
        labels = list(cm.get("labels", []) or [])
        if labels:
            return str(labels[0]).strip()
    
    return None

def build_multi_study_iq_summary(model: Any, analysis_items: list[tuple[Any, ModelAnalysis]]) -> dict[str, Any] | None:
    if len(analysis_items) <= 1:
        return None
    centroids: dict[str, complex] = {}
    clouds: dict[str, list[list[float]]] = {}
    study_map: dict[str, str] = {}
    noise_sigmas: list[float] = []
    for bundle, analysis in analysis_items:
        iq_output = analysis.output.iq
        if not iq_output:
            continue
        iq_payload = iq_output if isinstance(iq_output, dict) else asdict(iq_output)
        label = _get_study_label(bundle, analysis)
        if not label:
            continue
        centroid_map = dict(iq_payload.get('centroids', {}) or {})
        centroid_raw = None
        if label in centroid_map:
            centroid_raw = centroid_map.get(label)
        elif centroid_map:
            centroid_raw = next(iter(centroid_map.values()))
        
        if centroid_raw is None:
            centroids[label] = complex(0.0, 0.0)
            continue
        
        try:
            raw_val = np.asarray(centroid_raw)
            if raw_val.size < 2:
                centroids[label] = complex(0.0, 0.0)
                continue
            centroids[label] = complex(float(raw_val[0]), float(raw_val[1]))
        except (TypeError, ValueError, IndexError):
            centroids[label] = complex(0.0, 0.0)
            continue
        cloud_source = dict(iq_payload.get('synthetic_clouds', {}) or {})
        raw_cloud = cloud_source.get(label)
        if raw_cloud is None and cloud_source:
            raw_cloud = next(iter(cloud_source.values()))
        clouds[label] = [
            [float(point[0]), float(point[1])]
            for point in list(raw_cloud or [])
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        study_map[label] = str(bundle.identity.study_name or '')
        try:
            noise_sigmas.append(float(iq_payload.get('noise_sigma', 0.0) or 0.0))
        except Exception:
            pass
    labels = list(centroids.keys())
    if not labels:
        return None
    confusion = np.zeros((len(labels), len(labels)), dtype=int)
    for i, label in enumerate(labels):
        for point_raw in clouds.get(label, []):
            point = complex(float(point_raw[0]), float(point_raw[1]))
            pred = _nearest_centroid(point, centroids)
            if pred in labels:
                confusion[i, labels.index(pred)] += 1
    assignment_fidelity = float(np.trace(confusion) / max(1, confusion.sum())) if confusion.size else 0.0
    pairwise_distances = [
        abs(centroids[a] - centroids[b])
        for i, a in enumerate(labels)
        for b in labels[i + 1 :]
    ]
    noise_sigma = float(np.mean(noise_sigmas)) if noise_sigmas else 0.0
    cluster_separation = float(min(pairwise_distances) / max(noise_sigma, 1.0e-12)) if pairwise_distances else 0.0
    snr = float((np.mean(pairwise_distances) if pairwise_distances else 0.0) / max(2.0 * noise_sigma, 1.0e-12))
    return {
        "schema_version": "1.0",
        "labels": labels,
        "centroids": {label: [float(val.real), float(val.imag)] for label, val in centroids.items()},
        "synthetic_clouds": clouds,
        "confusion_matrix": {"labels": labels, "values": confusion.astype(int).tolist()},
        "assignment_fidelity": assignment_fidelity,
        "cluster_separation": cluster_separation,
        "snr": snr,
        "study_map": study_map,
    }

def compose_runtime_task(
    model: Any,
    *,
    solver_cfg: WorkflowSolverConfig,
    analyser_cfg: DefaultAnalyserConfig | None,
) -> WorkflowTask:
    # Use a clean DeviceConfig container for the builder
    device_cfg = WorkflowDeviceConfig(
        device=model.device.device,
        pulse=model.device.pulse,
        noise=model.device.noise,
    )
    
    return compose_workflow_task(
        task_cfg=model.task,
        solver_cfg=solver_cfg,
        device_cfg=device_cfg,
        analyser_cfg=analyser_cfg,
        model_pulse=model.pulse,
        backend_source=model.task.input.solver_config_path,
    )

def run_one_solver_study(
    model: Any,
    *,
    solver_id: str,
    solver_cfg: WorkflowSolverConfig,
    study: dict[str, Any],
    study_index: int | None,
    total_studies: int,
) -> str:
    selected_solver_id = require_solver_id(model, solver_id)
    default_analyser = None
    if model.analysers:
        bound = [cfg for cfg in model.analysers.values() if str(cfg.solver_id or '').strip() == selected_solver_id]
        default_analyser = bound[0] if bound else None
    single_solver_cfg = clone_solver_cfg_with_single_study(solver_cfg, study=study)
    task = compose_runtime_task(model, solver_cfg=single_solver_cfg, analyser_cfg=default_analyser)
    run_id = format_study_id(
        selected_solver_id,
        study=study,
        study_index=study_index,
        total_studies=total_studies,
    )
    study_name_val = study_name(study, study_index)

    run_started_at = time.perf_counter()
    timings: dict[str, float] = {}
    preferred_out = Path(task.output.out_dir)
    if total_studies > 1 and study_name_val:
        preferred_out = preferred_out / safe_study_token(study_name_val)
    out = resolve_writable_out_dir(preferred_out)
    model.out_dir = str(out)
    plan = build_execution_plan(task)

    started_at = time.perf_counter()
    parsed = parse_compile_lower_model(
        qasm_text=task.input.qasm_text,
        backend_path=task.input.backend_path,
        backend_config=task.input.backend_config,
        out=out,
        device=(task.input.device_model or task.input.device),
        pulse=task.input.pulse,
        frame=task.input.frame,
        analyser=task.input.analyser,
        study=task.input.study,
        schedule_policy=task.input.schedule_policy,
        reset_feedback_policy=task.input.reset_feedback_policy,
        noise=task.input.noise,
        solver_run={
            'dt_s': task.run.dt_s,
            't_end_s': task.run.t_end_s,
            't_padding_s': task.run.t_padding_s,
            'seed': task.run.seed,
            'ntraj': task.run.mcwf_ntraj,
            'qutip_options': task.run.qutip_options,
            'native_options': task.run.native_options,
            'backend_options': task.run.backend_options,
            'one_over_f_components': task.run.one_over_f_components,
        },
        solver_mode=task.run.solver_mode,
        param_bindings=task.input.param_bindings,
        persist_artifacts=task.output.persist_artifacts,
    )
    timings.update(parsed.get('timings', {}))
    timings['build'] = time.perf_counter() - started_at

    started_at = time.perf_counter()
    trajectory = run_engine_stage(
        model_spec=parsed['model_spec'],
        cfg=parsed['cfg'],
        engine=task.run.engine,
        allow_mock_fallback=task.run.allow_mock_fallback,
        julia_bin=task.run.julia_bin,
        julia_depot_path=task.run.julia_depot_path,
        julia_timeout_s=task.run.julia_timeout_s,
        mcwf_ntraj=task.run.mcwf_ntraj,
    )
    timings['solver'] = time.perf_counter() - started_at

    decoded = {
        'logical_error': None,
        'decoder_input': None,
        'decoder_output': None,
        'decoder_report': None,
        'prior_model': None,
        'prior_report': None,
        'syndrome': None,
    }
    if plan.run_decode:
        started_at = time.perf_counter()
        decoded = run_decode_stage(
            trajectory=trajectory,
            circuit=parsed['circuit'],
            model_spec=parsed['model_spec'],
            engine=task.run.engine,
            cfg=parsed['cfg'],
            prior_backend=task.run.prior_backend,
            decoder=task.run.decoder,
            decoder_options=task.run.decoder_options,
        )
        timings['decode'] = time.perf_counter() - started_at

    timings['total'] = time.perf_counter() - run_started_at
    
    # Initialize ModelRun as RUNNING
    run_obj = ModelRun(
        identity=RunIdentity(
            run_id=run_id,
            solver_id=selected_solver_id,
            study_name=study_name_val,
            study_index=study_index,
        ),
        runtime_task=task,
        status=RunStatus.RUNNING,
        started_at=time.time(),
    )
    model.runs[run_id] = run_obj

    try:
        provenance = RunProvenance(
            solver_id=selected_solver_id,
            study_name=study_name_val,
            study_index=study_index,
            spec_ref=None, 
            plan_ref=None, 
        )
        
        runtime_metadata = {
            'engine_requested': task.run.engine,
            'engine_used': trajectory.engine,
            'solver_mode': str(task.run.solver_mode or parsed['model_spec'].solver),
            'targets': list(plan.targets),
            'template': str(plan.template),
            'details': compact_runtime_details(dict(trajectory.metadata or {}).get('details', {})),
            'out_dir': str(out),
        }
        
        run_obj.artifacts = RunArtifacts(
            circuit=parsed['circuit'],
            normalized_circuit=parsed['normalized'],
            model_spec=parsed['model_spec'],
            pulse_ir=parsed['pulse_ir'],
            executable_model=parsed['executable'],
            compile_report=public_value(parsed['compile_report']),
            decoder_outputs=decoded,
            timings=timings,
        )
        run_obj.result = RunResult(
            result_id=run_id,
            trajectory=trajectory,
            provenance=provenance,
            runtime_metadata=runtime_metadata,
        )
        run_obj.status = RunStatus.COMPLETED
    except Exception as e:
        run_obj.status = RunStatus.FAILED
        run_obj.error = str(e)
        raise e
    finally:
        run_obj.finished_at = time.time()

    return run_id

def run_study(
    model: Any,
    *,
    solver_id: str | None = None,
    study_name_val: str | None = None,
    study_index: int | None = None,
) -> str:
    selected_solver_id = require_solver_id(model, solver_id)
    solver_cfg = model.solvers[selected_solver_id]
    entries = get_study_entries(solver_cfg)
    chosen_index: int | None = None
    chosen_study: dict[str, Any] | None = None
    if study_name_val is not None:
        wanted = str(study_name_val).strip()
        for idx, step in entries:
            if str(study_name(step, idx) or '').strip() == wanted:
                chosen_index = idx
                chosen_study = dict(step)
                break
        if chosen_study is None:
            raise KeyError(f'Unknown study `{wanted}` for solver `{selected_solver_id}`.')
    elif study_index is not None:
        for idx, step in entries:
            if idx == study_index:
                chosen_index = idx
                chosen_study = dict(step)
                break
        if chosen_study is None:
            raise IndexError(f'Unknown study index `{study_index}` for solver `{selected_solver_id}`.')
    else:
        if len(entries) != 1:
            raise ValueError(f'study_name or study_index is required for solver `{selected_solver_id}` with multiple study steps.')
        chosen_index, chosen_study = entries[0]
    assert chosen_study is not None
    run_id = format_study_id(
        selected_solver_id,
        study=chosen_study,
        study_index=chosen_index,
        total_studies=len(entries),
    )
    model.runs.pop(run_id, None)
    return run_one_solver_study(
        model,
        solver_id=selected_solver_id,
        solver_cfg=solver_cfg,
        study=chosen_study,
        study_index=chosen_index,
        total_studies=len(entries),
    )

def run_solver(model: Any, solver_id: str | None = None) -> None:
    selected_solver_id = require_solver_id(model, solver_id)
    solver_cfg = model.solvers[selected_solver_id]
    
    for run_id in list(model.runs.keys()):
        run_obj = model.runs[run_id]
        if run_obj.identity.solver_id == selected_solver_id:
            model.runs.pop(run_id, None)
            
    entries = get_study_entries(solver_cfg)
    for idx, step in entries:
        run_one_solver_study(
            model,
            solver_id=selected_solver_id,
            solver_cfg=solver_cfg,
            study=dict(step),
            study_index=idx,
            total_studies=len(entries),
        )

def run_analysis(model: Any, *, analyser_id: str | None = None, study_name_val: str | None = None) -> None:
    selected_analyser_id = require_analyser_id(model, analyser_id)
    analyser_cfg = model.analysers[selected_analyser_id]
    selected_solver_id = require_solver_id(model, analyser_cfg.solver_id)
    matching_runs = [
        (run_id, run_obj)
        for run_id, run_obj in model.runs.items()
        if run_obj.identity.solver_id == selected_solver_id and run_obj.result and run_obj.result.trajectory is not None
    ]
    if study_name_val is not None:
        matching_runs = [
            (run_id, run_obj)
            for run_id, run_obj in matching_runs
            if str(run_obj.identity.study_name or '').strip() == str(study_name_val).strip()
        ]
    if not matching_runs:
        raise ValueError(f'Solver `{selected_solver_id}` has not been run yet.')

    per_study_analyses: list[tuple[Any, ModelAnalysis]] = []
    total_studies = len(matching_runs)
    for run_id, solver_run in matching_runs:
        cfg = getattr(solver_run.runtime_task, 'input', None).backend_config if solver_run.runtime_task else None
        if cfg is None:
            raise ValueError(f'Missing runtime task/backend config for solver `{selected_solver_id}`.')
        logical_error = None
        decoder_outputs = solver_run.artifacts.decoder_outputs
        if decoder_outputs:
            logical_error = decoder_outputs.get('logical_error')

        started_at = time.perf_counter()
        from qsim.workflow.contracts import build_effective_pulse_config
        
        analyzed = run_analysis_stage(
            trajectory=solver_run.result.trajectory,
            model_spec=solver_run.artifacts.model_spec,
            pulse_ir=solver_run.artifacts.pulse_ir,
            pulse_cfg=build_effective_pulse_config(model.device, model.pulse),
            cfg=cfg,
            logical_error=logical_error,
            analyser_cfg=analyser_cfg.to_payload(),
            metric_registry=model.metric_registry,
        )
        
        output = analyzed.get('analysis')
        
        analysis_run_id = format_study_id(
            selected_analyser_id,
            study={"name": solver_run.identity.study_name} if solver_run.identity.study_name else {},
            study_index=solver_run.identity.study_index,
            total_studies=total_studies,
        )
        
        analysis_result = ModelAnalysis(
            analysis_id=analysis_run_id,
            analyser_id=selected_analyser_id,
            input_run_ids=[run_id],
            scope=AnalysisScope.SINGLE_RUN,
            output=output,
        )
        model.analyses[analysis_run_id] = analysis_result
        per_study_analyses.append((solver_run, analysis_result))
        
        # Update timings in artifacts, not in result metadata
        if solver_run.artifacts:
            solver_run.artifacts.timings[f'analysis:{selected_analyser_id}'] = time.perf_counter() - started_at

    if study_name_val is None:
        if total_studies == 1:
            model.analyses[selected_analyser_id] = per_study_analyses[0][1]
        else:
            summary_iq_payload = build_multi_study_iq_summary(model, per_study_analyses)
            if summary_iq_payload is not None:
                from qsim.schemas.results import AnalysisOutput, IQAnalysis
                iq_analysis = IQAnalysis(
                    centroids={k: complex(*v) for k, v in summary_iq_payload.get('centroids', {}).items()},
                    confusion_matrix=summary_iq_payload.get('confusion_matrix'),
                    assignment_fidelity=summary_iq_payload.get('assignment_fidelity', 0.0),
                    noise_sigma=summary_iq_payload.get('noise_sigma', 0.0),
                    snr=summary_iq_payload.get('snr', 0.0),
                )
                model.analyses[selected_analyser_id] = ModelAnalysis(
                    analysis_id=selected_analyser_id,
                    analyser_id=selected_analyser_id,
                    input_run_ids=[r.identity.run_id for r, a in per_study_analyses],
                    scope=AnalysisScope.STUDY_SUMMARY,
                    output=AnalysisOutput(iq=iq_analysis),
                )
            else:
                model.analyses[selected_analyser_id] = per_study_analyses[0][1]

def run_all(model: Any) -> None:
    for solver_id in sorted(model.solvers.keys()):
        run_solver(model, solver_id)
    for analyser_id in sorted(model.analysers.keys()):
        run_analysis(model, analyser_id=analyser_id)

def run(model: Any) -> None:
    run_all(model)