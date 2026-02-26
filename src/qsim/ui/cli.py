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
    run.add_argument("--prior-backend", default="auto", help="auto|stim|cirq|mock")
    run.add_argument("--decoder", default="mwpm", help="mwpm|bp|mock")
    run.add_argument("--qec-engine", default="auto", help="auto|stim|cirq|mock")
    run.add_argument("--pauli-plus-analysis", action="store_true", help="enable Pauli+/Kraus-aligned error budget outputs")
    run.add_argument("--pauli-plus-code-distances", default="", help="comma-separated code distances, e.g. 3,5")
    run.add_argument("--pauli-plus-shots", type=int, default=20000, help="shots per code distance for Pauli+ analysis")
    run.add_argument("--decoder-eval", action="store_true", help="enable decoder benchmark sweep")
    run.add_argument("--eval-decoders", default="", help="comma-separated decoders, e.g. mwpm,bp")
    run.add_argument("--eval-seeds", default="", help="comma-separated seeds, e.g. 123,456")
    run.add_argument("--eval-parallelism", type=int, default=1, help="parallel workers for eval tasks")
    run.add_argument("--eval-retries", type=int, default=0, help="retry count for eval task failures")
    run.add_argument("--eval-resume", action="store_true", help="resume eval tasks from resume_state.json")
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
        decoders = [x.strip() for x in args.eval_decoders.split(",") if x.strip()] if args.eval_decoders else None
        seeds = [int(x.strip()) for x in args.eval_seeds.split(",") if x.strip()] if args.eval_seeds else None
        pp_distances = (
            [int(x.strip()) for x in args.pauli_plus_code_distances.split(",") if x.strip()]
            if args.pauli_plus_code_distances
            else None
        )
        result = run_workflow(
            qasm_text=qasm_text,
            backend_path=args.backend,
            out_dir=args.out,
            engine=args.engine,
            prior_backend=args.prior_backend,
            decoder=args.decoder,
            qec_engine=args.qec_engine,
            pauli_plus_analysis=bool(args.pauli_plus_analysis),
            pauli_plus_code_distances=pp_distances,
            pauli_plus_shots=int(args.pauli_plus_shots),
            decoder_eval=bool(args.decoder_eval),
            eval_decoders=decoders,
            eval_seeds=seeds,
            eval_parallelism=int(args.eval_parallelism),
            eval_retries=int(args.eval_retries),
            eval_resume=bool(args.eval_resume),
        )
        print(f"Workflow completed. Outputs saved to: {result['out_dir']}")


if __name__ == "__main__":
    main()
