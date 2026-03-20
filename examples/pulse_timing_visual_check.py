from __future__ import annotations

from pathlib import Path

from qsim.pulse.visualize import (
    auto_fold_long_pulses,
    make_timing_theme,
    plot_pulses,
    pulse_ir_from_qasm,
    reorder_xy_z_channels,
)


def _write_case_inputs(case_dir: Path, qasm_text: str, backend_yaml_text: str) -> tuple[Path, Path]:
    qasm_path = case_dir / "input.qasm"
    backend_path = case_dir / "backend.yaml"
    qasm_path.write_text(qasm_text, encoding="utf-8")
    backend_path.write_text(backend_yaml_text, encoding="utf-8")
    return qasm_path, backend_path


def _build_cpmg_qasm() -> str:
    return """OPENQASM 3;
qubit[1] q;
bit[1] c;
x q[0];
x q[0];
x q[0];
x q[0];
x q[0];
x q[0];
measure q[0] -> c[0];
"""


def _build_ghz_qasm() -> str:
    return """OPENQASM 3;
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
cx q[1], q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
"""


def _backend_yaml() -> str:
    return """level: qubit
noise: deterministic
solver: se
analysis_pipeline: default
seed: 1234
"""


def generate_case(case_name: str, qasm_text: str, out_dir: Path) -> None:
    case_dir = out_dir / case_name
    case_dir.mkdir(parents=True, exist_ok=True)
    qasm_path, backend_path = _write_case_inputs(case_dir, qasm_text, _backend_yaml())

    pulse_ir = pulse_ir_from_qasm(
        qasm_path.read_text(encoding="utf-8"),
        backend_config=backend_path,
        hardware={
            "xy_freq_Hz": 5.0e9,
            "ro_freq_Hz": 8.0e9,
            "gate_duration_ns": 20.0,
            "measure_duration_ns": 2000.0,
        },
    )
    pulse_ir = reorder_xy_z_channels(pulse_ir)
    breaks = auto_fold_long_pulses(
        pulse_ir,
        channel_prefixes=("RO",),
        min_pulse_ns=1000.0,
        keep_head_ns=40.0,
        keep_tail_ns=40.0,
    )

    timing_theme = make_timing_theme(break_display_gap_ns=16.0)

    png_path = case_dir / "timing_python.png"
    dxf_path = case_dir / "timing_diagram.dxf"
    metadata_path = case_dir / "pulse_metadata.json"
    plot_pulses(
        pulse_ir,
        timing_layout=True,
        title=case_name,
        show_clock=True,
        breaks=breaks,
        carrier_plot_max_hz=0.5e9,
        dxf_path=dxf_path,
        png_path=png_path,
        theme=timing_theme,
        pulse_metadata_path=metadata_path,
    )

    print(f"[OK] {case_name}")
    print(f"  qasm:        {qasm_path}")
    print(f"  backend:     {backend_path}")
    print(f"  python plot: {png_path}")
    print(f"  dxf:         {dxf_path}")
    print(f"  pulses json: {metadata_path}")


def main() -> None:
    out_dir = Path("runs") / "visual_check"
    generate_case("single qubit cpmg", _build_cpmg_qasm(), out_dir)
    generate_case("three qubit ghz state", _build_ghz_qasm(), out_dir)


if __name__ == "__main__":
    main()
