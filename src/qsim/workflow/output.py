"""Output helpers for workflow artifacts and visualization."""

from __future__ import annotations

from pathlib import Path
import hashlib
import time

import h5py

from qsim.circuit.import_qasm import CircuitAdapter
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.visualize import plot_pulses, plot_report, plot_trace


def write_trace_h5(trace, out_path: Path) -> Path:
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
    trace,
    analysis: dict,
    out: Path,
    *,
    export_dxf: bool,
    selected_outputs: set[str] | None = None,
) -> dict[str, str]:
    """Export pulse/trace/report figures and return produced filename map."""
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

    if allow is None or "trace_plot" in allow:
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
    noise: dict | None,
    model_spec,
    trace,
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
    payload = model_spec.payload or {}
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
            "device": device or {},
            "pulse": pulse or {},
            "frame": frame or {},
            "solver_run": solver_run or {},
            "noise": noise or {},
        },
        "resolved": {
            "simulation_level": payload.get("simulation_level", "qubit"),
            "qubit_freqs_Hz": payload.get("qubit_freqs_Hz", []),
            "qubit_omega_rad_s": payload.get("qubit_omega_rad_s", []),
            "controls_count": len(payload.get("controls", [])),
            "couplings_count": len(payload.get("couplings", [])),
            "collapse_operator_count": len(payload.get("collapse_operators", [])),
            "noise_summary": payload.get("noise_summary", {}),
        },
        "parameter_mapping": {
            "qasm": "Defines logical gates and order only (x/sx/rz/cx/measure ...).",
            "device.qubits[].freq_Hz": "Per-qubit lab-frame transition frequency (Hz).",
            "device.qubits[].anharmonicity_Hz": "Per-qubit anharmonicity used by nlevel/cqed models (Hz).",
            "device.simulation_level": "Select physical model level: qubit | nlevel | cqed.",
            "device.qubit_freqs_Hz": "Optional normalized qubit frequencies in the lab frame (Hz).",
            "device.control_scale": "Amplitude scale for control terms built from pulse samples.",
            "pulse.gate_duration_ns": "Maps each gate to pulse duration in lowering (ns).",
            "pulse.measure_duration_ns": "Maps measure gate to RO pulse length (ns).",
            "pulse.xy_freq_Hz": "Default microwave carrier used for XY pulse generation (Hz).",
            "pulse.ro_freq_Hz": "Default readout carrier used for RO pulse generation (Hz).",
            "pulse.schedule_policy": "Lowering schedule policy: serial | parallel | hybrid.",
            "pulse.reset_feedback_policy": "Reset feedback scheduling: parallel | serial_global.",
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
    "write_trace_h5",
]
