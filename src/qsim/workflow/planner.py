"""Target/template-driven execution planning for workflow pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from qsim.workflow.contracts import WorkflowTask


STAGE_PARSE = "parse_compile_lower_model"
STAGE_ENGINE = "engine_run"
STAGE_DECODE = "decode_run"
STAGE_ANALYSIS = "analysis_run"
STAGE_DECODER_EVAL = "decoder_eval_run"
STAGE_PAULI_PLUS = "pauli_plus_run"
STAGE_CROSS_COMPARE = "cross_engine_compare"

_ORDERED_STAGES = (
    STAGE_PARSE,
    STAGE_ENGINE,
    STAGE_DECODE,
    STAGE_ANALYSIS,
    STAGE_DECODER_EVAL,
    STAGE_PAULI_PLUS,
    STAGE_CROSS_COMPARE,
)

_STAGE_OUTPUTS: dict[str, tuple[str, ...]] = {
    STAGE_PARSE: (
        "circuit",
        "backend_config",
        "normalized_circuit",
        "compile_report",
        "pulse_ir",
        "pulse_samples",
        "executable_model",
        "model_spec",
    ),
    STAGE_ENGINE: ("trace",),
    STAGE_DECODE: (
        "syndrome_frame",
        "prior_model",
        "prior_report",
        "prior_samples",
        "decoder_input",
        "decoder_output",
        "decoder_report",
        "logical_error",
    ),
    STAGE_ANALYSIS: ("observables", "report", "sensitivity_report", "error_budget_v2", "sensitivity_heatmap"),
    STAGE_DECODER_EVAL: (
        "decoder_eval_report",
        "decoder_eval_table",
        "decoder_pareto",
        "batch_manifest",
        "resume_state",
        "failed_tasks",
    ),
    STAGE_PAULI_PLUS: ("scaling_report", "error_budget_pauli_plus", "component_ablation"),
    STAGE_CROSS_COMPARE: ("cross_engine_compare",),
}


@dataclass(slots=True)
class TargetRule:
    """Dependency rule for one high-level target."""

    stages: tuple[str, ...]
    required_fields: tuple[str, ...] = ()


TARGET_RULES: dict[str, TargetRule] = {
    "trace": TargetRule(stages=(STAGE_PARSE, STAGE_ENGINE)),
    "logical_error": TargetRule(stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_DECODE), required_fields=("run.decoder",)),
    "sensitivity_report": TargetRule(
        stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_DECODE, STAGE_ANALYSIS),
        required_fields=("run.decoder",),
    ),
    "decoder_eval_report": TargetRule(
        stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_DECODE, STAGE_DECODER_EVAL),
        required_fields=("run.decoder",),
    ),
    "scaling_report": TargetRule(
        stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_DECODE, STAGE_ANALYSIS, STAGE_PAULI_PLUS),
        required_fields=("run.decoder",),
    ),
    "error_budget_pauli_plus": TargetRule(
        stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_DECODE, STAGE_ANALYSIS, STAGE_PAULI_PLUS),
        required_fields=("run.decoder",),
    ),
    "cross_engine_compare": TargetRule(
        stages=(STAGE_PARSE, STAGE_ENGINE, STAGE_CROSS_COMPARE),
        required_fields=("run.compare_engines",),
    ),
}

DEFAULT_TEMPLATE = "full"
TEMPLATE_TARGETS: dict[str, tuple[str, ...]] = {
    "simulate": ("trace",),
    "simulate_qec": ("logical_error", "sensitivity_report"),
    "full": ("logical_error", "sensitivity_report"),
    "full_eval": ("logical_error", "sensitivity_report", "decoder_eval_report", "scaling_report", "cross_engine_compare"),
}


@dataclass(slots=True)
class ExecutionPlan:
    """Resolved execution plan derived from task template/targets/features."""

    template: str
    targets: list[str]
    stages: list[str]
    required_fields: list[str]
    artifact_outputs: list[str]
    run_decode: bool
    run_analysis: bool
    run_decoder_eval: bool
    run_pauli_plus: bool
    run_cross_engine_compare: bool
    artifact_mode: str
    warnings: list[str] = field(default_factory=list)


def _task_field_value(task: WorkflowTask, dotted: str):
    current = task
    for part in dotted.split("."):
        current = getattr(current, part)
    return current


def _validate_required_fields(task: WorkflowTask, required_fields: list[str]) -> None:
    for field_name in required_fields:
        value = _task_field_value(task, field_name)
        if value in (None, "", [], {}):
            raise ValueError(f"Execution target requires `{field_name}` to be configured.")


def _normalize_targets(task: WorkflowTask) -> tuple[str, list[str]]:
    raw_template = (task.template or DEFAULT_TEMPLATE).strip().lower()
    if raw_template not in TEMPLATE_TARGETS:
        raise ValueError(f"Unknown workflow template: {task.template!r}")

    if task.targets:
        targets = [str(t).strip().lower() for t in task.targets if str(t).strip()]
    else:
        targets = list(TEMPLATE_TARGETS[raw_template])

    if not targets:
        raise ValueError("Workflow targets must not be empty.")

    unknown = [t for t in targets if t not in TARGET_RULES]
    if unknown:
        raise ValueError(f"Unknown workflow targets: {unknown}")

    deduped = list(dict.fromkeys(targets))
    return raw_template, deduped


def _normalize_artifact_mode(mode: str | None) -> str:
    normalized = (mode or "all").strip().lower()
    if normalized == "minimal":
        normalized = "targeted"
    if normalized not in {"all", "targeted"}:
        raise ValueError(f"Unsupported output.artifact_mode: {mode!r}")
    return normalized


def _validate_engine_run_dependency(task: WorkflowTask) -> None:
    """Validate engine-dependent solver/run fields."""
    engine = str(task.run.engine or "qutip").strip().lower()
    if engine.startswith("julia") or engine in {"quantumoptics", "quantumtoolbox"}:
        return
    disallowed = []
    if task.run.julia_bin:
        disallowed.append("run.julia_bin")
    if task.run.julia_depot_path:
        disallowed.append("run.julia_depot_path")
    if task.run.julia_timeout_s not in (None, 120.0):
        disallowed.append("run.julia_timeout_s")
    if disallowed:
        raise ValueError(f"Engine {engine!r} does not support Julia-only keys: {sorted(disallowed)}")


def build_execution_plan(task: WorkflowTask) -> ExecutionPlan:
    """Build minimal execution plan from task template/targets/features."""
    template, targets = _normalize_targets(task)

    stage_set: set[str] = set()
    required_fields: set[str] = set()
    for target in targets:
        rule = TARGET_RULES[target]
        stage_set.update(rule.stages)
        required_fields.update(rule.required_fields)

    run_decoder_eval = bool(task.features.decoder_eval or "decoder_eval_report" in targets)
    run_pauli_plus = bool(
        task.features.pauli_plus_analysis or "scaling_report" in targets or "error_budget_pauli_plus" in targets
    )
    run_cross_engine_compare = bool(task.run.compare_engines) or "cross_engine_compare" in targets

    if run_decoder_eval:
        stage_set.add(STAGE_DECODER_EVAL)
        stage_set.add(STAGE_DECODE)
    if run_pauli_plus:
        stage_set.add(STAGE_PAULI_PLUS)
        stage_set.add(STAGE_DECODE)
        stage_set.add(STAGE_ANALYSIS)
    if run_cross_engine_compare:
        stage_set.add(STAGE_CROSS_COMPARE)

    # Parse + engine are always required for a meaningful run.
    stage_set.add(STAGE_PARSE)
    stage_set.add(STAGE_ENGINE)

    run_decode = STAGE_DECODE in stage_set
    run_analysis = STAGE_ANALYSIS in stage_set
    if run_decode:
        required_fields.add("run.decoder")

    ordered_stages = [stage for stage in _ORDERED_STAGES if stage in stage_set]

    artifact_outputs: list[str] = []
    for stage in ordered_stages:
        artifact_outputs.extend(_STAGE_OUTPUTS.get(stage, ()))
    artifact_outputs.append("settings_report")
    artifact_outputs = list(dict.fromkeys(artifact_outputs))

    required_fields_list = sorted(required_fields)
    _validate_engine_run_dependency(task)
    _validate_required_fields(task, required_fields_list)

    return ExecutionPlan(
        template=template,
        targets=targets,
        stages=ordered_stages,
        required_fields=required_fields_list,
        artifact_outputs=artifact_outputs,
        run_decode=run_decode,
        run_analysis=run_analysis,
        run_decoder_eval=run_decoder_eval,
        run_pauli_plus=run_pauli_plus,
        run_cross_engine_compare=run_cross_engine_compare,
        artifact_mode=_normalize_artifact_mode(task.output.artifact_mode),
    )


__all__ = [
    "DEFAULT_TEMPLATE",
    "ExecutionPlan",
    "TARGET_RULES",
    "TEMPLATE_TARGETS",
    "build_execution_plan",
]
