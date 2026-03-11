"""Session integration for workflow results."""

from __future__ import annotations

from pathlib import Path

from qsim.session.session import Session


DEFAULT_SESSION_COMMIT_KINDS = [
    "settings",
    "timings",
    "logical_error",
    "decoder_report",
    "sensitivity_report",
    "error_budget_v2",
]

RESULT_KEY_BY_KIND = {
    "settings": "settings",
    "timings": "timings",
    "logical_error": "logical_error",
    "decoder_report": "decoder_report",
    "sensitivity_report": "sensitivity_report",
    "error_budget_v2": "error_budget_v2",
    "analysis": "analysis",
    "cross_engine_compare": "cross_engine_compare",
    "decoder_eval_report": "decoder_eval_report",
    "scaling_report": "scaling_report",
    "error_budget_pauli_plus": "error_budget_pauli_plus",
}


def commit_result_to_session(
    *,
    session_dir: str | Path,
    run_out_dir: str | Path,
    result_payload: dict,
    commit_kinds: list[str] | None = None,
) -> dict:
    """Commit selected result artifacts into a session store."""
    session = Session.open(session_dir)
    requested = list(commit_kinds or DEFAULT_SESSION_COMMIT_KINDS)
    run_out = str(Path(run_out_dir))
    run_id = Path(run_out).name
    inputs = {"run_out_dir": run_out}
    tags = [f"run:{run_id}"]

    commits: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for kind in requested:
        key = RESULT_KEY_BY_KIND.get(kind)
        if not key:
            skipped.append({"kind": kind, "reason": "unknown_kind"})
            continue
        payload = result_payload.get(key)
        if payload is None:
            skipped.append({"kind": kind, "reason": "missing_payload"})
            continue
        rev_id = session.commit(kind, payload, inputs=inputs, tags=tags)
        commits.append({"kind": kind, "rev_id": rev_id})

    return {
        "schema_version": "1.0",
        "session_dir": str(Path(session_dir).resolve()),
        "run_out_dir": run_out,
        "run_id": run_id,
        "requested_kinds": requested,
        "commits": commits,
        "skipped": skipped,
    }


__all__ = ["DEFAULT_SESSION_COMMIT_KINDS", "RESULT_KEY_BY_KIND", "commit_result_to_session"]
