from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import importlib.metadata as ilm
import time

import h5py

from qsim.analysis.registry import AnalysisRegistry, AnalysisRunner
from qsim.backend.compile_pipeline import CompilePipeline
from qsim.backend.config import dump_backend_config, load_backend_config
from qsim.backend.lowering import DefaultLowering
from qsim.backend.model_build import DefaultModelBuilder
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import RunManifest, write_json
from qsim.engines.julia_qoptics import JuliaQuantumOpticsEngine
from qsim.engines.julia_qtoolbox import JuliaQuantumToolboxEngine
from qsim.engines.qutip_engine import QuTiPEngine
from qsim.pulse.drawer_adapter import EngineeringDrawer
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trace


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

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

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
        pulse_npz = PulseCompiler.to_npz(pulse_samples, pulse_npz)
    t0 = _tick("pulse_npz_write", t0)

    model_spec = DefaultModelBuilder().build(executable, hw=hardware, noise=noise, pulse_samples=pulse_samples)
    t0 = _tick("model_build", t0)
    selected = _select_engine(engine)
    trace = selected.run(model_spec, run_options={"seed": cfg.seed})
    t0 = _tick("engine_run", t0)

    registry = AnalysisRegistry()
    analysis = AnalysisRunner(registry).run(trace, model_spec, pipeline=cfg.analysis_pipeline)
    t0 = _tick("analysis_run", t0)
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
            "settings_report": "settings_report.json",
        },
        dependencies=deps,
    )
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
