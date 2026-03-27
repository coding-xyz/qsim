"""Workflow pipeline implementation and artifact export helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
import math
import time

from qsim.common.schemas import Carrier, ChannelSpec, PulseIR, PulseSpec, Trace, utc_now_iso, write_json
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trace
from qsim.workflow.contracts import (
    WorkflowDeviceConfig,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
    extract_study_prep,
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


def _study_entries(task: WorkflowTask) -> list[dict]:
    return [dict(step) for step in list(task.input.study or []) if isinstance(step, dict)]


def _sanitize_study_name(name: str, idx: int) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(name).strip())
    raw = raw.strip("._") or f"study_{idx + 1}"
    return raw


def _prepare_task_for_study(task: WorkflowTask, study: dict, *, out_dir: Path) -> WorkflowTask:
    prep_state = extract_study_prep(study)
    prep_sequence = list(prep_state.get("prep_sequence", []) or [])
    prep_label = str(prep_state.get("prep_label", "") or "").strip()

    analysis = deepcopy(task.input.analysis or {})
    pulse = deepcopy(task.input.pulse or {})
    if prep_label:
        iq_cfg = dict(analysis.get("iq_discrimination", {}) or {})
        iq_cfg["calibration_states"] = [{"label": prep_label, "preparation": deepcopy(prep_sequence)}]
        analysis["iq_discrimination"] = iq_cfg

        acquisition = dict(pulse.get("acquisition", {}) or {})
        acquisition_iq = dict(acquisition.get("iq_discrimination", {}) or {})
        acquisition_iq["labels"] = [prep_label]
        acquisition["iq_discrimination"] = acquisition_iq
        pulse["acquisition"] = acquisition

    case_input = replace(
        task.input,
        analysis=analysis,
        pulse=pulse,
        study=[deepcopy(study)],
    )
    case_output = replace(task.output, out_dir=str(out_dir))
    return replace(task, input=case_input, output=case_output)


def _nearest_centroid(point: complex, centroids: dict[str, complex]) -> str:
    best_label = ""
    best_dist = float("inf")
    for label, center in centroids.items():
        dist = abs(point - center)
        if dist < best_dist:
            best_label = label
            best_dist = dist
    return best_label


def _build_multi_study_iq_comparison(case_results: dict[str, dict]) -> dict[str, object] | None:
    centroids: dict[str, complex] = {}
    clouds: dict[str, list[complex]] = {}
    study_map: dict[str, str] = {}
    for study_name, result in case_results.items():
        iq = dict(result.get("results", {}).get("iq", {}) or {})
        raw_centroids = dict(iq.get("centroids", {}) or {})
        raw_clouds = dict(iq.get("synthetic_clouds", {}) or {})
        for label, pair in raw_centroids.items():
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            centroids[str(label)] = complex(float(pair[0]), float(pair[1]))
            study_map[str(label)] = study_name
        for label, samples in raw_clouds.items():
            points: list[complex] = []
            for pair in list(samples or []):
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    continue
                points.append(complex(float(pair[0]), float(pair[1])))
            if points:
                clouds[str(label)] = points
    labels = [label for label in centroids.keys() if label in clouds]
    if not labels:
        return None

    confusion = [[0 for _ in labels] for _ in labels]
    all_pairwise: list[float] = []
    for i, label in enumerate(labels):
        for point in clouds.get(label, []):
            pred = _nearest_centroid(point, {lab: centroids[lab] for lab in labels})
            if pred in labels:
                confusion[i][labels.index(pred)] += 1
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            all_pairwise.append(abs(centroids[a] - centroids[b]))
    total = sum(sum(row) for row in confusion)
    fidelity = float(sum(confusion[i][i] for i in range(len(labels))) / max(1, total))
    noise_sigma = 0.0
    for label in labels:
        center = centroids[label]
        points = clouds.get(label, [])
        if not points:
            continue
        rms = math.sqrt(sum(abs(point - center) ** 2 for point in points) / max(1, len(points)))
        noise_sigma = max(noise_sigma, rms)
    cluster_separation = float(min(all_pairwise) / max(noise_sigma, 1.0e-12)) if all_pairwise else 0.0
    snr = float((sum(all_pairwise) / len(all_pairwise)) / max(2.0 * noise_sigma, 1.0e-12)) if all_pairwise else 0.0
    return {
        "schema_version": "1.0",
        "labels": labels,
        "centroids": {label: [float(centroids[label].real), float(centroids[label].imag)] for label in labels},
        "synthetic_clouds": {
            label: [[float(point.real), float(point.imag)] for point in clouds.get(label, [])]
            for label in labels
        },
        "confusion_matrix": {"labels": labels, "values": confusion},
        "assignment_fidelity": fidelity,
        "cluster_separation": cluster_separation,
        "snr": snr,
        "study_map": study_map,
    }


def _public_value(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _public_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def _pulse_ir_from_public_payload(payload: dict | None) -> PulseIR | None:
    raw = dict(payload or {})
    channels_payload = list(raw.get("channels", []) or [])
    if not channels_payload:
        return None
    channels: list[ChannelSpec] = []
    for ch in channels_payload:
        if not isinstance(ch, dict):
            continue
        pulses: list[PulseSpec] = []
        for pulse in list(ch.get("pulses", []) or []):
            if not isinstance(pulse, dict):
                continue
            carrier_payload = pulse.get("carrier")
            carrier = None
            if isinstance(carrier_payload, dict):
                carrier = Carrier(
                    freq=float(carrier_payload.get("freq", 0.0)),
                    phase=float(carrier_payload.get("phase", 0.0)),
                )
            pulses.append(
                PulseSpec(
                    t0_s=float(pulse.get("t0_s", 0.0)),
                    t1_s=float(pulse.get("t1_s", 0.0)),
                    amp=float(pulse.get("amp", 0.0)),
                    shape=str(pulse.get("shape", "rect")),
                    params=dict(pulse.get("params", {}) or {}),
                    carrier=carrier,
                )
            )
        channels.append(ChannelSpec(name=str(ch.get("name", "")), pulses=pulses))
    return PulseIR(
        schema_version=str(raw.get("schema_version", "1.0")),
        t_end_s=float(raw.get("t_end_s", 0.0)),
        channels=channels,
    )


def _run_core_stages(*, task: WorkflowTask, out: Path, timings: dict[str, float], plan: ExecutionPlan) -> dict:
    parsed = parse_compile_lower_model(
        qasm_text=task.input.qasm_text,
        backend_path=task.input.backend_path,
        backend_config=task.input.backend_config,
        out=out,
        device=(task.input.device_model or task.input.device),
        pulse=task.input.pulse,
        frame=task.input.frame,
        analysis=task.input.analysis,
        study=task.input.study,
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
    if plan.run_analysis:
        analyzed = run_analysis_stage(
            trace=trace,
            model_spec=parsed["model_spec"],
            pulse_ir=parsed["pulse_ir"],
            pulse_cfg=task.input.pulse,
            cfg=parsed["cfg"],
            logical_error=decoded["logical_error"],
            analysis_cfg=task.input.analysis,
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
        analysis=task.input.analysis,
        study=parsed.get("study"),
        primary_step=parsed.get("primary_step"),
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
        qasm_text=str(parsed.get("effective_qasm_text", task.input.qasm_text)),
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
    trace = core_ctx["trace"]
    decoded = core_ctx["decoded"]
    analyzed = core_ctx["analyzed"]
    model_spec = parsed["model_spec"]
    model_payload = dict(model_spec.payload or {})
    results_trace = dict(analyzed.get("analysis", {}).get("trace", {}) or {})
    results_metrics = dict(analyzed.get("analysis", {}).get("metrics", {}) or {})
    results_readout = dict(analyzed.get("analysis", {}).get("readout", {}) or {})
    results_iq = dict(analyzed.get("analysis", {}).get("iq", {}) or {})
    results_report = dict(analyzed.get("analysis", {}).get("report", {}) or {})

    qec_payload = {
        "syndrome": decoded.get("syndrome"),
        "prior_model": decoded.get("prior_model"),
        "prior_report": decoded.get("prior_report"),
        "decoder_input": decoded.get("decoder_input"),
        "decoder_output": decoded.get("decoder_output"),
        "decoder_report": decoded.get("decoder_report"),
        "logical_error": decoded.get("logical_error"),
    }
    if not any(value is not None for value in qec_payload.values()):
        qec_payload = None

    return {
        "meta": {
            "schema_version": "3.0",
            "run_id": out.name,
            "created_at": utc_now_iso(),
            "task": {
                "template": plan.template,
                "targets": list(plan.targets),
                "tags": list(task.tags or []),
            },
        },
        "inputs": {
            "task": {
                "targets": list(plan.targets),
                "qasm_text": str(parsed.get("effective_qasm_text", task.input.qasm_text)),
                "param_bindings": dict(task.input.param_bindings or {}),
            },
            "solver": {
                "engine": task.run.engine,
                "study": list(task.input.study or []),
                "analysis": dict(task.input.analysis or {}),
                "schedule": {"policy": task.input.schedule_policy} if task.input.schedule_policy else {},
                "frame": dict(task.input.frame or {}),
            },
            "device": _public_value(parsed["device_cfg"] or {}),
            "pulse": _public_value(parsed["pulse_cfg"] or {}),
            "noise": _public_value(task.input.noise or {}),
        },
        "model": {
            "runtime_level": model_payload.get("simulation_level", "qubit"),
            "model_type": model_payload.get("model_type", "unknown"),
            "dimension": model_spec.dimension,
            "num_qubits": model_payload.get("num_qubits"),
            "component_summary": model_payload.get("component_summary", {}),
            "study_summary": model_payload.get("study_summary", {}),
            "executable": {
                "circuit": _public_value(parsed["circuit"]),
                "normalized_circuit": _public_value(parsed["normalized"]),
                "compile_report": _public_value(parsed["compile_report"]),
                "pulse_ir": _public_value(parsed["pulse_ir"]),
                "executable_model": _public_value(parsed["executable"]),
                "model_spec": _public_value(model_spec),
            },
        },
        "results": {
            "trace": _public_value(results_trace),
            "metrics": _public_value(results_metrics),
            "readout": _public_value(results_readout),
            "iq": _public_value(results_iq),
            "report": _public_value(results_report),
            "qec": _public_value(qec_payload),
            "sensitivity": _public_value(analyzed.get("sensitivity_report")),
            "error_budget": _public_value(analyzed.get("error_budget_v2")),
        },
        "runtime": {
            "engine_requested": task.run.engine,
            "engine_used": trace.engine,
            "solver_mode": str(task.run.solver_mode or model_spec.solver),
            "seed": int(parsed["cfg"].seed),
            "out_dir": str(out),
            "timings": {str(k): float(v) for k, v in timings.items()},
            "execution_plan": {
                "template": plan.template,
                "targets": list(plan.targets),
                "stages": list(plan.stages),
                "artifact_mode": plan.artifact_mode,
                "artifact_outputs": list(plan.artifact_outputs),
                "warnings": list(plan.warnings),
            },
        },
        "artifacts": {
            "out_dir": str(out),
            "files": dict(finalized["outputs_map"]),
        },
    }


def _run_single_task(
    *,
    task: WorkflowTask,
    out: Path,
) -> dict:
    plan = build_execution_plan(task)
    run_started_at = time.perf_counter()
    timings: dict[str, float] = {}

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


def _build_multi_study_payload(*, task: WorkflowTask, out: Path, case_results: dict[str, dict]) -> dict:
    iq_comparison = _build_multi_study_iq_comparison(case_results)
    study_dirs = {
        name: str(Path(result.get("artifacts", {}).get("out_dir", "")))
        for name, result in case_results.items()
    }
    payload = {
        "meta": {
            "schema_version": "3.0",
            "run_id": out.name,
            "created_at": utc_now_iso(),
            "multi_study": True,
        },
        "inputs": {
            "task": {
                "qasm_text": task.input.qasm_text,
                "param_bindings": dict(task.input.param_bindings or {}),
            },
            "solver": {
                "engine": task.run.engine,
                "study": list(task.input.study or []),
                "analysis": dict(task.input.analysis or {}),
                "frame": dict(task.input.frame or {}),
            },
            "device": _public_value(task.input.device_model or task.input.device or {}),
            "pulse": _public_value(task.input.pulse or {}),
            "noise": _public_value(task.input.noise or {}),
        },
        "runtime": {
            "multi_study": True,
            "engine_requested": task.run.engine,
            "out_dir": str(out),
            "study_names": list(case_results.keys()),
        },
        "artifacts": {
            "out_dir": str(out),
            "study_dirs": study_dirs,
        },
        "studies": case_results,
    }
    if task.output.persist_artifacts:
        write_json(out / "study_index.json", payload["artifacts"])
        if iq_comparison is not None:
            write_json(out / "study_comparison_iq.json", iq_comparison)
            payload["artifacts"]["study_comparison_iq"] = str(out / "study_comparison_iq.json")
    if iq_comparison is not None:
        payload["comparison"] = {"iq": iq_comparison}
    return payload


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
    """Run a qsim workflow and return a structured result payload.

    Args:
        task: Either a fully composed ``WorkflowTask``, a
            ``WorkflowTaskConfig``, or a path to a task config file.
        solver_config: Optional solver config object or config path.
        device_config: Optional device config object or config path.
        pulse_config: Optional pulse config mapping or config path.

    Returns:
        A structured result dictionary with top-level groups:
        ``meta``, ``inputs``, ``model``, ``results``, ``runtime``, and ``artifacts``.
    """
    task = _resolve_runtime_task(
        task,
        solver_config=solver_config,
        device_config=device_config,
        pulse_config=pulse_config,
    )
    out = resolve_writable_out_dir(Path(task.output.out_dir))
    studies = _study_entries(task)
    if len(studies) <= 1:
        return _run_single_task(task=task, out=out)

    case_results: dict[str, dict] = {}
    for idx, study in enumerate(studies):
        case_name = _sanitize_study_name(str(study.get("name", "")), idx)
        case_task = _prepare_task_for_study(task, study, out_dir=out / case_name)
        case_results[case_name] = _run_single_task(task=case_task, out=out / case_name)
    return _build_multi_study_payload(task=task, out=out, case_results=case_results)


def run_task_files(
    *,
    task_config: str | Path,
    solver_config: str | Path | None = None,
    device_config: str | Path | None = None,
    pulse_config: str | Path | None = None,
) -> dict:
    """Run a workflow from config files.

    This is the most common file-driven entrypoint and mirrors the CLI command
    ``qsim run-task``.
    """
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
    model = dict(result.get("model", {}) or {})
    executable = dict(model.get("executable", {}) or {})
    results = dict(result.get("results", {}) or {})
    trace_payload = dict(results.get("trace", {}) or {})
    pulse_ir = _pulse_ir_from_public_payload(executable.get("pulse_ir"))
    plot_trace_obj = None
    states = list(trace_payload.get("states", []) or [])
    times = list(trace_payload.get("times", []) or [])
    representation = dict(trace_payload.get("state_representation", {}) or {})
    if (
        representation.get("encoding") != "complex_pairs"
        and states
        and times
        and isinstance(states[0], list)
        and all(not isinstance(item, (list, tuple)) for item in states[0])
    ):
        plot_trace_obj = Trace(
            engine=str(dict(result.get("runtime", {}) or {}).get("engine_used", "unknown")),
            times=[float(t) for t in times],
            states=[[float(v) for v in row] for row in states],
        )
    return {
        "pulses": plot_pulses(pulse_ir) if pulse_ir is not None else None,
        "trace": plot_trace(plot_trace_obj) if plot_trace_obj is not None else None,
        "report": plot_report(results.get("report", {})),
    }
