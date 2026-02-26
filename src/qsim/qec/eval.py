from __future__ import annotations

import csv
import json
import time
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from qsim.common.schemas import DecoderInput
from qsim.qec.decoder import get_decoder, summarize_logical_error


def _task_id(decoder: str, seed: int, opts: dict[str, Any]) -> str:
    """Build stable task ID from decoder/seed/options."""
    raw = json.dumps({"decoder": decoder, "seed": int(seed), "opts": opts}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _run_task_once(
    decoder_input: DecoderInput,
    decoder: str,
    seed: int,
    opts: dict[str, Any],
    task_id: str,
    attempt: int,
) -> dict[str, Any]:
    """Run a single decoder-eval task and return a table row."""
    t0 = time.perf_counter()
    output = get_decoder(decoder).run(decoder_input, options={"seed": int(seed), **opts})
    elapsed = time.perf_counter() - t0
    logical = summarize_logical_error(output, shots=max(1, len(decoder_input.syndrome.detectors)))
    return {
        "task_id": task_id,
        "attempt": int(attempt),
        "decoder": output.decoder_name,
        "decoder_rev": output.decoder_rev,
        "seed": int(seed),
        "status": output.status,
        "confidence": float(output.confidence),
        "num_corrections": len(output.corrections),
        "logical_x": float(logical.logical_x),
        "logical_z": float(logical.logical_z),
        "elapsed_s": float(elapsed),
        "options_json": json.dumps(opts, ensure_ascii=False, sort_keys=True),
    }


def _run_task_with_retries(
    decoder_input: DecoderInput,
    decoder: str,
    seed: int,
    opts: dict[str, Any],
    task_id: str,
    max_attempts: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Execute one task with bounded retries.

    Returns:
        Tuple ``(row, failure)`` where only one item is non-``None``.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            row = _run_task_once(decoder_input, decoder, seed, opts, task_id, attempt)
            return row, None
        except Exception as exc:  # pragma: no cover - depends on runtime errors
            last_err = exc
    return None, {"task_id": task_id, "decoder": decoder, "seed": int(seed), "error": str(last_err), "attempts": int(max_attempts)}


def _load_resume_state(path: Path) -> set[str]:
    """Load completed task IDs from resume state file."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data.get("completed_task_ids", [])
        return {str(x) for x in ids}
    except Exception:
        return set()


def _write_resume_state(path: Path, completed: set[str], batch_id: str) -> None:
    """Persist resume state for incremental batch continuation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "completed_task_ids": sorted(completed),
        "updated_at": time.time(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_decoder_eval(
    decoder_input: DecoderInput,
    *,
    decoders: list[str],
    seeds: list[int],
    option_grid: list[dict[str, Any]] | None = None,
    parallelism: int = 1,
    retries: int = 0,
    resume: bool = False,
    resume_state_path: str | Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Run decoder benchmark sweep with parallel/retry/resume controls.

    Args:
        decoder_input: Decoder input bundle shared across sweep tasks.
        decoders: Decoder names to evaluate.
        seeds: Seed list for repeated evaluation.
        option_grid: Optional decoder-option grid, defaults to ``[{}]``.
        parallelism: Worker count; ``1`` forces serial mode.
        retries: Retry count per task after first failure.
        resume: Whether to skip completed tasks from ``resume_state_path``.
        resume_state_path: Resume state file path.

    Returns:
        ``(report, rows, batch_manifest, failed_tasks, resume_state)``
    """
    grid = option_grid or [{}]
    batch_id = hashlib.sha256(
        json.dumps({"decoders": decoders, "seeds": seeds, "grid": grid}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    resume_path = Path(resume_state_path) if resume_state_path is not None else Path("resume_state.json")
    completed_ids = _load_resume_state(resume_path) if resume else set()

    tasks: list[dict[str, Any]] = []
    skipped = 0
    for dec in decoders:
        for opts in grid:
            for seed in seeds:
                tid = _task_id(dec, int(seed), opts)
                if tid in completed_ids:
                    skipped += 1
                    continue
                tasks.append({"decoder": dec, "seed": int(seed), "opts": opts, "task_id": tid})

    rows: list[dict[str, Any]] = []
    failed_tasks: list[dict[str, Any]] = []
    max_attempts = max(1, int(retries) + 1)

    used_parallelism = int(max(1, parallelism))
    if used_parallelism <= 1:
        for t in tasks:
            row, fail = _run_task_with_retries(
                decoder_input,
                t["decoder"],
                int(t["seed"]),
                dict(t["opts"]),
                str(t["task_id"]),
                max_attempts=max_attempts,
            )
            if row is not None:
                rows.append(row)
                completed_ids.add(str(t["task_id"]))
            elif fail is not None:
                failed_tasks.append(fail)
    else:
        try:
            with ProcessPoolExecutor(max_workers=used_parallelism) as ex:
                futures = {
                    ex.submit(
                        _run_task_with_retries,
                        decoder_input,
                        t["decoder"],
                        int(t["seed"]),
                        dict(t["opts"]),
                        str(t["task_id"]),
                        max_attempts,
                    ): t
                    for t in tasks
                }
                for fut in as_completed(futures):
                    t = futures[fut]
                    try:
                        row, fail = fut.result()
                    except Exception as exc:  # pragma: no cover - process failures are env-dependent
                        fail = {
                            "task_id": str(t["task_id"]),
                            "decoder": t["decoder"],
                            "seed": int(t["seed"]),
                            "error": str(exc),
                            "attempts": int(max_attempts),
                        }
                        row = None
                    if row is not None:
                        rows.append(row)
                        completed_ids.add(str(t["task_id"]))
                    elif fail is not None:
                        failed_tasks.append(fail)
        except Exception as exc:
            # Some Windows-restricted environments disallow process pipes.
            used_parallelism = 1
            failed_tasks.append(
                {
                    "task_id": "executor_init",
                    "decoder": "n/a",
                    "seed": -1,
                    "error": f"parallel disabled: {exc}",
                    "attempts": 1,
                }
            )
            for t in tasks:
                row, fail = _run_task_with_retries(
                    decoder_input,
                    t["decoder"],
                    int(t["seed"]),
                    dict(t["opts"]),
                    str(t["task_id"]),
                    max_attempts=max_attempts,
                )
                if row is not None:
                    rows.append(row)
                    completed_ids.add(str(t["task_id"]))
                elif fail is not None:
                    failed_tasks.append(fail)

    if resume:
        _write_resume_state(resume_path, completed_ids, batch_id=batch_id)

    # Aggregate by decoder for quick ranking.
    by_decoder: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_decoder.setdefault(str(r["decoder"]), []).append(r)

    summary: list[dict[str, Any]] = []
    for name, items in by_decoder.items():
        n = max(1, len(items))
        avg_lx = sum(float(i["logical_x"]) for i in items) / n
        avg_lz = sum(float(i["logical_z"]) for i in items) / n
        avg_t = sum(float(i["elapsed_s"]) for i in items) / n
        fail_rate = sum(1 for i in items if str(i["status"]) != "ok") / n
        summary.append(
            {
                "decoder": name,
                "runs": len(items),
                "avg_logical_x": avg_lx,
                "avg_logical_z": avg_lz,
                "avg_elapsed_s": avg_t,
                "fail_rate": fail_rate,
            }
        )

    summary = sorted(summary, key=lambda x: (x["avg_logical_x"], x["avg_elapsed_s"]))
    pareto = [{"decoder": s["decoder"], "avg_logical_x": s["avg_logical_x"], "avg_elapsed_s": s["avg_elapsed_s"]} for s in summary]

    report = {
        "schema_version": "1.0",
        "status": "ok" if len(failed_tasks) == 0 else "partial",
        "total_runs": len(rows),
        "failed_runs": len(failed_tasks),
        "skipped_runs": int(skipped),
        "decoders": list(decoders),
        "seeds": [int(s) for s in seeds],
        "option_grid_size": len(grid),
        "parallelism": int(used_parallelism),
        "retries": int(max(0, retries)),
        "resume_enabled": bool(resume),
        "summary": summary,
        "pareto": pareto,
    }
    batch_manifest = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "total_tasks": len(decoders) * len(seeds) * len(grid),
        "scheduled_tasks": len(tasks),
        "completed_tasks": len(rows),
        "failed_tasks": len(failed_tasks),
        "skipped_tasks": int(skipped),
        "parallelism": int(used_parallelism),
        "retries": int(max(0, retries)),
        "resume_enabled": bool(resume),
    }
    resume_state = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "completed_task_ids": sorted(completed_ids),
    }
    return report, rows, batch_manifest, failed_tasks, resume_state


def write_decoder_eval_csv(rows: list[dict[str, Any]], out_path: str | Path) -> Path:
    """Write decoder evaluation table as CSV."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "decoder",
        "decoder_rev",
        "seed",
        "status",
        "confidence",
        "num_corrections",
        "logical_x",
        "logical_z",
        "elapsed_s",
        "options_json",
    ]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, "") for h in headers})
    return out


def write_failed_tasks_jsonl(failed_tasks: list[dict[str, Any]], out_path: str | Path) -> Path:
    """Write failed task records as JSON Lines for postmortem analysis."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for item in failed_tasks:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return out
