"""Workflow pipeline implementation and artifact export helpers."""

from __future__ import annotations

from pathlib import Path
import time

from qsim.common.schemas import write_json
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trace
from qsim.workflow.contracts import (
    WorkflowDeviceConfig,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
)
from qsim.workflow.output import build_settings_report, resolve_writable_out_dir
from qsim.workflow.persistence import (
    ArtifactPayload,
    ArtifactWritePolicy,
    build_manifest,
    export_visualizations,
    gather_dependencies,
    write_artifacts,
)
from qsim.workflow.planner import ExecutionPlan, build_execution_plan
from qsim.workflow.plugins import run_cross_engine_compare_plugin, run_decoder_eval_plugin, run_pauli_plus_plugin
from qsim.workflow.session_adapter import commit_result_to_session
from qsim.workflow.stages import parse_compile_lower_model, run_analysis_stage, run_decode_stage, run_engine_stage
from qsim.workflow.task_io import (
    load_config_bundle_files,
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
)


def _tick(timings: dict[str, float], stage: str, started_at: float) -> None:
    timings[stage] = time.perf_counter() - started_at


def _run_core_stages(*, task: WorkflowTask, out: Path, timings: dict[str, float], plan: ExecutionPlan) -> dict:
    parsed = parse_compile_lower_model(
        qasm_text=task.input.qasm_text,
        backend_path=task.input.backend_path,
        backend_config=task.input.backend_config,
        out=out,
        device=task.input.device,
        pulse=task.input.pulse,
        frame=task.input.frame,
        schedule_policy=task.input.schedule_policy,
        reset_feedback_policy=task.input.reset_feedback_policy,
        noise=task.input.noise,
        solver_run={
            "dt_s": task.run.dt_s,
            "t_end_s": task.run.t_end_s,
            "t_padding_s": task.run.t_padding_s,
        },
        solver_mode=task.run.solver_mode,
        param_bindings=task.input.param_bindings,
        persist_artifacts=task.output.persist_artifacts,
    )
    timings.update(parsed["timings"])

    started_at = time.perf_counter()
    trace = run_engine_stage(
        model_spec=parsed["model_spec"],
        cfg=parsed["cfg"],
        engine=task.run.engine,
        allow_mock_fallback=task.run.allow_mock_fallback,
        julia_bin=task.run.julia_bin,
        julia_depot_path=task.run.julia_depot_path,
        julia_timeout_s=task.run.julia_timeout_s,
        mcwf_ntraj=task.run.mcwf_ntraj,
    )
    _tick(timings, "engine_run", started_at)

    decoded = {
        "syndrome": None,
        "prior_model": None,
        "prior_report": None,
        "decoder_input": None,
        "decoder_output": None,
        "decoder_report": None,
        "logical_error": None,
    }
    if plan.run_decode:
        started_at = time.perf_counter()
        decoded = run_decode_stage(
            trace=trace,
            circuit=parsed["circuit"],
            model_spec=parsed["model_spec"],
            engine=task.run.engine,
            cfg=parsed["cfg"],
            prior_backend=task.run.prior_backend,
            decoder=task.run.decoder,
            decoder_options=task.run.decoder_options,
        )
        _tick(timings, "decode_run", started_at)

    analyzed = {
        "analysis": {},
        "observables_obj": None,
        "logical_error_obj": None,
        "sensitivity_report": None,
        "error_budget_v2": None,
        "timings": {},
    }
    if plan.run_analysis and decoded.get("logical_error") is not None:
        analyzed = run_analysis_stage(
            trace=trace,
            model_spec=parsed["model_spec"],
            cfg=parsed["cfg"],
            logical_error=decoded["logical_error"],
        )
        timings.update(analyzed["timings"])

    return {"parsed": parsed, "trace": trace, "decoded": decoded, "analyzed": analyzed}


def _run_optional_branches(
    *,
    task: WorkflowTask,
    out: Path,
    core_ctx: dict,
    timings: dict[str, float],
    plan: ExecutionPlan,
) -> dict:
    cfg_seed = int(core_ctx["parsed"]["cfg"].seed)
    decoded = core_ctx["decoded"]
    analyzed = core_ctx["analyzed"]

    decoder_eval_payload = {
        "decoder_eval_report": None,
        "decoder_eval_rows": [],
        "decoder_eval_batch_manifest": None,
        "failed_eval_tasks": [],
        "decoder_eval_resume_state": None,
        "decoder_eval_table_rel": "",
    }
    if plan.run_decoder_eval and decoded.get("decoder_input") is not None:
        started_at = time.perf_counter()
        decoder_eval_payload = run_decoder_eval_plugin(
            enabled=True,
            decoder_input=decoded["decoder_input"],
            out=out,
            cfg_seed=cfg_seed,
            decoder=task.run.decoder,
            eval_decoders=task.features.eval_decoders,
            eval_seeds=task.features.eval_seeds,
            eval_option_grid=task.features.eval_option_grid,
            eval_parallelism=task.features.eval_parallelism,
            eval_retries=task.features.eval_retries,
            eval_resume=task.features.eval_resume,
        )
        _tick(timings, "decoder_eval_run", started_at)

    pauli_plus_payload = {
        "scaling_report": None,
        "error_budget_pauli_plus": None,
        "component_model": None,
        "component_ablation_rel": "",
    }
    if plan.run_pauli_plus and analyzed.get("logical_error_obj") is not None and analyzed.get("observables_obj") is not None:
        started_at = time.perf_counter()
        pauli_plus_payload = run_pauli_plus_plugin(
            enabled=True,
            logical_error_obj=analyzed["logical_error_obj"],
            observables_obj=analyzed["observables_obj"],
            qec_engine=task.run.qec_engine,
            pauli_plus_code_distances=task.features.pauli_plus_code_distances,
            pauli_plus_shots=task.features.pauli_plus_shots,
            cfg_seed=cfg_seed,
        )
        timings["sensitivity_run"] = timings.get("sensitivity_run", 0.0) + (time.perf_counter() - started_at)

    cross_engine_compare = None
    if plan.run_cross_engine_compare:
        started_at = time.perf_counter()
        cross_engine_compare = run_cross_engine_compare_plugin(
            compare_engines=task.run.compare_engines,
            model_spec=core_ctx["parsed"]["model_spec"],
            engine=task.run.engine,
            cfg_seed=cfg_seed,
            allow_mock_fallback=task.run.allow_mock_fallback,
            julia_bin=task.run.julia_bin,
            julia_depot_path=task.run.julia_depot_path,
            julia_timeout_s=task.run.julia_timeout_s,
            mcwf_ntraj=task.run.mcwf_ntraj,
        )
        _tick(timings, "cross_engine_compare", started_at)

    return {
        "decoder_eval_payload": decoder_eval_payload,
        "pauli_plus_payload": pauli_plus_payload,
        "cross_engine_compare": cross_engine_compare,
    }


def _persist_and_finalize(
    *,
    task: WorkflowTask,
    out: Path,
    core_ctx: dict,
    optional_ctx: dict,
    timings: dict[str, float],
    run_started_at: float,
    plan: ExecutionPlan,
) -> dict:
    parsed = core_ctx["parsed"]
    trace = core_ctx["trace"]
    decoded = core_ctx["decoded"]
    analyzed = core_ctx["analyzed"]
    decoder_eval_payload = optional_ctx["decoder_eval_payload"]
    pauli_plus_payload = optional_ctx["pauli_plus_payload"]
    cross_engine_compare = optional_ctx["cross_engine_compare"]

    settings_report = build_settings_report(
        backend_path=(task.input.backend_path or "<inline:solver.backend>"),
        cfg=parsed["cfg"],
        device=parsed["device_cfg"],
        pulse=parsed["pulse_cfg"],
        frame=parsed["frame_cfg"],
        noise=task.input.noise,
        model_spec=parsed["model_spec"],
        trace=trace,
        selected_engine_name=task.run.engine,
        solver_mode=task.run.solver_mode,
        solver_run={
            "dt_s": task.run.dt_s,
            "t_end_s": task.run.t_end_s,
            "t_padding_s": task.run.t_padding_s,
        },
        param_bindings=task.input.param_bindings,
        allow_mock_fallback=task.run.allow_mock_fallback,
        compare_engines=task.run.compare_engines,
        julia_bin=task.run.julia_bin,
        julia_depot_path=task.run.julia_depot_path,
        julia_timeout_s=task.run.julia_timeout_s,
        mcwf_ntraj=task.run.mcwf_ntraj,
    )

    selected_outputs = set(plan.artifact_outputs) if plan.artifact_mode == "targeted" else None
    write_policy = ArtifactWritePolicy(
        persist_artifacts=task.output.persist_artifacts,
        artifact_mode=plan.artifact_mode,
        selected_outputs=selected_outputs,
    )
    artifact_payload = ArtifactPayload(
        core={
            "circuit": parsed["circuit"],
            "backend_config": parsed["cfg"],
            "normalized": parsed["normalized"],
            "compile_report": parsed["compile_report"],
            "pulse_ir": parsed["pulse_ir"],
            "executable_model": parsed["executable"],
            "model_spec": parsed["model_spec"],
            "trace": trace,
            "pulse_samples_rel": str(parsed["pulse_npz"].name),
        },
        qec={
            "syndrome": decoded.get("syndrome"),
            "prior_model": decoded.get("prior_model"),
            "prior_report": decoded.get("prior_report"),
            "prior_samples_rel": "prior_samples.npz",
            "decoder_input": decoded.get("decoder_input"),
            "decoder_output": decoded.get("decoder_output"),
            "decoder_report": decoded.get("decoder_report"),
            "logical_error": decoded.get("logical_error"),
        },
        analysis={
            "analysis": analyzed.get("analysis", {}),
            "sensitivity_report": analyzed.get("sensitivity_report"),
            "error_budget_v2": analyzed.get("error_budget_v2"),
            "settings_report": settings_report,
        },
        optional={
            "pauli_plus_analysis": plan.run_pauli_plus,
            "scaling_report": pauli_plus_payload.get("scaling_report"),
            "error_budget_pauli_plus": pauli_plus_payload.get("error_budget_pauli_plus"),
            "component_model": pauli_plus_payload.get("component_model"),
            "decoder_eval": plan.run_decoder_eval,
            "decoder_eval_report": decoder_eval_payload.get("decoder_eval_report"),
            "decoder_eval_rows": decoder_eval_payload.get("decoder_eval_rows", []),
            "decoder_eval_batch_manifest": decoder_eval_payload.get("decoder_eval_batch_manifest"),
            "decoder_eval_resume_state": decoder_eval_payload.get("decoder_eval_resume_state"),
            "failed_eval_tasks": decoder_eval_payload.get("failed_eval_tasks", []),
            "cross_engine_compare": cross_engine_compare,
        },
    )

    started_at = time.perf_counter()
    write_report = write_artifacts(out=out, policy=write_policy, payload=artifact_payload)
    _tick(timings, "artifact_write", started_at)

    started_at = time.perf_counter()
    viz_outputs = export_visualizations(
        out=out,
        policy=write_policy,
        export_plots=task.output.export_plots,
        export_dxf=task.output.export_dxf,
        circuit=parsed["circuit"],
        pulse_ir=parsed["pulse_ir"],
        trace=trace,
        analysis=dict(analyzed.get("analysis", {}) or {}),
    )
    _tick(timings, "viz_export", started_at)

    outputs_map = dict(write_report.outputs)
    outputs_map.update(viz_outputs)

    session_commit_report = None
    session_commit_report_rel = ""
    started_at = time.perf_counter()
    if task.output.session_auto_commit and task.output.session_dir:
        session_payload = {
            "settings": settings_report,
            "timings": timings,
            "logical_error": decoded.get("logical_error"),
            "decoder_report": decoded.get("decoder_report"),
            "sensitivity_report": analyzed.get("sensitivity_report"),
            "error_budget_v2": analyzed.get("error_budget_v2"),
            "analysis": analyzed.get("analysis"),
            "cross_engine_compare": cross_engine_compare,
            "decoder_eval_report": decoder_eval_payload.get("decoder_eval_report"),
            "scaling_report": pauli_plus_payload.get("scaling_report"),
            "error_budget_pauli_plus": pauli_plus_payload.get("error_budget_pauli_plus"),
        }
        session_commit_report = commit_result_to_session(
            session_dir=task.output.session_dir,
            run_out_dir=out,
            result_payload=session_payload,
            commit_kinds=task.output.session_commit_kinds,
        )
        if task.output.persist_artifacts:
            write_json(out / "session_commit_report.json", session_commit_report)
            session_commit_report_rel = "session_commit_report.json"
            outputs_map["session_commit_report"] = session_commit_report_rel
    _tick(timings, "session_commit", started_at)

    manifest = build_manifest(
        out=out,
        cfg_seed=parsed["cfg"].seed,
        backend_path=(task.input.backend_path or "<inline:solver.backend>"),
        qasm_text=task.input.qasm_text,
        dependencies=gather_dependencies(trace=trace, selected_engine_name=task.run.engine),
        outputs=outputs_map,
    )

    started_at = time.perf_counter()
    if task.output.persist_artifacts:
        manifest.finalize_digests(out)
        manifest.finalize_dependency_fingerprint()
        write_json(out / "run_manifest.json", manifest.__dict__)
    _tick(timings, "manifest_write", started_at)

    timings["total"] = time.perf_counter() - run_started_at
    started_at = time.perf_counter()
    if task.output.persist_artifacts:
        write_json(out / "timings.json", timings)
    _tick(timings, "timings_write", started_at)

    return {
        "settings_report": settings_report,
        "component_ablation_rel": write_report.relpath("component_ablation"),
        "session_commit_report": session_commit_report,
        "outputs_map": outputs_map,
    }


def _build_result_payload(
    *,
    task: WorkflowTask,
    out: Path,
    core_ctx: dict,
    optional_ctx: dict,
    finalized: dict,
    timings: dict,
    plan: ExecutionPlan,
) -> dict:
    parsed = core_ctx["parsed"]
    decoded = core_ctx["decoded"]
    analyzed = core_ctx["analyzed"]
    decoder_eval_payload = optional_ctx["decoder_eval_payload"]
    pauli_plus_payload = optional_ctx["pauli_plus_payload"]

    return {
        "core": {
            "circuit": parsed["circuit"],
            "backend_config": parsed["cfg"],
            "normalized": parsed["normalized"],
            "pulse_ir": parsed["pulse_ir"],
            "model_spec": parsed["model_spec"],
            "trace": core_ctx["trace"],
        },
        "qec": {
            "syndrome": decoded.get("syndrome"),
            "prior_model": decoded.get("prior_model"),
            "prior_report": decoded.get("prior_report"),
            "decoder_input": decoded.get("decoder_input"),
            "decoder_output": decoded.get("decoder_output"),
            "decoder_report": decoded.get("decoder_report"),
            "logical_error": decoded.get("logical_error"),
        },
        "analysis": {
            "analysis": analyzed.get("analysis", {}),
            "sensitivity_report": analyzed.get("sensitivity_report"),
            "error_budget_v2": analyzed.get("error_budget_v2"),
            "settings": finalized["settings_report"],
        },
        "optional": {
            "cross_engine_compare": optional_ctx["cross_engine_compare"],
            "decoder_eval_report": decoder_eval_payload.get("decoder_eval_report"),
            "decoder_eval_batch_manifest": decoder_eval_payload.get("decoder_eval_batch_manifest"),
            "decoder_eval_resume_state": decoder_eval_payload.get("decoder_eval_resume_state"),
            "failed_eval_tasks": decoder_eval_payload.get("failed_eval_tasks"),
            "scaling_report": pauli_plus_payload.get("scaling_report"),
            "error_budget_pauli_plus": pauli_plus_payload.get("error_budget_pauli_plus"),
            "component_ablation": finalized["component_ablation_rel"],
            "session_commit_report": finalized["session_commit_report"],
        },
        "runtime": {
            "out_dir": str(out),
            "timings": timings,
            "solver_mode": parsed["model_spec"].solver,
            "param_bindings": dict(task.input.param_bindings or {}),
            "execution_plan": {
                "template": plan.template,
                "targets": list(plan.targets),
                "stages": list(plan.stages),
                "artifact_mode": plan.artifact_mode,
                "artifact_outputs": list(plan.artifact_outputs),
                "warnings": list(plan.warnings),
            },
        },
    }


def _resolve_runtime_task(
    task: WorkflowTask | WorkflowTaskConfig | str | Path,
    *,
    solver_config: WorkflowSolverConfig | str | Path | None = None,
    device_config: WorkflowDeviceConfig | str | Path | None = None,
    pulse_config: dict | str | Path | None = None,
) -> WorkflowTask:
    """Resolve public run_task inputs to canonical runtime task."""
    if isinstance(task, WorkflowTask):
        if solver_config is not None or device_config is not None or pulse_config is not None:
            raise TypeError("Do not pass solver_config/device_config/pulse_config when `task` is already WorkflowTask.")
        return task

    if isinstance(task, WorkflowTaskConfig):
        if isinstance(solver_config, WorkflowSolverConfig):
            solver_cfg = solver_config
        elif solver_config is None and task.input.solver_config_path:
            solver_cfg = load_solver_config_file(task.input.solver_config_path)
        elif solver_config is None:
            solver_cfg = WorkflowSolverConfig()
        else:
            solver_cfg = load_solver_config_file(solver_config)

        if isinstance(device_config, WorkflowDeviceConfig):
            device_cfg = device_config
        elif device_config is None and task.input.device_config_path:
            device_cfg = load_device_config_file(task.input.device_config_path)
        elif device_config is None:
            device_cfg = WorkflowDeviceConfig()
        else:
            device_cfg = load_device_config_file(device_config)
        if isinstance(pulse_config, dict):
            device_cfg.pulse = {**dict(device_cfg.pulse or {}), **dict(pulse_config)}
        elif pulse_config is None and task.input.pulse_config_path:
            device_cfg.pulse = {**dict(device_cfg.pulse or {}), **load_pulse_config_file(task.input.pulse_config_path)}
        elif pulse_config is not None:
            device_cfg.pulse = {**dict(device_cfg.pulse or {}), **load_pulse_config_file(pulse_config)}
        backend_source = None
        if isinstance(solver_config, (str, Path)):
            backend_source = str(Path(solver_config).resolve())
        elif task.input.solver_config_path:
            backend_source = str(Path(task.input.solver_config_path).resolve())
        return compose_workflow_task(task, solver_cfg, device_cfg, backend_source=backend_source)

    if isinstance(task, (str, Path)):
        if isinstance(solver_config, WorkflowSolverConfig) or isinstance(device_config, WorkflowDeviceConfig):
            raise TypeError("When task is a file path, solver_config/device_config must be config paths, not objects.")
        if isinstance(pulse_config, dict):
            raise TypeError("When task is a file path, pulse_config must be a config path, not an inline dict.")
        return load_config_bundle_files(
            task_config=task,
            solver_config=solver_config,
            device_config=device_config,
            pulse_config=pulse_config,
        )

    raise TypeError(
        "run_task expects WorkflowTask, WorkflowTaskConfig, or task-config path. "
        "When using path/task-config, solver_config and device_config are required."
    )


def run_task(
    task: WorkflowTask | WorkflowTaskConfig | str | Path,
    *,
    solver_config: WorkflowSolverConfig | str | Path | None = None,
    device_config: WorkflowDeviceConfig | str | Path | None = None,
    pulse_config: dict | str | Path | None = None,
) -> dict:
    """Run qsim workflow from merged task or task/solver/device/pulse configs."""
    task = _resolve_runtime_task(
        task,
        solver_config=solver_config,
        device_config=device_config,
        pulse_config=pulse_config,
    )

    plan = build_execution_plan(task)
    run_started_at = time.perf_counter()
    timings: dict[str, float] = {}
    out = resolve_writable_out_dir(Path(task.output.out_dir))

    core_ctx = _run_core_stages(task=task, out=out, timings=timings, plan=plan)
    optional_ctx = _run_optional_branches(task=task, out=out, core_ctx=core_ctx, timings=timings, plan=plan)
    finalized = _persist_and_finalize(
        task=task,
        out=out,
        core_ctx=core_ctx,
        optional_ctx=optional_ctx,
        timings=timings,
        run_started_at=run_started_at,
        plan=plan,
    )
    return _build_result_payload(
        task=task,
        out=out,
        core_ctx=core_ctx,
        optional_ctx=optional_ctx,
        finalized=finalized,
        timings=timings,
        plan=plan,
    )


def run_task_files(
    *,
    task_config: str | Path,
    solver_config: str | Path | None = None,
    device_config: str | Path | None = None,
    pulse_config: str | Path | None = None,
) -> dict:
    """Run workflow from task config, with optional solver/device/pulse overrides."""
    return run_task(
        task_config,
        solver_config=solver_config,
        device_config=device_config,
        pulse_config=pulse_config,
    )


def plot_default(result: dict) -> dict:
    """Create default plotting bundle from ``run_task`` result.

    Returns a dict containing matplotlib figures with keys:
    ``pulses``, ``trace``, and ``report``.
    """
    core = dict(result.get("core", {}))
    analysis_group = dict(result.get("analysis", {}))
    analysis = dict(analysis_group.get("analysis", {}))
    return {
        "pulses": plot_pulses(core["pulse_ir"]),
        "trace": plot_trace(core["trace"]),
        "report": plot_report(analysis.get("report", {})),
    }
