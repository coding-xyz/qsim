"""One-click native tri-engine comparison for Task1 single-qubit reference.

Runs:
- QuTiP reference (Python)
- QuantumOptics.jl reference (Julia)
- QuantumToolbox.jl reference (Julia)

Outputs a compact CSV summary for quick engine-call sanity checks.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import csv
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _run_qutip() -> list[dict]:
    """Run QuTiP native reference for baseline/detuned and return summary rows."""
    if str(ROOT / "examples" / "noise_simulation_tests") not in sys.path:
        sys.path.insert(0, str(ROOT / "examples" / "noise_simulation_tests"))
    from task1_qutip_native_reference import run_case  # type: ignore

    omega_eff = 0.08
    cases = {
        "baseline": {"delta": 5.0, "t1": 120.0, "t2": 90.0, "t_end": 240.0, "dt": 1.0},
        "detuned": {"delta": 5.2, "t1": 80.0, "t2": 55.0, "t_end": 256.0, "dt": 1.0},
    }
    rows: list[dict] = []
    for case, cfg in cases.items():
        t, p1 = run_case(
            delta=cfg["delta"],
            omega=omega_eff,
            t1=cfg["t1"],
            t2=cfg["t2"],
            t_end=cfg["t_end"],
            dt=cfg["dt"],
        )
        rows.append(
            {
                "engine": "qutip",
                "case": case,
                "samples": int(len(t)),
                "final_p1": float(p1[-1]),
                "mean_p1": float(sum(p1) / len(p1)),
                "status": "ok",
                "note": "",
            }
        )
    return rows


_LINE_RE = re.compile(r"^(baseline|detuned):\s+samples=(\d+)\s+final_p1=([0-9eE+\-.]+)\s+mean_p1=([0-9eE+\-.]+)\s*$")


def _run_julia(script_name: str, label: str, julia_bin: str) -> list[dict]:
    """Run a Julia native reference script and parse compact stdout summary rows."""
    script = ROOT / "examples" / "noise_simulation_tests" / script_name
    cmd = [julia_bin, str(script)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip().replace("\n", " | ")
        return [
            {"engine": label, "case": "baseline", "samples": 0, "final_p1": float("nan"), "mean_p1": float("nan"), "status": "error", "note": msg},
            {"engine": label, "case": "detuned", "samples": 0, "final_p1": float("nan"), "mean_p1": float("nan"), "status": "error", "note": msg},
        ]
    rows: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        rows.append(
            {
                "engine": label,
                "case": m.group(1),
                "samples": int(m.group(2)),
                "final_p1": float(m.group(3)),
                "mean_p1": float(m.group(4)),
                "status": "ok",
                "note": "",
            }
        )
    if len(rows) != 2:
        note = "unexpected output format"
        return [
            {"engine": label, "case": "baseline", "samples": 0, "final_p1": float("nan"), "mean_p1": float("nan"), "status": "error", "note": note},
            {"engine": label, "case": "detuned", "samples": 0, "final_p1": float("nan"), "mean_p1": float("nan"), "status": "error", "note": note},
        ]
    return rows


def main() -> int:
    """CLI entry point for native tri-engine Task1 summary generation."""
    parser = argparse.ArgumentParser(description="Run Task1 native tri-engine references and export one summary CSV.")
    parser.add_argument("--out-dir", default=str(ROOT / "task1_outputs"), help="Output directory (default: <repo>/task1_outputs)")
    parser.add_argument("--julia-bin", default="julia", help="Julia executable for .jl references")
    parser.add_argument("--skip-julia", action="store_true", help="Skip Julia references and run only QuTiP")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    rows.extend(_run_qutip())
    if not args.skip_julia:
        rows.extend(_run_julia("task1_quantumoptics_native_reference.jl", "julia_qoptics_native", args.julia_bin))
        rows.extend(_run_julia("task1_quantumtoolbox_native_reference.jl", "julia_qtoolbox_native", args.julia_bin))

    out_csv = out_dir / "task1_native_tri_compare_summary.csv"
    fields = ["engine", "case", "samples", "final_p1", "mean_p1", "status", "note"]
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("summary_csv =", out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
