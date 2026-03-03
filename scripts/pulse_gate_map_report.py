"""Export current gate-to-pulse mapping catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qsim.common.schemas import write_json
from qsim.pulse.catalog import build_gate_mapping_catalog


def _to_markdown(payload: dict) -> str:
    lines = [
        "# Pulse Gate Map",
        "",
        f"Schema: `{payload['schema']}`",
        "",
        "## Resolved Hardware",
        "",
    ]
    for key, value in payload["resolved_hardware"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Operations", ""])
    for op in payload["operations"]:
        lines.append(f"### `{op['op_name']}`")
        lines.append("")
        lines.append(f"- arity: `{op['qubit_arity']}`")
        lines.append(f"- duration_ns: `{op['duration_ns']}`")
        if op.get("shared_recipe_group"):
            lines.append(f"- shared_recipe_group: `{op['shared_recipe_group']}`")
        if op.get("note"):
            lines.append(f"- note: {op['note']}")
        lines.append(f"- summary: {op['summary']}")
        lines.append("")
        if not op["steps"]:
            lines.append("_No steps_")
            lines.append("")
            continue
        lines.append("| kind | stage | role | channel | shape | amp | start_ns | end_ns |")
        lines.append("| --- | --- | --- | --- | --- | ---: | ---: | ---: |")
        for step in op["steps"]:
            lines.append(
                "| {kind} | {stage} | {role} | {channel} | {shape} | {amp} | {start} | {end} |".format(
                    kind=step.get("kind", ""),
                    stage=step.get("stage", ""),
                    role=step.get("role", ""),
                    channel=step.get("channel_template", ""),
                    shape=step.get("shape", ""),
                    amp=step.get("amp", ""),
                    start=step.get("start_ns", ""),
                    end=step.get("end_ns", ""),
                )
            )
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export qsim gate-to-pulse mapping catalog")
    parser.add_argument("--format", choices=["json", "md"], default="json")
    parser.add_argument("--out", required=True, help="Output file path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = build_gate_mapping_catalog()
    out_path = Path(args.out)
    if args.format == "json":
        write_json(out_path, payload)
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_to_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
