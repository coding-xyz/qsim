"""Output helpers for workflow artifacts and visualization."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import time

import h5py

from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import json_safe
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trajectory


def _jsonable(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return json_safe(value)


def write_trajectory_h5(trajectory, out_path: Path) -> Path:
    """Persist a ``Trajectory`` object into an HDF5 file with structured metadata."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(out_path, "w") as h5:
        h5.create_dataset("times", data=trajectory.times)
        h5.attrs["engine"] = trajectory.engine
        h5.attrs["trajectory_schema_version"] = getattr(trajectory, "schema_version", "1.0")
        metadata = dict(getattr(trajectory, "metadata", {}) or {})
        wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
        density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
        classical = dict(getattr(trajectory, "classical", {}) or {})
        measurements = dict(getattr(trajectory, "measurements", {}) or {})
        for key in ("num_qubits", "model_dimension"):
            value = metadata.get(key, None)
            if value is not None:
                h5.attrs[key] = value
        if metadata:
            metadata_json = json.dumps(_jsonable(metadata), ensure_ascii=False)
            h5.create_dataset("metadata_json", data=metadata_json, dtype=h5py.string_dtype(encoding="utf-8"))
        if wave_function:
            wave_function_json = json.dumps(_jsonable(wave_function), ensure_ascii=False)
            h5.create_dataset("wave_function_json", data=wave_function_json, dtype=h5py.string_dtype(encoding="utf-8"))
        if density_matrix:
            density_matrix_json = json.dumps(_jsonable(density_matrix), ensure_ascii=False)
            h5.create_dataset("density_matrix_json", data=density_matrix_json, dtype=h5py.string_dtype(encoding="utf-8"))
        if classical:
            classical_json = json.dumps(_jsonable(classical), ensure_ascii=False)
            h5.create_dataset("classical_json", data=classical_json, dtype=h5py.string_dtype(encoding="utf-8"))
        if measurements:
            measurements_json = json.dumps(_jsonable(measurements), ensure_ascii=False)
            h5.create_dataset("measurements_json", data=measurements_json, dtype=h5py.string_dtype(encoding="utf-8"))
    return out_path


def sha256_text(value: str) -> str:
    """Calculate SHA-256 of UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_pulse_npz_with_fallback(pulse_samples: dict, out: Path) -> Path:
    """Write pulse samples NPZ, falling back to a unique filename if locked."""
    preferred = out / "pulse_samples.npz"
    try:
        return PulseCompiler.to_npz(pulse_samples, preferred)
    except PermissionError:
        # Windows may keep old artifacts locked by notebook/IDE preview.
        stamp = int(time.time() * 1000)
        alt = out / f"pulse_samples_{stamp}.npz"
        return PulseCompiler.to_npz(pulse_samples, alt)


def resolve_writable_out_dir(preferred: Path) -> Path:
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


def export_circuit_diagram(circuit, out: Path) -> str:
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


def export_result_figures(
    pulse_ir,
    trajectory,
    analysis: dict,
    out: Path,
    *,
    export_dxf: bool,
    selected_outputs: set[str] | None = None,
) -> dict[str, str]:
    """Export pulse/trajectory/report figures and return produced filename map."""
    outputs: dict[str, str] = {}
    allow = selected_outputs
    need_pulse = allow is None or "pulse_timing" in allow
    need_dxf = export_dxf and (allow is None or "timing_diagram" in allow)
    if need_pulse or need_dxf:
        try:
            fig = plot_pulses(
                pulse_ir,
                timing_layout=True,
                show_clock=True,
                png_path=(out / "pulse_timing.png") if need_pulse else None,
                dxf_path=(out / "timing_diagram.dxf") if need_dxf else None,
            )
            if need_pulse:
                outputs["pulse_timing"] = "pulse_timing.png"
            if need_dxf:
                outputs["timing_diagram"] = "timing_diagram.dxf"
            try:
                import matplotlib.pyplot as plt

                plt.close(fig)
            except Exception:
                pass
        except Exception:
            pass

    if allow is None or "trajectory_plot" in allow:
        try:
            fig = plot_trajectory(trajectory)
            fig.savefig(out / "trajectory.png", dpi=180)
            outputs["trajectory_plot"] = "trajectory.png"
            try:
                import matplotlib.pyplot as plt

                plt.close(fig)
            except Exception:
                pass
        except Exception:
            pass

    if allow is None or "report_plot" in allow:
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


def build_settings_report(
    backend_path: str,
    cfg,
    device: dict | None,
    pulse: dict | None,
    frame: dict | None,
    analyser: dict | None,
    study: list[dict] | None,
    primary_step: dict | None,
    noise: dict | None,
    model_spec,
    trajectory,
    selected_engine_name: str,
    solver_mode: str | None,
    solver_run: dict | None,
    param_bindings: dict | None,
    allow_mock_fallback: bool,
    compare_engines: list[str] | None,
    julia_bin: str | None,
    julia_depot_path: str | None,
    julia_timeout_s: float,
    mcwf_ntraj: int,
) -> dict:
    """Build settings_report payload for post-run auditing."""
    backend_path_value = str(backend_path or "")
    if backend_path_value.startswith("<") and backend_path_value.endswith(">"):
        backend_repr = backend_path_value
    else:
        backend_repr = str(Path(backend_path_value).resolve()) if backend_path_value else ""
    return {
        "schema_version": "1.0",
        "workflow": {
            "backend_path": backend_repr,
            "engine_requested": selected_engine_name,
            "engine_used": trajectory.engine,
            "solver": model_spec.solver_mode,
            "solver_mode_requested": (solver_mode or "").lower(),
            "allow_mock_fallback": bool(allow_mock_fallback),
            "compare_engines_requested": list(compare_engines or []),
            "julia_bin": str(julia_bin or ""),
            "julia_depot_path": str(julia_depot_path or ""),
            "julia_timeout_s": float(julia_timeout_s),
            "mcwf_ntraj": int(max(1, mcwf_ntraj)),
            "level": cfg.level,
            "backend_noise_mode": cfg.noise,
            "analysis_pipeline": getattr(cfg, "analysis", cfg.analysis_pipeline),
            "seed": cfg.seed,
            "param_bindings": dict(param_bindings or {}),
        },
        "model": {
            "model_type": model_spec.system.model_type,
            "dimension": model_spec.dimension,
            "num_qubits": model_spec.system.num_qubits,
            "study_summary": dict(model_spec.study.summary if model_spec.study else {}),
            "model_assumptions": dict(model_spec.system.assumptions),
            "truncation": cfg.truncation,
        },
        "inputs": {
            "device": device or {},
            "pulse": pulse or {},
            "frame": frame or {},
            "analyser": analyser or {},
            "study": list(study or []),
            "primary_step": dict(primary_step or {}),
            "solver_run": solver_run or {},
            "noise": noise or {},
        },
        "runtime": {
            "simulation_level": model_spec.system.simulation_level,
            "qubit_freqs_Hz": list(model_spec.system.qubit_freqs_Hz),
            "qubit_omega_rad_s": list(model_spec.system.qubit_omega_rad_s),
            "controls_count": len(model_spec.hamiltonian.control_terms),
            "couplings_count": len(model_spec.hamiltonian.coupling_terms),
            "collapse_operator_count": len(model_spec.noise.collapse_channels),
            "readout_lines": [line.to_dict() for line in model_spec.readout.lines] if model_spec.readout else [],
            "noise_summary": {
                "selected_model": model_spec.noise.selected_model,
                "sources": [source.to_dict() for source in model_spec.noise.sources],
                "realizations": list(model_spec.noise.realizations),
                "control_crosstalk": [item.to_dict() for item in model_spec.noise.control_crosstalk],
                "readout_crosstalk": [item.to_dict() for item in model_spec.noise.readout_crosstalk],
                "supported": list(model_spec.noise.supported),
                "unsupported": list(model_spec.noise.unsupported),
                "warnings": list(model_spec.noise.warnings),
            },
        },
        "parameter_mapping": {
            "qasm": "Defines logical gates and order only (x/sx/rz/cx/measure ...).",
            "device.qubits[].freq_Hz": "Per-qubit lab-frame transition frequency (Hz).",
            "device.qubits[].anharmonicity_Hz": "Per-qubit anharmonicity used by nlevel/cqed models (Hz).",
            "device.components / device.connections": "Composite schema entrypoint for subsystem-based models.",
            "runtime.simulation_level": "Internal runtime level inferred from the device model for the current engine.",
            "device.qubit_freqs_Hz": "Optional normalized qubit frequencies in the lab frame (Hz).",
            "device.control_scale": "Amplitude scale for control terms built from pulse samples.",
            "pulse.gate_duration_ns": "Maps each gate to pulse duration in lowering (ns).",
            "pulse.measure_duration_ns": "Maps measure gate to RO pulse length (ns).",
            "pulse.measure_amp": "Maps measure gate to RO pulse amplitude used by lowering.",
            "pulse.xy_freq_Hz": "Default microwave carrier used for XY pulse generation (Hz).",
            "pulse.ro_freq_Hz": "Default readout carrier used for RO pulse generation (Hz).",
            "pulse.schedule": "Lowering schedule policy: serial | parallel | hybrid.",
            "pulse.reset_feedback_policy": "Reset feedback scheduling: parallel | serial_global.",
            "solver.study": "Ordered study steps used to pick the active runtime step and to describe postprocessing stages.",
            "solver.run.dt_s": "Simulation time step used by model builder/engine (s).",
            "solver.run.t_end_s": "Explicit solver stop time in seconds; overrides pulse-derived duration.",
            "solver.run.t_padding_s": "Extra padding added to inferred pulse end time when t_end_s is omitted.",
            "frame.mode": "Reference-frame mode: rotating | lab.",
            "frame.reference": "Reference frequency source: pulse_carrier | explicit | none.",
            "frame.rwa": "Enable rotating-wave approximation for XY drives.",
            "frame.qubit_reference_freqs_Hz": "Explicit per-qubit reference frequencies used when frame.reference=explicit.",
            "noise.T1_s/T2_s/Tphi_s/Tup_s or gamma*_Hz": "Converted to internal angular-rate Lindblad coefficients (rad/s).",
            "noise.model": "Select noise model: markovian_lindblad | one_over_f | ou.",
        },
        "notes": [
            "Tup means upward thermal excitation time constant; gamma_up = 1 / Tup.",
            "Current QuTiP engine supports qubit, nlevel transmon, and cqed (single cavity mode) model types.",
        ],
    }


__all__ = [
    "build_settings_report",
    "export_circuit_diagram",
    "export_result_figures",
    "resolve_writable_out_dir",
    "sha256_text",
    "write_pulse_npz_with_fallback",
    "write_trajectory_h5",
]

