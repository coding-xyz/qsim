"""Core workflow stages (mandatory execution path)."""

from __future__ import annotations

import time

from qsim.analysis.registry import AnalysisRegistry, AnalysisRunner
from qsim.analysis.sensitivity import build_error_budget_v2, build_sensitivity_report
from qsim.analysis.trace_semantics import annotate_trace_metadata
from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import load_backend_config
from qsim.backend.lowering import DefaultLowering
from qsim.backend.model_build import DefaultModelBuilder
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import DecoderInput, LogicalErrorSummary, Observables, SyndromeFrame
from qsim.pulse.sequence import PulseCompiler
from qsim.qec.decoder import build_decoder_report, get_decoder, summarize_logical_error
from qsim.qec.prior import build_prior_and_report
from qsim.workflow.engines import select_engine
from qsim.workflow.output import write_pulse_npz_with_fallback


def parse_compile_lower_model(
    *,
    qasm_text: str,
    backend_path: str | None,
    backend_config=None,
    out,
    hardware: dict | None,
    schedule_policy: str | None,
    reset_feedback_policy: str | None,
    noise: dict | None,
    solver_mode: str | None,
    param_bindings: dict[str, float] | None,
    persist_artifacts: bool,
):
    """Parse input and build simulation model artifacts."""
    stage_timings: dict[str, float] = {}
    t0 = time.perf_counter()
    circuit = CircuitAdapter.from_qasm(qasm_text, param_bindings=param_bindings)
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

    lowering_hw = dict(hardware or {})
    if schedule_policy is not None:
        lowering_hw["schedule_policy"] = str(schedule_policy).strip().lower()
    if reset_feedback_policy is not None:
        lowering_hw["reset_feedback_policy"] = str(reset_feedback_policy).strip().lower()

    normalized, compile_report = CompilePipeline().run(circuit, cfg, hardware=lowering_hw)
    t3 = time.perf_counter()
    stage_timings["compile_pipeline"] = t3 - t2
    pulse_ir, executable = DefaultLowering().lower(normalized, hw=lowering_hw, cfg=cfg)
    t4 = time.perf_counter()
    stage_timings["lowering"] = t4 - t3

    pulse_samples = PulseCompiler.compile(pulse_ir, sample_rate=1.0)
    t5 = time.perf_counter()
    stage_timings["pulse_compile"] = t5 - t4
    pulse_npz = out / "pulse_samples.npz"
    if persist_artifacts:
        pulse_npz = write_pulse_npz_with_fallback(pulse_samples, out)
    t6 = time.perf_counter()
    stage_timings["pulse_npz_write"] = t6 - t5

    model_spec = DefaultModelBuilder().build(executable, hw=lowering_hw, noise=noise, pulse_samples=pulse_samples)
    if solver_mode:
        model_spec.solver = str(solver_mode).strip().lower()
    t7 = time.perf_counter()
    stage_timings["model_build"] = t7 - t6

    return {
        "circuit": circuit,
        "cfg": cfg,
        "lowering_hw": lowering_hw,
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


def run_analysis_stage(*, trace, model_spec, cfg, logical_error):
    """Run observables/report analysis and build sensitivity budgets."""
    stage_timings: dict[str, float] = {}
    t0 = time.perf_counter()
    registry = AnalysisRegistry()
    analysis = AnalysisRunner(registry).run(trace, model_spec, pipeline=cfg.analysis_pipeline)
    t1 = time.perf_counter()
    stage_timings["analysis_run"] = t1 - t0

    obs_payload = analysis.get("observables", {}) if isinstance(analysis, dict) else {}
    observables_obj = Observables(
        schema_version=str(obs_payload.get("schema_version", "1.0")),
        values=dict(obs_payload.get("values", {})),
    )
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
