from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from qsim.common.schemas import DecoderInput, PriorModel, SyndromeFrame
from qsim.qec.eval import run_decoder_eval


def test_decoder_eval_resume_skips_completed_tasks():
    out_dir = Path("runs") / f"pytest_qec_resume_{uuid.uuid4().hex[:8]}"
    resume_path = out_dir / "resume_state.json"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        decoder_input = DecoderInput(
            syndrome=SyndromeFrame(rounds=3, detectors=[[0, 1], [1, 0], [0, 0]], observables=[0, 1]),
            prior=PriorModel(nodes=[{"id": 0}, {"id": 1}], edges=[{"u": 0, "v": 1, "weight": 1.0}]),
        )

        first_report, *_ = run_decoder_eval(
            decoder_input,
            decoders=["mwpm", "bp"],
            seeds=[21, 22],
            option_grid=[{}],
            resume=True,
            resume_state_path=resume_path,
        )
        assert int(first_report["total_runs"]) == 4
        second_report, *_ = run_decoder_eval(
            decoder_input,
            decoders=["mwpm", "bp"],
            seeds=[21, 22],
            option_grid=[{}],
            resume=True,
            resume_state_path=resume_path,
        )
        assert int(second_report["skipped_runs"]) >= 4
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
