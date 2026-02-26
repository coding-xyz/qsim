from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import importlib.metadata as ilm
import time

import h5py

from qsim.analysis.registry import AnalysisRegistry, AnalysisRunner
from qsim.analysis.error_budget_pauli import build_component_budget, write_component_ablation_csv
from qsim.analysis.pauli_plus import build_component_error_model, run_scaling_sweep
from qsim.analysis.sensitivity import build_error_budget_v2, build_sensitivity_report
from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import dump_backend_config, load_backend_config
from qsim.backend.lowering import DefaultLowering
from qsim.backend.model_build import DefaultModelBuilder
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import DecoderInput, LogicalErrorSummary, Observables, RunManifest, SyndromeFrame, write_json
from qsim.engines.julia_qoptics import JuliaQuantumOpticsEngine
from qsim.engines.julia_qtoolbox import JuliaQuantumToolboxEngine
from qsim.engines.qutip_engine import QuTiPEngine
from qsim.pulse.drawer_adapter import EngineeringDrawer
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trace
from qsim.qec.decoder import build_decoder_report, get_decoder, summarize_logical_error
from qsim.qec.eval import run_decoder_eval, write_decoder_eval_csv, write_failed_tasks_jsonl
from qsim.qec.prior import build_prior_and_report


def _select_engine(name: str):
    """Return an engine instance by user-facing name."""
    key = name.lower()
    if key == "qutip":
        return QuTiPEngine()
    if key in {"julia_qtoolbox", "quantumtoolbox", "julia_quantumtoolbox"}:
        return JuliaQuantumToolboxEngine()
    if key in {"julia_qoptics", "quantumoptics", "julia_quantumoptics"}:
        return JuliaQuantumOpticsEngine()
    return QuTiPEngine()


def _write_trace_h5(trace, out_path: Path) -> Path:
    """Persist a ``Trace`` object into a minimal HDF5 file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w") as h5:
        h5.create_dataset("times", data=trace.times)
        h5.create_dataset("states", data=trace.states)
        h5.attrs["engine"] = trace.engine
    return out_path


def _sha256_text(value: str) -> str:
    """Calculate SHA-256 of UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_pulse_npz_with_fallback(pulse_samples: dict, out: Path) -> Path:
    """Write pulse samples NPZ, falling back to a unique filename if locked."""
    preferred = out / "pulse_samples.npz"
    try:
        return PulseCompiler.to_npz(pulse_samples, preferred)
    except PermissionError:
        # Windows may keep old artifacts locked by notebook/IDE preview.
        stamp = int(time.time() * 1000)
        alt = out / f"pulse_samples_{stamp}.npz"
        return PulseCompiler.to_npz(pulse_samples, alt)


def _resolve_writable_out_dir(preferred: Path) -> Path:
    """Return a writable output directory, falling back if needed."""
    preferred.mkdir(parents=True, exist_ok=True)
    probe = preferred / ".qsim_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return preferred
    except Exception:
        stamp = int(time.time() * 1000)
        alt = preferred.parent / f"{preferred.name}_rerun_{stamp}"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def _build_settings_report(
    backend_path: str,
    cfg,
    hardware: dict | None,
    noise: dict | None,
    model_spec,
    trace,
    selected_engine_name: str,
) -> dict:
    """Build settings_report payload for post-run auditing."""
    payload = model_spec.payload or {}
    return {
        "schema_version": "1.0",
        "workflow": {
            "backend_path": str(Path(backend_path).resolve()),
            "engine_requested": selected_engine_name,
            "engine_used": trace.engine,
            "solver": model_spec.solver,
            "level": cfg.level,
            "backend_noise_mode": cfg.noise,
            "analysis_pipeline": cfg.analysis_pipeline,
            "seed": cfg.seed,
        },
        "model": {
            "model_type": payload.get("model_type", "unknown"),
            "dimension": model_spec.dimension,
            "num_qubits": payload.get("num_qubits"),
            "model_assumptions": payload.get("model_assumptions", {}),
            "truncation": cfg.truncation,
        },
        "inputs": {
            "hardware": hardware or {},
            "noise": noise or {},
        },
        "resolved": {
            "simulation_level": payload.get("simulation_level", "qubit"),
            "qubit_freqs_hz": payload.get("qubit_freqs_hz", []),
            "controls_count": len(payload.get("controls", [])),
            "couplings_count": len(payload.get("couplings", [])),
            "collapse_operator_count": len(payload.get("collapse_operators", [])),
            "noise_summary": payload.get("noise_summary", {}),
        },
        "parameter_mapping": {
            "qasm": "Defines logical gates and order only (x/sx/rz/cx/measure ...).",
            "hardware.simulation_level": "Select physical model level: qubit | nlevel | cqed.",
            "hardware.gate_duration": "Maps each gate to pulse duration in lowering.",
            "hardware.measure_duration": "Maps measure gate to RO pulse length.",
            "hardware.dt": "Simulation time step used by model builder/engine.",
            "hardware.qubit_freqs_hz": "Static drift term in Hamiltonian.",
            "hardware.control_scale": "Amplitude scale for control terms built from pulse samples.",
            "noise.t1/t2/tphi/tup or gamma*": "Converted to per-qubit collapse rates.",
            "noise.model": "Select noise model: markovian_lindblad | one_over_f | ou.",
        },
        "notes": [
            "Tup means upward thermal excitation time constant; gamma_up = 1 / Tup.",
            "Current QuTiP engine supports qubit, nlevel transmon, and cqed (single cavity mode) model types.",
        ],
    }


def run_workflow(
    qasm_text: str,
    backend_path: str,
    out_dir: str,
    hardware: dict | None = None,
    noise: dict | None = None,
    engine: str = "qutip",
    prior_backend: str = "auto",
    decoder: str = "mwpm",
    decoder_options: dict | None = None,
    qec_engine: str = "auto",
    pauli_plus_analysis: bool = False,
    pauli_plus_code_distances: list[int] | None = None,
    pauli_plus_shots: int = 20000,
    decoder_eval: bool = False,
    eval_decoders: list[str] | None = None,
    eval_seeds: list[int] | None = None,
    eval_option_grid: list[dict] | None = None,
    eval_parallelism: int = 1,
    eval_retries: int = 0,
    eval_resume: bool = False,
    persist_artifacts: bool = True,
    export_dxf: bool = True,
) -> dict:
    """Run the full qsim workflow and optionally persist artifacts.

    Args:
        qasm_text: OpenQASM 3 program text.
        backend_path: Path to backend YAML config.
        out_dir: Output directory for generated artifacts.
        hardware: Optional hardware/model override parameters.
        noise: Optional noise override parameters.
        engine: Engine name, e.g. ``qutip``.
        prior_backend: Prior backend selector: ``auto|stim|cirq|mock``.
        decoder: Decoder selector: ``mwpm|bp|mock``.
        decoder_options: Optional decoder runtime options.
        qec_engine: QEC analysis engine selector: ``auto|stim|cirq|mock``.
        pauli_plus_analysis: Enable Pauli+/Kraus-aligned scaling and budget outputs.
        pauli_plus_code_distances: Code distances for scaling report (defaults to ``[3, 5]``).
        pauli_plus_shots: Shots per code distance for Pauli+ simulation.
        decoder_eval: Enable decoder benchmark sweep report generation.
        eval_decoders: Decoder set for evaluation; defaults to ``[decoder, "bp"]``.
        eval_seeds: Seeds for evaluation sweep; defaults to ``[cfg.seed]``.
        eval_option_grid: Hyperparameter option grid for evaluation.
        eval_parallelism: Parallel workers for evaluation tasks.
        eval_retries: Retry count for failed eval tasks.
        eval_resume: Resume from `resume_state.json` if available.
        persist_artifacts: Whether to write artifacts to disk.
        export_dxf: Whether to export DXF timing diagram.

    Returns:
        A result dict containing circuit, model, trace, analysis, and timings.

    Example:
        ```python
        from pathlib import Path
        from qsim.ui.notebook import run_workflow

        result = run_workflow(
            qasm_text=Path("examples/bell.qasm").read_text(encoding="utf-8"),
            backend_path="examples/backend.yaml",
            out_dir="runs/demo_docs",
            engine="qutip",
        )
        print(result["trace"].engine, result["timings"]["total"])
        ```
    """
    t_start = time.perf_counter()
    timings: dict[str, float] = {}

    def _tick(stage: str, t0: float) -> float:
        now = time.perf_counter()
        timings[stage] = now - t0
        return now

    out = _resolve_writable_out_dir(Path(out_dir))

    t0 = time.perf_counter()
    circuit = CircuitAdapter.from_qasm(qasm_text)
    t0 = _tick("qasm_parse", t0)
    cfg = load_backend_config(backend_path)
    t0 = _tick("backend_load", t0)

    normalized, compile_report = CompilePipeline().run(circuit, cfg, hardware=hardware)
    t0 = _tick("compile_pipeline", t0)
    pulse_ir, executable = DefaultLowering().lower(normalized, hw=hardware, cfg=cfg)
    t0 = _tick("lowering", t0)

    pulse_samples = PulseCompiler.compile(pulse_ir, sample_rate=1.0)
    t0 = _tick("pulse_compile", t0)
    pulse_npz = out / "pulse_samples.npz"
    if persist_artifacts:
        pulse_npz = _write_pulse_npz_with_fallback(pulse_samples, out)
    t0 = _tick("pulse_npz_write", t0)

    model_spec = DefaultModelBuilder().build(executable, hw=hardware, noise=noise, pulse_samples=pulse_samples)
    t0 = _tick("model_build", t0)
    selected = _select_engine(engine)
    trace = selected.run(model_spec, run_options={"seed": cfg.seed})
    t0 = _tick("engine_run", t0)

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
    t0 = _tick("decode_run", t0)

    decoder_eval_report = None
    decoder_eval_rows: list[dict] = []
    decoder_eval_batch_manifest = None
    failed_eval_tasks: list[dict] = []
    decoder_eval_resume_state = None
    decoder_eval_table_rel = ""
    if decoder_eval:
        requested_decoders = eval_decoders or [decoder, "bp"]
        # Keep ordering and remove duplicates.
        seen: set[str] = set()
        decs = [d for d in requested_decoders if not (d in seen or seen.add(d))]
        seeds = eval_seeds or [int(cfg.seed)]
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
    t0 = _tick("decoder_eval_run", t0)

    registry = AnalysisRegistry()
    analysis = AnalysisRunner(registry).run(trace, model_spec, pipeline=cfg.analysis_pipeline)
    t0 = _tick("analysis_run", t0)
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
    scaling_report = None
    error_budget_pauli_plus = None
    component_ablation_rel = ""
    component_model: dict[str, float] | None = None
    if pauli_plus_analysis:
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
            seed=int(cfg.seed),
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
                seed=int(cfg.seed),
                options={"error_scale": 1.0, "mode": "component_off", "component": comp},
            )
        scaling_report["ablation_mode"] = "component_off"
        scaling_report["components"] = sorted(component_model.keys())
        error_budget_pauli_plus = build_component_budget(
            baseline_scaling=scaling_report,
            component_model=component_model,
            ablation_scaling=ablation_scaling,
        )
    t0 = _tick("sensitivity_run", t0)
    settings_report = _build_settings_report(
        backend_path=backend_path,
        cfg=cfg,
        hardware=hardware,
        noise=noise,
        model_spec=model_spec,
        trace=trace,
        selected_engine_name=engine,
    )

    if persist_artifacts:
        write_json(out / "circuit.json", asdict(circuit))
        dump_backend_config(cfg, out / "backend_config.json")
        write_json(out / "normalized_circuit.json", asdict(normalized))
        write_json(out / "compile_report.json", compile_report)
        write_json(out / "pulse_ir.json", asdict(pulse_ir))
        write_json(out / "executable_model.json", asdict(executable))
        write_json(out / "model_spec.json", asdict(model_spec))
        _write_trace_h5(trace, out / "trace.h5")
        write_json(out / "observables.json", analysis.get("observables", {}))
        write_json(out / "report.json", analysis.get("report", {}))
        write_json(out / "syndrome_frame.json", asdict(syndrome))
        write_json(out / "prior_model.json", asdict(prior_model))
        write_json(out / "prior_report.json", prior_report)
        write_json(out / "decoder_input.json", asdict(decoder_input))
        write_json(out / "decoder_output.json", asdict(decoder_output))
        write_json(out / "decoder_report.json", decoder_report)
        write_json(out / "logical_error.json", asdict(logical_error))
        write_json(out / "sensitivity_report.json", sensitivity_report)
        write_json(out / "error_budget_v2.json", error_budget_v2)
        if pauli_plus_analysis and scaling_report is not None and error_budget_pauli_plus is not None:
            write_json(out / "scaling_report.json", scaling_report)
            write_json(out / "error_budget_pauli_plus.json", error_budget_pauli_plus)
            if component_model is not None:
                write_component_ablation_csv(
                    component_model=component_model,
                    budget=error_budget_pauli_plus,
                    out_path=out / "component_ablation.csv",
                )
                component_ablation_rel = "component_ablation.csv"
        if decoder_eval and decoder_eval_report is not None:
            write_json(out / "decoder_eval_report.json", decoder_eval_report)
            write_decoder_eval_csv(decoder_eval_rows, out / "decoder_eval_table.csv")
            write_json(out / "batch_manifest.json", decoder_eval_batch_manifest or {"schema_version": "1.0"})
            write_json(out / "resume_state.json", decoder_eval_resume_state or {"schema_version": "1.0"})
            write_failed_tasks_jsonl(failed_eval_tasks, out / "failed_tasks.jsonl")
            decoder_eval_table_rel = "decoder_eval_table.csv"
        write_json(out / "settings_report.json", settings_report)
    t0 = _tick("artifact_write", t0)

    dxf_rel = ""
    if persist_artifacts and export_dxf:
        try:
            EngineeringDrawer.export_dxf(pulse_ir, out / "timing_diagram.dxf", style={"title": "qsim timing"})
            dxf_rel = "timing_diagram.dxf"
        except Exception:
            dxf_rel = ""
    t0 = _tick("dxf_export", t0)

    deps = {}
    for name in ["numpy", "h5py", "PyYAML", "qutip", "qiskit", "ezdxf"]:
        try:
            deps[name] = ilm.version(name)
        except ilm.PackageNotFoundError:
            pass

    manifest = RunManifest(
        run_id=out.name,
        random_seed=cfg.seed,
        inputs={
            "backend": str(Path(backend_path)),
            "qasm_inline": "<inline>",
            "qasm_sha256": _sha256_text(qasm_text),
        },
        outputs={
            "circuit": "circuit.json",
            "backend_config": "backend_config.json",
            "normalized_circuit": "normalized_circuit.json",
            "compile_report": "compile_report.json",
            "pulse_ir": "pulse_ir.json",
            "pulse_samples": str(pulse_npz.name),
            "executable_model": "executable_model.json",
            "model_spec": "model_spec.json",
            "trace": "trace.h5",
            "observables": "observables.json",
            "report": "report.json",
            "syndrome_frame": "syndrome_frame.json",
            "prior_model": "prior_model.json",
            "prior_report": "prior_report.json",
            "decoder_input": "decoder_input.json",
            "decoder_output": "decoder_output.json",
            "decoder_report": "decoder_report.json",
            "logical_error": "logical_error.json",
            "sensitivity_report": "sensitivity_report.json",
            "error_budget_v2": "error_budget_v2.json",
            "settings_report": "settings_report.json",
        },
        dependencies=deps,
    )
    if pauli_plus_analysis and scaling_report is not None and error_budget_pauli_plus is not None:
        manifest.outputs["scaling_report"] = "scaling_report.json"
        manifest.outputs["error_budget_pauli_plus"] = "error_budget_pauli_plus.json"
        if component_ablation_rel:
            manifest.outputs["component_ablation"] = component_ablation_rel
    if decoder_eval and decoder_eval_report is not None:
        manifest.outputs["decoder_eval_report"] = "decoder_eval_report.json"
        manifest.outputs["decoder_eval_table"] = decoder_eval_table_rel or "decoder_eval_table.csv"
        manifest.outputs["batch_manifest"] = "batch_manifest.json"
        manifest.outputs["resume_state"] = "resume_state.json"
        manifest.outputs["failed_tasks"] = "failed_tasks.jsonl"
    if dxf_rel:
        manifest.outputs["timing_diagram"] = dxf_rel

    if persist_artifacts:
        manifest.finalize_digests(out)
        manifest.finalize_dependency_fingerprint()
        write_json(out / "run_manifest.json", manifest.__dict__)
    t0 = _tick("manifest_write", t0)

    timings["total"] = time.perf_counter() - t_start
    if persist_artifacts:
        write_json(out / "timings.json", timings)
    _tick("timings_write", t0)

    return {
        "circuit": circuit,
        "backend_config": cfg,
        "normalized": normalized,
        "pulse_ir": pulse_ir,
        "model_spec": model_spec,
        "trace": trace,
        "syndrome": syndrome,
        "prior_model": prior_model,
        "prior_report": prior_report,
        "decoder_input": decoder_input,
        "decoder_output": decoder_output,
        "decoder_report": decoder_report,
        "logical_error": logical_error,
        "sensitivity_report": sensitivity_report,
        "error_budget_v2": error_budget_v2,
        "scaling_report": scaling_report,
        "error_budget_pauli_plus": error_budget_pauli_plus,
        "component_ablation": component_ablation_rel,
        "decoder_eval_report": decoder_eval_report,
        "decoder_eval_batch_manifest": decoder_eval_batch_manifest,
        "decoder_eval_resume_state": decoder_eval_resume_state,
        "failed_eval_tasks": failed_eval_tasks,
        "analysis": analysis,
        "settings": settings_report,
        "out_dir": str(out),
        "timings": timings,
    }


def plot_default(result: dict) -> dict:
    """Create default plotting bundle from ``run_workflow`` result.

    Returns a dict containing matplotlib figures with keys:
    ``pulses``, ``trace``, and ``report``.
    """
    return {
        "pulses": plot_pulses(result["pulse_ir"]),
        "trace": plot_trace(result["trace"]),
        "report": plot_report(result["analysis"].get("report", {})),
    }
