"""Core workflow stages (mandatory execution path)."""

from __future__ import annotations

import time
from copy import deepcopy

from qsim.analysis.metrics import resolve_metrics_payload
from qsim.analysis.readout_chain import build_readout_analysis
from qsim.analysis.sensitivity import build_error_budget_v2, build_sensitivity_report
from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import load_backend_config
from qsim.backend.model.build import DefaultModelBuilder
from qsim.circuit.export_qasm import to_qasm
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import CircuitGate, DecoderInput, LogicalErrorSummary, Observables, Report, SyndromeFrame
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.lowering import DefaultPulseLowering
from qsim.qec.decoder import build_decoder_report, get_decoder, summarize_logical_error
from qsim.qec.prior import build_prior_and_report
from qsim.workflow.engines import select_engine
from qsim.workflow.output import write_pulse_npz_with_fallback
from qsim.workflow.contracts import (
    apply_composite_device_step_overrides,
    extract_study_prep,
    filter_composite_device_for_step,
    normalize_device_payload,
    select_primary_study_step,
)


def _normalize_study_prep(step: dict | None) -> dict[str, object]:
    return extract_study_prep(step)


def _prep_gate_from_spec(spec, *, num_qubits: int) -> CircuitGate:
    if isinstance(spec, str):
        if num_qubits != 1:
            raise ValueError("String prep_sequence entries require a single-qubit circuit or explicit qubit targets.")
        return CircuitGate(name=str(spec).strip().lower(), qubits=[0], params=[], clbits=[])
    if isinstance(spec, dict):
        name = str(spec.get("name", "")).strip().lower()
        if not name:
            raise ValueError(f"Invalid prep_sequence entry: {spec!r}")
        qubits = [int(q) for q in list(spec.get("qubits", []) or [])]
        if not qubits:
            if num_qubits != 1:
                raise ValueError("prep_sequence gate dicts must declare qubits for multi-qubit circuits.")
            qubits = [0]
        return CircuitGate(
            name=name,
            qubits=qubits,
            params=[float(x) for x in list(spec.get("params", []) or [])],
            clbits=[int(c) for c in list(spec.get("clbits", []) or [])],
        )
    raise ValueError(f"Unsupported prep_sequence entry: {spec!r}")


def _apply_study_prep_sequence_to_qasm(qasm_text: str, prep_sequence) -> str:
    sequence = list(prep_sequence or [])
    if not sequence:
        return qasm_text
    circuit = CircuitAdapter.from_qasm(qasm_text)
    prep_gates = [_prep_gate_from_spec(item, num_qubits=circuit.num_qubits) for item in sequence]
    measure_gates = [deepcopy(gate) for gate in list(circuit.gates or []) if str(gate.name).strip().lower() == "measure"]
    circuit.gates = prep_gates + measure_gates
    circuit.source_qasm = to_qasm(circuit)
    return circuit.source_qasm


def parse_compile_lower_model(
    *,
    qasm_text: str,
    backend_path: str | None,
    backend_config=None,
    out,
    device: dict | None,
    pulse: dict | None,
    frame: dict | None,
    schedule_policy: str | None,
    reset_feedback_policy: str | None,
    noise: dict | None,
    solver_run: dict | None,
    solver_mode: str | None,
    param_bindings: dict[str, float] | None,
    persist_artifacts: bool,
    analyser: dict | None = None,
    study: list[dict] | None = None,
):
    """Parse input and build simulation model artifacts."""
    stage_timings: dict[str, float] = {}
    primary_step = select_primary_study_step(study, fallback_solver_mode=solver_mode)
    prep_state = _normalize_study_prep(primary_step)
    effective_qasm_text = qasm_text
    if prep_state.get("prep_sequence") is not None:
        effective_qasm_text = _apply_study_prep_sequence_to_qasm(qasm_text, prep_state.get("prep_sequence"))
    t0 = time.perf_counter()
    circuit = CircuitAdapter.from_qasm(effective_qasm_text, param_bindings=param_bindings)
    t1 = time.perf_counter()
    stage_timings["qasm_parse"] = t1 - t0
    if backend_config is not None:
        cfg = backend_config
    else:
        if not backend_path:
            raise ValueError("Missing backend config: provide solver.backend or input.backend_path.")
        cfg = load_backend_config(backend_path)
    t2 = time.perf_counter()
    stage_timings["backend_load"] = t2 - t1

    raw_device = dict(device or {})
    raw_device = filter_composite_device_for_step(raw_device, primary_step)
    raw_device = apply_composite_device_step_overrides(raw_device, primary_step)
    model_device = normalize_device_payload(raw_device)
    pulse_cfg = dict(pulse or {})
    lowering_device = dict(model_device)
    lowering_device.update(pulse_cfg)
    if schedule_policy is not None:
        lowering_device["schedule_policy"] = str(schedule_policy).strip().lower()
        lowering_device["schedule"] = str(schedule_policy).strip().lower()
    if reset_feedback_policy is not None:
        lowering_device["reset_feedback_policy"] = str(reset_feedback_policy).strip().lower()

    normalized, compile_report = CompilePipeline().run(circuit, cfg, hardware=lowering_device)
    t3 = time.perf_counter()
    stage_timings["compile_pipeline"] = t3 - t2
    pulse_ir, executable = DefaultPulseLowering().lower(normalized, hw=lowering_device, cfg=cfg)
    t4 = time.perf_counter()
    stage_timings["lowering"] = t4 - t3

    pulse_samples = PulseCompiler.compile(pulse_ir, sample_rate_Hz=1.0e9)
    t5 = time.perf_counter()
    stage_timings["pulse_compile"] = t5 - t4
    pulse_npz = out / "pulse_samples.npz"
    if persist_artifacts:
        pulse_npz = write_pulse_npz_with_fallback(pulse_samples, out)
    t6 = time.perf_counter()
    stage_timings["pulse_npz_write"] = t6 - t5

    model_spec = DefaultModelBuilder().build(
        executable,
        hw=model_device,
        noise=noise,
        pulse_samples=pulse_samples,
        frame=frame,
        solver_run=solver_run,
        analyser=analyser,
        study=study,
        primary_step=primary_step,
        circuit=normalized,
    )
    if solver_mode:
        model_spec.solver.mode = str(solver_mode).strip().lower()
    t7 = time.perf_counter()
    stage_timings["model_build"] = t7 - t6

    return {
        "circuit": circuit,
        "cfg": cfg,
        "device_cfg": raw_device,
        "model_device": model_device,
        "pulse_cfg": pulse_cfg,
        "frame_cfg": dict(frame or {}),
        "analyser_cfg": dict(analyser or {}),
        "study": list(study or []),
        "primary_step": primary_step,
        "prep_state": prep_state,
        "effective_qasm_text": effective_qasm_text,
        "normalized": normalized,
        "compile_report": compile_report,
        "pulse_ir": pulse_ir,
        "executable": executable,
        "pulse_samples": pulse_samples,
        "pulse_npz": pulse_npz,
        "model_spec": model_spec,
        "timings": stage_timings,
    }


def run_engine_stage(
    *,
    model_spec,
    cfg,
    engine: str,
    allow_mock_fallback: bool,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
):
    """Run selected engine and annotate trajectory metadata."""
    selected = select_engine(engine)
    if model_spec.solver.seed is None:
        model_spec.solver.seed = int(cfg.seed)
    if model_spec.solver.ntraj is None:
        model_spec.solver.ntraj = int(max(1, mcwf_ntraj))

    if str(engine).strip().lower() == "qutip":
        trajectory = selected.run(model_spec)
    else:
        run_options = {
            "allow_mock_fallback": bool(allow_mock_fallback),
            "julia_timeout_s": float(julia_timeout_s),
        }
        if julia_bin:
            run_options["julia_bin"] = str(julia_bin)
        if julia_depot_path:
            run_options["julia_depot_path"] = str(julia_depot_path)
        trajectory = selected.run(model_spec, run_options=run_options)
    metadata = dict(getattr(trajectory, "metadata", {}) or {})
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    classical = dict(getattr(trajectory, "classical", {}) or {})
    measurements = dict(getattr(trajectory, "measurements", {}) or {})
    details = dict(metadata.get("details", {}) or {})
    if "quantum_state_trajectory" in metadata:
        qstate = dict(metadata.pop("quantum_state_trajectory", {}) or {})
    elif "quantum_state_trajectory" in details:
        qstate = dict(details.pop("quantum_state_trajectory", {}) or {})
    else:
        qstate = {}
    actual_kind = str(qstate.get("actual_kind", "")).strip().lower()
    if qstate:
        if actual_kind == "wave_function":
            wave_function.update(qstate)
        elif actual_kind == "density_matrix":
            density_matrix.update(qstate)
        else:
            density_matrix.update(qstate)
    if "readout_observables" in metadata:
        classical["readout"] = dict(metadata.pop("readout_observables", {}) or {})
    if "readout_observables" in details and "readout" not in classical:
        classical["readout"] = dict(details.pop("readout_observables", {}) or {})
    if "measurement_records" in metadata:
        measurements["records"] = list(metadata.pop("measurement_records", []) or [])
    if "measurement_records" in details and "records" not in measurements:
        measurements["records"] = list(details.pop("measurement_records", []) or [])
    if "jump_events" in details and "jump_events" not in metadata:
        metadata["jump_events"] = list(details.pop("jump_events", []) or [])
    if details:
        metadata["details"] = details
    elif "details" in metadata:
        metadata.pop("details", None)
    descriptions = dict(metadata.get("descriptions", {}) or {})
    descriptions["times"] = {
        "meaning": "Simulation time samples aligned with all trajectory channels.",
        "unit": "s",
        "shape": "[time]",
    }
    if wave_function:
        descriptions["wave_function"] = {
            "meaning": "Complex wave-function snapshots psi(t) over time.",
            "encoding": str(wave_function.get("encoding", "complex")),
            "shape": "[time][hilbert_index]",
            "representation": "ket",
        }
    if density_matrix:
        descriptions["density_matrix"] = {
            "meaning": "Complex density-matrix snapshots rho(t) over time.",
            "encoding": str(density_matrix.get("encoding", "complex")),
            "shape": "[time][hilbert_index][hilbert_index]",
            "representation": "operator",
        }
    for key, payload in classical.items():
        if isinstance(payload, dict):
            descriptions[f"classical.{key}"] = {
                "meaning": str(payload.get("description", f"Classical trajectory payload `{key}`.")),
                "quantity": str(payload.get("quantity", key)),
                "unit": str(payload.get("unit", "")),
                "series_labels": list(payload.get("series_labels", []) or []),
                "shape": "[time][series]",
            }
    for key, payload in measurements.items():
        descriptions[f"measurements.{key}"] = {
            "meaning": "Measurement-side raw data aligned with the trajectory timeline or event order.",
            "kind": type(payload).__name__,
            "shape": "[event]" if isinstance(payload, list) else "structured",
        }
    metadata["descriptions"] = descriptions
    trajectory.wave_function = wave_function or None
    trajectory.density_matrix = density_matrix or None
    trajectory.classical = classical
    trajectory.measurements = measurements
    trajectory.metadata = metadata
    return trajectory


def run_decode_stage(
    *,
    trajectory,
    circuit,
    model_spec,
    engine: str,
    cfg,
    prior_backend: str,
    decoder: str,
    decoder_options: dict | None,
):
    """Run syndrome build, prior build, decoder, and logical error summary."""
    rows = state_rows(trajectory)
    syndrome = SyndromeFrame(
        rounds=max(1, len(trajectory.times)),
        detectors=[[1 if v > 0.5 else 0 for v in row] for row in rows],
        observables=[int(v > 0.5) for v in (rows[-1] if rows else [])],
        metadata={"source": "trajectory_threshold", "threshold": 0.5},
    )
    prior_model, prior_report = build_prior_and_report(
        syndrome,
        backend=prior_backend,
        context={"num_qubits": circuit.num_qubits, "solver": model_spec.solver_mode, "engine": engine},
    )
    decoder_input = DecoderInput(
        syndrome=syndrome,
        prior=prior_model,
        options={"algorithm": decoder},
        metadata={"pipeline": "qec_m3", "prior_backend": prior_backend},
    )

    dec_t0 = time.perf_counter()
    decoder_output = get_decoder(decoder).run(decoder_input, options={"seed": cfg.seed, **(decoder_options or {})})
    decoder_report = build_decoder_report(decoder_input, decoder_output, elapsed_s=time.perf_counter() - dec_t0)
    logical_error = summarize_logical_error(decoder_output, shots=max(1, len(syndrome.detectors)))

    return {
        "syndrome": syndrome,
        "prior_model": prior_model,
        "prior_report": prior_report,
        "decoder_input": decoder_input,
        "decoder_output": decoder_output,
        "decoder_report": decoder_report,
        "logical_error": logical_error,
    }


def _resolve_analysis_trajectory(trajectory, analyser_cfg: dict | None) -> dict:
    trajectory_cfg = dict((analyser_cfg or {}).get("trajectory", {}) or {})
    save_times = str(trajectory_cfg.get("save_times", "all")).strip().lower()
    include_times = save_times != "none"
    save_final_state = bool(trajectory_cfg.get("save_final_state", True))
    save_jump_events = bool(trajectory_cfg.get("save_jump_events", False))
    save_measurement_records = bool(trajectory_cfg.get("save_measurement_records", False))
    requested_kind = str(trajectory_cfg.get("quantum", "")).strip().lower()
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    payload = {}
    if include_times:
        payload["times"] = list(trajectory.times)
    if requested_kind == "wave_function" and wave_function:
        payload["wave_function"] = list(wave_function.get("snapshots", []) or [])
        if wave_function.get("runs"):
            payload["wave_function_runs"] = list(wave_function.get("runs", []) or [])
    elif requested_kind == "density_matrix" and density_matrix:
        payload["density_matrix"] = list(density_matrix.get("snapshots", []) or [])
        if density_matrix.get("runs"):
            payload["density_matrix_runs"] = list(density_matrix.get("runs", []) or [])
    else:
        if density_matrix:
            payload["density_matrix"] = list(density_matrix.get("snapshots", []) or [])
            if density_matrix.get("runs"):
                payload["density_matrix_runs"] = list(density_matrix.get("runs", []) or [])
        elif wave_function:
            payload["wave_function"] = list(wave_function.get("snapshots", []) or [])
            if wave_function.get("runs"):
                payload["wave_function_runs"] = list(wave_function.get("runs", []) or [])
    if getattr(trajectory, "classical", None):
        payload["classical"] = dict(trajectory.classical or {})
    if save_measurement_records and getattr(trajectory, "measurements", None):
        payload["measurements"] = dict(trajectory.measurements or {})
    descriptions = dict((trajectory.metadata or {}).get("descriptions", {}) or {})
    if descriptions:
        payload["metadata"] = {"descriptions": descriptions}
    if save_final_state:
        if "density_matrix" in payload and payload["density_matrix"]:
            payload["final_density_matrix"] = payload["density_matrix"][-1]
        elif "wave_function" in payload and payload["wave_function"]:
            payload["final_wave_function"] = payload["wave_function"][-1]
    if save_jump_events:
        payload["jump_events"] = list((trajectory.metadata or {}).get("jump_events", []) or [])
    if density_matrix.get("note"):
        payload["note"] = str(density_matrix.get("note"))
    elif wave_function.get("note"):
        payload["note"] = str(wave_function.get("note"))
    elif requested_kind in {"wave_function", "density_matrix"} and not density_matrix and not wave_function:
        payload["note"] = (
            f"requested {requested_kind} but no quantum_state_trajectory was stored; "
            "classical channels contain reduced observables rather than full subsystem states"
        )
    return payload


def _resolve_metric_payload(trajectory, model_spec, analyser_cfg: dict | None, metric_registry=None) -> tuple[dict, Observables, Report]:
    return resolve_metrics_payload(trajectory, model_spec, analyser_cfg, registry=metric_registry)


def run_analysis_stage(
    *,
    trajectory,
    model_spec,
    pulse_ir,
    pulse_cfg: dict | None,
    cfg,
    logical_error,
    analyser_cfg: dict | None,
    metric_registry=None,
):
    """Run observables/report analysis and build sensitivity budgets."""
    stage_timings: dict[str, float] = {}
    t0 = time.perf_counter()
    trajectory_payload = _resolve_analysis_trajectory(trajectory, analyser_cfg)
    metrics_payload, observables_obj, report_obj = _resolve_metric_payload(
        trajectory,
        model_spec,
        analyser_cfg,
        metric_registry=metric_registry,
    )
    readout_payload = build_readout_analysis(
        trajectory=trajectory,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analyser_cfg=analyser_cfg,
        seed=int(getattr(cfg, "seed", 12345)),
    )
    analysis = {
        "trajectory": trajectory_payload,
        "metrics": metrics_payload,
        "report": report_obj.__dict__,
    }
    if readout_payload.get("readout") is not None:
        analysis["readout"] = readout_payload["readout"]
    if readout_payload.get("iq") is not None:
        analysis["iq"] = readout_payload["iq"]
    t1 = time.perf_counter()
    stage_timings["analysis_run"] = t1 - t0

    logical_error_obj = None
    sensitivity_report = None
    error_budget_v2 = None
    if logical_error is not None:
        logical_error_obj = LogicalErrorSummary(
            schema_version=str(logical_error.schema_version),
            logical_x=float(logical_error.logical_x),
            logical_z=float(logical_error.logical_z),
            shots=int(logical_error.shots),
            metadata=dict(logical_error.metadata),
        )
        sensitivity_report = build_sensitivity_report(
            observables_obj,
            logical_error_obj,
            seed=cfg.seed,
            sweep=cfg.sweep,
        )
        error_budget_v2 = build_error_budget_v2(
            observables_obj,
            logical_error_obj,
            sensitivity_report=sensitivity_report,
        )
    t2 = time.perf_counter()
    stage_timings["sensitivity_run"] = t2 - t1
    return {
        "analysis": analysis,
        "observables_obj": observables_obj,
        "logical_error_obj": logical_error_obj,
        "sensitivity_report": sensitivity_report,
        "error_budget_v2": error_budget_v2,
        "timings": stage_timings,
    }


__all__ = [
    "parse_compile_lower_model",
    "run_analysis_stage",
    "run_decode_stage",
    "run_engine_stage",
]

