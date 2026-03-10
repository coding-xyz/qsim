"""Task1 single-qubit tri-engine visual comparison helper.

This script reads existing Task1 run artifacts and exports per-case p1(t)
comparison plots plus a compact summary table.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from qsim.analysis.trace_semantics import annotate_trace_metadata, extract_p1_series  # noqa: E402
from qsim.pulse.visualize import load_trace_h5  # noqa: E402


TASK_JSON = ROOT / "examples" / "noise_simulation_tests" / "required_tasks_tri_engine" / "task1_single_qubit_baseline.json"
OUT_ROOT = ROOT / "examples" / "noise_simulation_tests" / "runs" / "required_tasks_tri_engine"


def _plot_case_dynamics(case_df: pd.DataFrame, case: str, out_dir: Path) -> Path:
    """Plot p1(t) curves for one case across engines and return PNG path."""
    fig, ax = plt.subplots(figsize=(9, 4))
    for _, row in case_df.sort_values("engine").iterrows():
        ax.plot(row["times"], row["p1_t"], label=row["engine"], linewidth=2.0)
    ax.set_title(f"Task1 {case}: p1(t) dynamics")
    ax.set_xlabel("time")
    ax.set_ylabel("p1")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out_path = out_dir / f"task1_{case}_p1_dynamics.png"
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
    return out_path


def _plot_final_p1_bar(df: pd.DataFrame, out_dir: Path) -> Path:
    """Plot final p1 bar chart by case/engine and return PNG path."""
    pivot = df.pivot(index="case", columns="engine", values="final_p1_from_trace")
    ax = pivot.plot(kind="bar", figsize=(9, 4), rot=0)
    ax.set_title("Task1 final p1 from trace by case/engine")
    ax.set_ylabel("final_p1_from_trace")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out_path = out_dir / "task1_final_p1_bar.png"
    plt.savefig(out_path, dpi=180)
    plt.close()
    return out_path


def main() -> int:
    """CLI entry point that builds Task1 visual compare artifacts from existing runs."""
    parser = argparse.ArgumentParser(description="Build Task1 p1(t) plots from existing run artifacts.")
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "task1_outputs"),
        help="Output directory for CSV/PNG artifacts (default: <repo>/task1_outputs).",
    )
    args = parser.parse_args()

    task = json.loads(TASK_JSON.read_text(encoding="utf-8"))
    task_tag = str(task["tag"])
    plot_root = Path(args.out_dir).resolve()
    plot_root.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    dyn_rows: list[dict] = []
    for case in task["cases"]:
        case_tag = str(case["tag"])
        for engine in task["engines"]:
            engine_tag = str(engine)
            out_dir = OUT_ROOT / task_tag / case_tag / engine_tag
            trace_h5 = out_dir / "trace.h5"
            if not trace_h5.exists():
                raise FileNotFoundError(f"missing trace artifact: {trace_h5}")
            trace = load_trace_h5(trace_h5)
            annotate_trace_metadata(trace, num_qubits=1, engine_name=engine_tag)
            p1_t = extract_p1_series(trace)
            times = [float(x) for x in trace.times[: len(p1_t)]]
            final_p1 = float(p1_t[-1]) if p1_t else float("nan")
            mean_p1 = float(sum(p1_t) / len(p1_t)) if p1_t else float("nan")
            summary_rows.append(
                {
                    "task": task_tag,
                    "case": case_tag,
                    "engine": engine_tag,
                    "encoding": str(getattr(trace, "metadata", {}).get("state_encoding", "unknown")),
                    "samples": int(len(times)),
                    "final_p1_from_trace": final_p1,
                    "mean_p1_from_trace": mean_p1,
                    "trace_path": str(trace_h5),
                }
            )
            dyn_rows.append(
                {
                    "task": task_tag,
                    "case": case_tag,
                    "engine": engine_tag,
                    "times": times,
                    "p1_t": p1_t,
                    "encoding": str(getattr(trace, "metadata", {}).get("state_encoding", "unknown")),
                }
            )

    df = pd.DataFrame(summary_rows)
    dyn_df = pd.DataFrame(dyn_rows)
    summary_csv = plot_root / f"{task_tag}_visual_compare_summary.csv"
    df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    dyn_csv_rows = []
    for _, row in dyn_df.iterrows():
        times = row["times"]
        p1_t = row["p1_t"]
        for t, p in zip(times, p1_t):
            dyn_csv_rows.append(
                {
                    "task": row["task"],
                    "case": row["case"],
                    "engine": row["engine"],
                    "time": float(t),
                    "p1": float(p),
                    "encoding": row["encoding"],
                }
            )
    dyn_csv = plot_root / "task1_p1_dynamics_long.csv"
    pd.DataFrame(dyn_csv_rows).to_csv(dyn_csv, index=False, encoding="utf-8-sig")

    case_plots: list[Path] = []
    for case in sorted(dyn_df["case"].unique()):
        case_plots.append(_plot_case_dynamics(dyn_df[dyn_df["case"] == case], case, plot_root))
    final_p1_bar = _plot_final_p1_bar(df, plot_root)

    print("summary_csv =", summary_csv)
    print("dynamics_csv =", dyn_csv)
    for p in case_plots:
        print("plot =", p)
    print("plot =", final_p1_bar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
