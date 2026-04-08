"""Command-line interface for model-first workflow execution."""

from __future__ import annotations

import argparse

from qsim.workflow import create_model


def build_parser() -> argparse.ArgumentParser:
    """Build parser for 5-config model creation and execution."""
    parser = argparse.ArgumentParser(description="qsim model runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_model_cmd = sub.add_parser("run-model", help="create a model from task/solver/device/pulse/analyser configs and run it")
    run_model_cmd.add_argument("--task-config", required=True, help="path to task config (json/yaml)")
    run_model_cmd.add_argument("--solver-config", default="", help="optional solver config override (json/yaml)")
    run_model_cmd.add_argument("--device-config", default="", help="optional device config override (json/yaml)")
    run_model_cmd.add_argument("--pulse-config", default="", help="optional pulse config override (json/yaml)")
    run_model_cmd.add_argument("--analyser-config", default="", help="optional analyser config override (json/yaml)")
    return parser


def main() -> None:
    """CLI entrypoint.

    Example:
        ```bash
        qsim run-model --task-config tasks/demo.yaml --solver-config solvers/qutip.yaml --device-config device/default.yaml --pulse-config pulses/default.yaml --analyser-config analysers/default.yaml
        ```
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd != "run-model":
        parser.error("Only `run-model` mode is supported.")

    model = create_model(
        task_config=args.task_config,
        solver_config=(args.solver_config or None),
        device_config=(args.device_config or None),
        pulse_config=(args.pulse_config or None),
        analyser_config=(args.analyser_config or None),
    )
    model.run()
    out = model.save()
    print(f"Model completed. Outputs saved to: {out}")


if __name__ == "__main__":
    main()
