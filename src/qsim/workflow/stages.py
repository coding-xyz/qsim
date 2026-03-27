"""Core workflow stages (mandatory execution path)."""

from __future__ import annotations

import time
from copy import deepcopy

from qsim.analysis.observables import compute_observables
from qsim.analysis.readout_chain import build_readout_analysis
from qsim.analysis.sensitivity import build_error_budget_v2, build_sensitivity_report
from qsim.analysis.trace_semantics import annotate_trace_metadata, state_encoding
from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import load_backend_config
from qsim.backend.lowering import DefaultLowering
from qsim.backend.model_build import DefaultModelBuilder
from qsim.circuit.export_qasm import to_qasm
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import CircuitGate, DecoderInput, LogicalErrorSummary, Observables, Report, SyndromeFrame
from qsim.pulse.sequence import PulseCompiler
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
    analysis: dict | None = None,
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
    pulse_ir, executable = DefaultLowering().lower(normalized, hw=lowering_device, cfg=cfg)
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
        analysis=analysis,
        study=study,
        primary_step=primary_step,
    )
    if solver_mode:
        model_spec.solver = str(solver_mode).strip().lower()
    t7 = time.perf_counter()
    stage_timings["model_build"] = t7 - t6

    return {
        "circuit": circuit,
        "cfg": cfg,
        "device_cfg": raw_device,
        "model_device": model_device,
        "pulse_cfg": pulse_cfg,
        "frame_cfg": dict(frame or {}),
        "analysis_cfg": dict(analysis or {}),
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
    """Run selected engine and annotate trace metadata."""
    selected = select_engine(engine)
    run_options = {
        "seed": cfg.seed,
        "solver_mode": model_spec.solver,
        "allow_mock_fallback": bool(allow_mock_fallback),
        "julia_timeout_s": float(julia_timeout_s),
        "ntraj": int(max(1, mcwf_ntraj)),
    }
    if julia_bin:
        run_options["julia_bin"] = str(julia_bin)
    if julia_depot_path:
        run_options["julia_depot_path"] = str(julia_depot_path)

    trace = selected.run(model_spec, run_options=run_options)
    annotate_trace_metadata(
        trace,
        num_qubits=int(model_spec.payload.get("num_qubits", 0) or 0) or None,
        dimension=int(getattr(model_spec, "dimension", 0) or 0) or None,
        engine_name=engine,
    )
    return trace


def run_decode_stage(
    *,
    trace,
    circuit,
    model_spec,
    engine: str,
    cfg,
    prior_backend: str,
    decoder: str,
    decoder_options: dict | None,
):
    """Run syndrome build, prior build, decoder, and logical error summary."""
    syndrome = SyndromeFrame(
        rounds=max(1, len(trace.times)),
        detectors=[[1 if v > 0.5 else 0 for v in row] for row in trace.states],
        observables=[int(v > 0.5) for v in (trace.states[-1] if trace.states else [])],
        metadata={"source": "trace_threshold", "threshold": 0.5},
    )
    prior_model, prior_report = build_prior_and_report(
        syndrome,
        backend=prior_backend,
        context={"num_qubits": circuit.num_qubits, "solver": model_spec.solver, "engine": engine},
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


def _resolve_analysis_trace(trace, analysis_cfg: dict | None) -> dict:
    trace_cfg = dict((analysis_cfg or {}).get("trace", {}) or {})
    save_times = str(trace_cfg.get("save_times", "all")).strip().lower()
    include_times = save_times != "none"
    save_final_state = bool(trace_cfg.get("save_final_state", True))
    save_jump_events = bool(trace_cfg.get("save_jump_events", False))
    save_measurement_records = bool(trace_cfg.get("save_measurement_records", False))
    requested_kind = str(trace_cfg.get("states", "")).strip().lower()
    quantum_state_trace = dict((trace.metadata or {}).get("quantum_state_trace", {}) or {})
    actual_kind = requested_kind
    states_payload = [list(row) for row in trace.states]
    if requested_kind in {"wave_function", "density_matrix"} and quantum_state_trace:
        actual_kind = str(quantum_state_trace.get("actual_kind", requested_kind))
        states_payload = list(quantum_state_trace.get("snapshots", []) or [])
    payload = {
        "state_representation": {
            "requested": trace_cfg.get("states", ""),
            "actual": actual_kind,
            "encoding": "complex_pairs" if quantum_state_trace else state_encoding(trace),
        },
        "times": list(trace.times) if include_times else [],
        "states": states_payload,
    }
    if save_final_state:
        if quantum_state_trace and states_payload:
            payload["final_state"] = states_payload[-1]
        else:
            payload["final_state"] = list(trace.states[-1]) if trace.states else []
    if save_jump_events:
        payload["jump_events"] = list((trace.metadata or {}).get("jump_events", []) or [])
    if save_measurement_records:
        payload["measurement_records"] = list((trace.metadata or {}).get("measurement_records", []) or [])
    if quantum_state_trace.get("note"):
        payload["note"] = str(quantum_state_trace.get("note"))
    elif requested_kind in {"wave_function", "density_matrix"} and not quantum_state_trace:
        payload["note"] = (
            f"requested {requested_kind} but no quantum_state_trace was stored; "
            "states contains reduced observables rather than full subsystem states"
        )
    return payload


def _complex_from_pair(value) -> complex:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return complex(float(value[0]), float(value[1]))
    return complex(float(value), 0.0)


def _basis_labels(dimension: int, num_qubits: int, levels: int) -> list[str]:
    if dimension <= 0:
        return []
    if num_qubits > 0 and levels > 1:
        expected = levels**num_qubits
        if expected == dimension:
            labels: list[str] = []
            for idx in range(dimension):
                digits: list[str] = []
                rem = idx
                for _ in range(num_qubits):
                    digits.append(str(rem % levels))
                    rem //= levels
                labels.append("".join(reversed(digits)))
            return labels
    return [str(i) for i in range(dimension)]


def _label_excitation_value(label: str, *, num_qubits: int) -> float:
    digits = [int(ch) for ch in str(label) if ch.isdigit()]
    if not digits:
        return 0.0
    if num_qubits > 0 and len(digits) >= num_qubits:
        return float(sum(digits[:num_qubits])) / float(num_qubits)
    return float(sum(digits)) / float(len(digits))


def _population_series_from_quantum_state(trace, model_spec) -> dict[str, list[float]]:
    qstate = dict((trace.metadata or {}).get("quantum_state_trace", {}) or {})
    snapshots = list(qstate.get("snapshots", []) or [])
    if not snapshots:
        return {}
    actual_kind = str(qstate.get("actual_kind", "")).strip().lower()
    payload = dict((model_spec.payload or {}))
    num_qubits = int(payload.get("num_qubits", 0) or 0)
    levels = 2
    if str(payload.get("model_type", "")).strip().lower() in {"transmon_nlevel", "cqed_jc"}:
        levels = int(payload.get("transmon_levels", 2) or 2)
    series: dict[str, list[float]] = {}
    labels: list[str] = []

    for snapshot in snapshots:
        populations: list[float]
        if actual_kind == "density_matrix":
            populations = []
            for i, row in enumerate(snapshot):
                if i >= len(row):
                    populations.append(0.0)
                else:
                    populations.append(max(0.0, float(_complex_from_pair(row[i]).real)))
        elif actual_kind == "wave_function":
            populations = [abs(_complex_from_pair(v)) ** 2 for v in snapshot]
        else:
            return {}

        if not labels:
            labels = _basis_labels(len(populations), num_qubits, max(2, levels))
            series = {label: [] for label in labels}
        for idx, label in enumerate(labels):
            value = float(populations[idx]) if idx < len(populations) else 0.0
            series[label].append(value)
    return series


def _population_series_from_trace_rows(trace, model_spec) -> dict[str, list[float]]:
    if not trace.states:
        return {}
    payload = dict(model_spec.payload or {})
    num_qubits = int(payload.get("num_qubits", 0) or 0)
    levels = 2
    if str(payload.get("model_type", "")).strip().lower() in {"transmon_nlevel", "cqed_jc"}:
        levels = int(payload.get("transmon_levels", 2) or 2)

    row_len = len(trace.states[0]) if trace.states and trace.states[0] else 0
    if row_len <= 0:
        return {}
    labels = _basis_labels(row_len if row_len > 1 else 2, num_qubits, max(2, levels))
    if row_len == 1:
        series = {labels[0]: [], labels[1]: []}
        for row in trace.states:
            p1 = float(row[0]) if row else 0.0
            series[labels[0]].append(float(max(0.0, 1.0 - p1)))
            series[labels[1]].append(p1)
        return series

    series = {label: [] for label in labels[:row_len]}
    for row in trace.states:
        for idx, label in enumerate(labels[:row_len]):
            value = float(row[idx]) if idx < len(row) else 0.0
            series[label].append(value)
    return series


def _population_series(trace, model_spec) -> dict[str, list[float]]:
    return _population_series_from_quantum_state(trace, model_spec) or _population_series_from_trace_rows(trace, model_spec)


def _mean_excited_series_from_population(series: dict[str, list[float]], model_spec) -> list[float]:
    if not series:
        return []
    payload = dict(model_spec.payload or {})
    num_qubits = int(payload.get("num_qubits", 0) or 0)
    labels = list(series.keys())
    length = max(len(values) for values in series.values())
    values: list[float] = []
    for idx in range(length):
        total = 0.0
        for label in labels:
            sample = series[label][idx] if idx < len(series[label]) else 0.0
            total += _label_excitation_value(label, num_qubits=num_qubits) * float(sample)
        values.append(float(total))
    return values


def _variance_series_from_population(series: dict[str, list[float]], model_spec) -> list[float]:
    if not series:
        return []
    payload = dict(model_spec.payload or {})
    num_qubits = int(payload.get("num_qubits", 0) or 0)
    labels = list(series.keys())
    label_values = {label: _label_excitation_value(label, num_qubits=num_qubits) for label in labels}
    means = _mean_excited_series_from_population(series, model_spec)
    length = len(means)
    values: list[float] = []
    for idx in range(length):
        mean = means[idx]
        total = 0.0
        for label in labels:
            sample = series[label][idx] if idx < len(series[label]) else 0.0
            delta = label_values[label] - mean
            total += float(sample) * float(delta * delta)
        values.append(float(total))
    return values


def _metric_terminal_value(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if isinstance(value.get("values"), list) and value.get("values"):
            tail = value["values"][-1]
            if isinstance(tail, (int, float)):
                return float(tail)
        if isinstance(value.get("series"), dict):
            return None
    return None


def _resolve_metric_payload(trace, model_spec, analysis_cfg: dict | None) -> tuple[dict, Observables, Report]:
    requested_metrics = list((analysis_cfg or {}).get("metrics", []) or [])
    observables = compute_observables(trace)
    observable_values = dict(observables.values or {})
    metrics_out: dict[str, object] = {}

    if not requested_metrics:
        metrics_out = dict(observable_values)
    else:
        for item in requested_metrics:
            if isinstance(item, str):
                name = str(item).strip()
                metric_cfg = {}
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                metric_cfg = dict(item)
            else:
                continue
            if not name:
                continue
            key = name.lower()
            if key == "population":
                basis_series = _population_series(trace, model_spec)
                metrics_out[name] = {
                    "times": list(trace.times),
                    "series": basis_series,
                }
                for label, values in basis_series.items():
                    if values:
                        observable_values[str(label)] = float(values[-1])
                if "0" in basis_series and basis_series["0"]:
                    observable_values["final_p0"] = float(basis_series["0"][-1])
                if "1" in basis_series and basis_series["1"]:
                    observable_values["final_p1"] = float(basis_series["1"][-1])
            elif key == "variance":
                basis_series = _population_series(trace, model_spec)
                variance_series = _variance_series_from_population(basis_series, model_spec)
                metrics_out[name] = {
                    "times": list(trace.times),
                    "values": variance_series,
                }
                if variance_series:
                    observable_values["variance"] = float(variance_series[-1])
            elif key == "mean_excited":
                basis_series = _population_series(trace, model_spec)
                mean_series = _mean_excited_series_from_population(basis_series, model_spec)
                metrics_out[name] = {
                    "times": list(trace.times),
                    "values": mean_series,
                }
                if mean_series:
                    observable_values["mean_excited"] = float(mean_series[-1])
            else:
                if key in observable_values:
                    metrics_out[name] = float(observable_values[key])
                elif name in observable_values:
                    metrics_out[name] = float(observable_values[name])

    error_budget = {}
    for key, value in metrics_out.items():
        terminal = _metric_terminal_value(value)
        if terminal is not None:
            error_budget[key] = float(terminal)
    report = Report(
        summary={
            "metrics": list(metrics_out.keys()),
            "metric_mode": "time_series",
            "metric_terminal_values": error_budget,
        },
        error_budget=error_budget,
    )
    return metrics_out, Observables(values=observable_values), report


def run_analysis_stage(*, trace, model_spec, pulse_ir, pulse_cfg: dict | None, cfg, logical_error, analysis_cfg: dict | None):
    """Run observables/report analysis and build sensitivity budgets."""
    stage_timings: dict[str, float] = {}
    t0 = time.perf_counter()
    trace_payload = _resolve_analysis_trace(trace, analysis_cfg)
    metrics_payload, observables_obj, report_obj = _resolve_metric_payload(trace, model_spec, analysis_cfg)
    readout_payload = build_readout_analysis(
        trace=trace,
        model_spec=model_spec,
        pulse_ir=pulse_ir,
        pulse_cfg=pulse_cfg,
        analysis_cfg=analysis_cfg,
        seed=int(getattr(cfg, "seed", 12345)),
    )
    analysis = {
        "trace": trace_payload,
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
