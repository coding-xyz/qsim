"""Notebook-oriented workflow orchestration and artifact export helpers."""

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
from qsim.analysis.sensitivity import build_error_budget_v2, build_sensitivity_report, write_sensitivity_heatmap
from qsim.analysis.trace_semantics import annotate_trace_metadata, pointwise_compare_compatibility, state_encoding
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
from qsim.qec.eval import run_decoder_eval, write_decoder_eval_csv, write_decoder_pareto_png, write_failed_tasks_jsonl
from qsim.qec.prior import build_prior_and_report, write_prior_samples_npz


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


def _canonical_engine_name(name: str) -> str:
    key = str(name).strip().lower()
    if key in {"julia_qtoolbox", "quantumtoolbox", "julia_quantumtoolbox"}:
        return "julia_qtoolbox"
    if key in {"julia_qoptics", "quantumoptics", "julia_quantumoptics"}:
        return "julia_qoptics"
    if key == "qutip":
        return "qutip"
    return key


def _trace_summary(trace) -> dict:
    last = trace.states[-1] if trace.states else []
    final_mean = float(sum(last) / len(last)) if last else 0.0
    return {
        "engine": trace.engine,
        "samples": len(trace.times),
        "state_dim": len(last),
        "final_state": [float(v) for v in last],
        "final_mean": final_mean,
        "state_encoding": state_encoding(trace),
        "metadata": dict(getattr(trace, "metadata", {}) or {}),
    }


def _trace_pair_metrics(ref, other) -> dict:
    comparable, reason = pointwise_compare_compatibility(ref, other)
    if not comparable:
        return {
            "comparable": False,
            "reason": reason,
            "samples_compared": 0,
        }
    n = min(len(ref.times), len(other.times))
    if n <= 0:
        return {"comparable": True, "samples_compared": 0, "mse": 0.0, "mae": 0.0}
    d = 0
    if ref.states and other.states:
        d = min(len(ref.states[0]), len(other.states[0]))
    if d <= 0:
        return {"comparable": True, "samples_compared": n, "mse": 0.0, "mae": 0.0}
    sq_sum = 0.0
    abs_sum = 0.0
    count = 0
    for i in range(n):
        ra = ref.states[i]
        rb = other.states[i]
        for j in range(d):
            dv = float(ra[j]) - float(rb[j])
            sq_sum += dv * dv
            abs_sum += abs(dv)
            count += 1
    if count <= 0:
        return {"samples_compared": n, "mse": 0.0, "mae": 0.0}
    return {
        "comparable": True,
        "samples_compared": n,
        "state_dim_compared": d,
        "mse": float(sq_sum / count),
        "mae": float(abs_sum / count),
    }


def _run_cross_engine_compare(
    model_spec,
    *,
    engines: list[str],
    seed: int,
    allow_mock_fallback: bool,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
) -> dict:
    """Run model on selected engines and build a compact consistency report."""
    selected: list[str] = []
    seen: set[str] = set()
    for name in engines:
        k = _canonical_engine_name(name)
        if k and k not in seen:
            selected.append(k)
            seen.add(k)
    if not selected:
        return {"schema_version": "1.0", "status": "empty", "runs": [], "pairwise": []}

    runs: list[dict] = []
    traces = []
    for name in selected:
        engine = _select_engine(name)
        run_opts = {
            "seed": int(seed),
            "solver_mode": model_spec.solver,
            "allow_mock_fallback": bool(allow_mock_fallback),
            "julia_timeout_s": float(julia_timeout_s),
            "ntraj": int(max(1, mcwf_ntraj)),
        }
        if julia_bin:
            run_opts["julia_bin"] = str(julia_bin)
        if julia_depot_path:
            run_opts["julia_depot_path"] = str(julia_depot_path)
        trace = engine.run(
            model_spec,
            run_options=run_opts,
        )
        annotate_trace_metadata(
            trace,
            num_qubits=int(model_spec.payload.get("num_qubits", 0) or 0) or None,
            dimension=int(getattr(model_spec, "dimension", 0) or 0) or None,
            engine_name=name,
        )
        traces.append((name, trace))
        item = _trace_summary(trace)
        item["requested_engine"] = name
        runs.append(item)

    baseline_name, baseline_trace = traces[0]
    pairwise = []
    for name, trace in traces[1:]:
        pairwise.append(
            {
                "ref_engine": baseline_name,
                "other_engine": name,
                **_trace_pair_metrics(baseline_trace, trace),
            }
        )

    return {
        "schema_version": "1.0",
        "status": "ok",
        "solver_mode": str(model_spec.solver),
        "baseline_engine": baseline_name,
        "runs": runs,
        "pairwise": pairwise,
    }


def _write_trace_h5(trace, out_path: Path) -> Path:
    """Persist a ``Trace`` object into a minimal HDF5 file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w") as h5:
        h5.create_dataset("times", data=trace.times)
        h5.create_dataset("states", data=trace.states)
        h5.attrs["engine"] = trace.engine
        metadata = dict(getattr(trace, "metadata", {}) or {})
        for key in ("state_encoding", "num_qubits", "model_dimension"):
            value = metadata.get(key, None)
            if value is not None:
                h5.attrs[key] = value
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


def _export_circuit_diagram(circuit, out: Path) -> str:
    """Export Qiskit-backed circuit diagram as PNG; return relative filename or empty."""
    try:
        qc = CircuitAdapter.to_qiskit(circuit)
        fig = qc.draw(output="mpl")
        out_path = out / "circuit_diagram.png"
        fig.savefig(out_path, dpi=180)
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:
            pass
        return out_path.name
    except Exception:
        return ""


def _export_result_figures(pulse_ir, trace, analysis: dict, out: Path, *, export_dxf: bool) -> dict[str, str]:
    """Export pulse/trace/report figures and return produced filename map."""
    outputs: dict[str, str] = {}
    try:
        fig = plot_pulses(
            pulse_ir,
            timing_layout=True,
            show_clock=True,
            png_path=out / "pulse_timing.png",
            dxf_path=(out / "timing_diagram.dxf") if export_dxf else None,
        )
        outputs["pulse_timing"] = "pulse_timing.png"
        if export_dxf:
            outputs["timing_diagram"] = "timing_diagram.dxf"
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:
            pass
    except Exception:
        pass

    try:
        fig = plot_trace(trace)
        fig.savefig(out / "trace.png", dpi=180)
        outputs["trace_plot"] = "trace.png"
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:
            pass
    except Exception:
        pass

    try:
        fig = plot_report(analysis.get("report", {}))
        fig.savefig(out / "report.png", dpi=180)
        outputs["report_plot"] = "report.png"
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:
            pass
    except Exception:
        pass

    return outputs


def _build_settings_report(
    backend_path: str,
    cfg,
    hardware: dict | None,
    noise: dict | None,
    model_spec,
    trace,
    selected_engine_name: str,
    solver_mode: str | None,
    param_bindings: dict | None,
    allow_mock_fallback: bool,
    compare_engines: list[str] | None,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
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
            "solver_mode_requested": (solver_mode or "").lower(),
            "allow_mock_fallback": bool(allow_mock_fallback),
            "compare_engines_requested": list(compare_engines or []),
            "julia_bin": str(julia_bin or ""),
            "julia_depot_path": str(julia_depot_path or ""),
            "julia_timeout_s": float(julia_timeout_s),
            "mcwf_ntraj": int(max(1, mcwf_ntraj)),
            "level": cfg.level,
            "backend_noise_mode": cfg.noise,
            "analysis_pipeline": cfg.analysis_pipeline,
            "seed": cfg.seed,
            "param_bindings": dict(param_bindings or {}),
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
            "hardware.schedule_policy": "Lowering schedule policy: serial | parallel | hybrid.",
            "hardware.reset_feedback_policy": "Reset feedback scheduling: parallel | serial_global.",
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


def _collect_runtime_dependencies(trace, selected_engine_name: str) -> dict[str, str]:
    """Extract runtime dependency details from engine trace metadata."""
    deps: dict[str, str] = {}
    meta = dict(getattr(trace, "metadata", {}) or {})
    if str(selected_engine_name).lower().startswith("julia") or str(trace.engine).lower().startswith("julia"):
        julia_ver = str(meta.get("julia_version", "")).strip()
        backend = str(meta.get("julia_backend", "")).strip()
        backend_ver = str(meta.get("julia_backend_version", "")).strip()
        if julia_ver:
            deps["julia"] = julia_ver
        if backend:
            deps[f"julia_backend:{backend}"] = backend_ver or "unknown"
    return deps


def run_workflow(
    qasm_text: str,
    backend_path: str,
    out_dir: str,
    hardware: dict | None = None,
    schedule_policy: str | None = None,
    reset_feedback_policy: str | None = None,
    noise: dict | None = None,
    engine: str = "qutip",
    solver_mode: str | None = None,
    param_bindings: dict[str, float] | None = None,
    compare_engines: list[str] | None = None,
    allow_mock_fallback: bool = False,
    julia_bin: str | None = None,
    julia_depot_path: str | None = None,
    julia_timeout_s: float = 120.0,
    mcwf_ntraj: int = 128,
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
    export_plots: bool = True,
) -> dict:
    """Run the full qsim workflow and optionally persist artifacts.

    Args:
        qasm_text: OpenQASM 3 program text.
        backend_path: Path to backend YAML config.
        out_dir: Output directory for generated artifacts.
        hardware: Optional hardware/model override parameters.
        schedule_policy: Optional lowering schedule policy: ``serial|parallel|hybrid``.
        reset_feedback_policy: Optional reset feedback policy: ``parallel|serial_global``.
        noise: Optional noise override parameters.
        engine: Engine name, e.g. ``qutip``.
        solver_mode: Optional solver override: ``se|me|mcwf``.
        param_bindings: Optional parameter bindings for OpenQASM expressions.
        compare_engines: Optional engine list for cross-engine compare artifact.
        allow_mock_fallback: Whether Julia engines may fallback to mock output.
        julia_bin: Optional explicit Julia executable path.
        julia_depot_path: Optional Julia depot path for package environment.
        julia_timeout_s: Julia subprocess timeout in seconds.
        mcwf_ntraj: MCWF trajectories for engines that support trajectory solvers.
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
        export_plots: Whether to export PNG figures for circuit/pulse/trace/report.

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
    circuit = CircuitAdapter.from_qasm(qasm_text, param_bindings=param_bindings)
    t0 = _tick("qasm_parse", t0)
    cfg = load_backend_config(backend_path)
    t0 = _tick("backend_load", t0)

    lowering_hw = dict(hardware or {})
    if schedule_policy is not None:
        lowering_hw["schedule_policy"] = str(schedule_policy).strip().lower()
    if reset_feedback_policy is not None:
        lowering_hw["reset_feedback_policy"] = str(reset_feedback_policy).strip().lower()

    normalized, compile_report = CompilePipeline().run(circuit, cfg, hardware=lowering_hw)
    t0 = _tick("compile_pipeline", t0)
    pulse_ir, executable = DefaultLowering().lower(normalized, hw=lowering_hw, cfg=cfg)
    t0 = _tick("lowering", t0)

    pulse_samples = PulseCompiler.compile(pulse_ir, sample_rate=1.0)
    t0 = _tick("pulse_compile", t0)
    pulse_npz = out / "pulse_samples.npz"
    if persist_artifacts:
        pulse_npz = _write_pulse_npz_with_fallback(pulse_samples, out)
    t0 = _tick("pulse_npz_write", t0)

    model_spec = DefaultModelBuilder().build(executable, hw=lowering_hw, noise=noise, pulse_samples=pulse_samples)
    if solver_mode:
        model_spec.solver = str(solver_mode).strip().lower()
    t0 = _tick("model_build", t0)
    selected = _select_engine(engine)
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
    prior_samples_rel = "prior_samples.npz"
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
    cross_engine_compare = None
    if compare_engines:
        cross_engine_compare = _run_cross_engine_compare(
            model_spec,
            engines=[engine, *list(compare_engines)],
            seed=int(cfg.seed),
            allow_mock_fallback=bool(allow_mock_fallback),
            julia_bin=julia_bin,
            julia_depot_path=julia_depot_path,
            julia_timeout_s=float(julia_timeout_s),
            mcwf_ntraj=int(max(1, mcwf_ntraj)),
        )
    t0 = _tick("cross_engine_compare", t0)
    settings_report = _build_settings_report(
        backend_path=backend_path,
        cfg=cfg,
        hardware=lowering_hw,
        noise=noise,
        model_spec=model_spec,
        trace=trace,
        selected_engine_name=engine,
        solver_mode=solver_mode,
        param_bindings=param_bindings,
        allow_mock_fallback=allow_mock_fallback,
        compare_engines=compare_engines,
        julia_bin=julia_bin,
        julia_depot_path=julia_depot_path,
        julia_timeout_s=julia_timeout_s,
        mcwf_ntraj=mcwf_ntraj,
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
        write_prior_samples_npz(prior_model, out / prior_samples_rel)
        write_json(out / "decoder_input.json", asdict(decoder_input))
        write_json(out / "decoder_output.json", asdict(decoder_output))
        write_json(out / "decoder_report.json", decoder_report)
        write_json(out / "logical_error.json", asdict(logical_error))
        write_json(out / "sensitivity_report.json", sensitivity_report)
        write_json(out / "error_budget_v2.json", error_budget_v2)
        write_sensitivity_heatmap(sensitivity_report, out / "figures" / "sensitivity_heatmap.png")
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
            write_decoder_pareto_png(decoder_eval_report, out / "figures" / "decoder_pareto.png")
            write_json(out / "batch_manifest.json", decoder_eval_batch_manifest or {"schema_version": "1.0"})
            write_json(out / "resume_state.json", decoder_eval_resume_state or {"schema_version": "1.0"})
            write_failed_tasks_jsonl(failed_eval_tasks, out / "failed_tasks.jsonl")
            decoder_eval_table_rel = "decoder_eval_table.csv"
        write_json(out / "settings_report.json", settings_report)
        if cross_engine_compare is not None:
            write_json(out / "cross_engine_compare.json", cross_engine_compare)
    t0 = _tick("artifact_write", t0)

    viz_outputs: dict[str, str] = {}
    if persist_artifacts and export_plots:
        circuit_png = _export_circuit_diagram(circuit, out)
        if circuit_png:
            viz_outputs["circuit_diagram"] = circuit_png
        viz_outputs.update(_export_result_figures(pulse_ir, trace, analysis, out, export_dxf=export_dxf))
    elif persist_artifacts and export_dxf:
        try:
            EngineeringDrawer.export_dxf(pulse_ir, out / "timing_diagram.dxf", style={"title": "qsim timing"})
            viz_outputs["timing_diagram"] = "timing_diagram.dxf"
        except Exception:
            pass
    t0 = _tick("viz_export", t0)

    deps = {}
    for name in ["numpy", "h5py", "PyYAML", "qutip", "qiskit", "ezdxf"]:
        try:
            deps[name] = ilm.version(name)
        except ilm.PackageNotFoundError:
            pass
    deps.update(_collect_runtime_dependencies(trace, engine))

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
            "prior_samples": prior_samples_rel,
            "decoder_input": "decoder_input.json",
            "decoder_output": "decoder_output.json",
            "decoder_report": "decoder_report.json",
            "logical_error": "logical_error.json",
            "sensitivity_report": "sensitivity_report.json",
            "error_budget_v2": "error_budget_v2.json",
            "sensitivity_heatmap": "figures/sensitivity_heatmap.png",
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
        manifest.outputs["decoder_pareto"] = "figures/decoder_pareto.png"
        manifest.outputs["batch_manifest"] = "batch_manifest.json"
        manifest.outputs["resume_state"] = "resume_state.json"
        manifest.outputs["failed_tasks"] = "failed_tasks.jsonl"
    for key, rel in viz_outputs.items():
        manifest.outputs[key] = rel
    if cross_engine_compare is not None:
        manifest.outputs["cross_engine_compare"] = "cross_engine_compare.json"

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
        "cross_engine_compare": cross_engine_compare,
        "param_bindings": dict(param_bindings or {}),
        "solver_mode": model_spec.solver,
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
