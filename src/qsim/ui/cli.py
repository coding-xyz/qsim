from __future__ import annotations

import argparse
from pathlib import Path

from qsim.ui.notebook import run_workflow


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for qsim workflow entrypoint."""
    parser = argparse.ArgumentParser(description="qsim workflow runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run full workflow")
    run.add_argument("--qasm", required=True, help="path to .qasm file")
    run.add_argument("--backend", required=True, help="path to backend.yaml")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--engine", default="qutip", help="qutip|julia_qtoolbox|julia_qoptics")
    return parser


def main() -> None:
    """CLI entrypoint.

    Example:
        ```bash
        qsim run --qasm examples/bell.qasm --backend examples/backend.yaml --out runs/demo
        ```
    """
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "run":
        qasm_text = Path(args.qasm).read_text(encoding="utf-8")
        run_workflow(
            qasm_text=qasm_text,
            backend_path=args.backend,
            out_dir=args.out,
            engine=args.engine,
        )
        print(f"Workflow completed. Outputs saved to: {args.out}")


if __name__ == "__main__":
    main()
