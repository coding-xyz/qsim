"""Command-line interface for task/solver/device/pulse workflow execution."""

from __future__ import annotations

import argparse

from qsim.workflow import run_task_files


def build_parser() -> argparse.ArgumentParser:
    """Build parser for 3-config workflow execution."""
    parser = argparse.ArgumentParser(description="qsim workflow runner (task/solver/device)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_task_cmd = sub.add_parser("run-task", help="run workflow from task/solver/device/pulse configs")
    run_task_cmd.add_argument("--task-config", required=True, help="path to task config (json/yaml)")
    run_task_cmd.add_argument("--solver-config", default="", help="optional solver config override (json/yaml)")
    run_task_cmd.add_argument("--device-config", default="", help="optional device config override (json/yaml)")
    run_task_cmd.add_argument("--pulse-config", default="", help="optional pulse config override (json/yaml)")
    return parser


def main() -> None:
    """CLI entrypoint.

    Example:
        ```bash
        qsim run-task --task-config tasks/demo.yaml --solver-config solvers/qutip.yaml --device-config device/default.yaml --pulse-config pulses/default.yaml
        ```
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd != "run-task":
        parser.error("Only `run-task` mode is supported.")

    result = run_task_files(
        task_config=args.task_config,
        solver_config=(args.solver_config or None),
        device_config=(args.device_config or None),
        pulse_config=(args.pulse_config or None),
    )
    print(f"Workflow completed. Outputs saved to: {result['runtime']['out_dir']}")


if __name__ == "__main__":
    main()
