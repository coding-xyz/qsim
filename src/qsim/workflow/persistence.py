"""Persistence services for workflow artifacts, viz, and manifest."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import importlib.metadata as ilm

from qsim.analysis.error_budget_pauli import write_component_ablation_csv
from qsim.analysis.sensitivity import write_sensitivity_heatmap
from qsim.backend.config import dump_backend_config
from qsim.common.schemas import RunManifest, write_json
from qsim.pulse.drawer_adapter import EngineeringDrawer
from qsim.qec.eval import write_decoder_eval_csv, write_decoder_pareto_png, write_failed_tasks_jsonl
from qsim.qec.prior import write_prior_samples_npz
from qsim.workflow.engines import collect_runtime_dependencies
from qsim.workflow.output import export_circuit_diagram, export_result_figures, sha256_text, write_trace_h5


@dataclass(slots=True)
class ArtifactWritePolicy:
    """Artifact persistence policy."""

    persist_artifacts: bool = True
    artifact_mode: str = "all"
    selected_outputs: set[str] | None = None


@dataclass(slots=True)
class ArtifactPayload:
    """Structured payload for artifact writers."""

    core: dict
    qec: dict
    analysis: dict
    optional: dict


@dataclass(slots=True)
class ArtifactWriteReport:
    """Structured write result with logical output map."""

    outputs: dict[str, str] = field(default_factory=dict)
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def relpath(self, key: str) -> str:
        """Return relative output path by logical key."""
        return self.outputs.get(key, "")


def _normalized_policy(policy: ArtifactWritePolicy) -> ArtifactWritePolicy:
    mode = (policy.artifact_mode or "all").strip().lower()
    if mode == "minimal":
        mode = "targeted"
    if mode not in {"all", "targeted"}:
        raise ValueError(f"Unsupported artifact mode: {policy.artifact_mode!r}")
    selected = set(policy.selected_outputs or []) or None
    return ArtifactWritePolicy(
        persist_artifacts=bool(policy.persist_artifacts),
        artifact_mode=mode,
        selected_outputs=selected,
    )


def _should_write(policy: ArtifactWritePolicy, logical_name: str) -> bool:
    if not policy.persist_artifacts:
        return False
    if policy.artifact_mode == "all":
        return True
    return bool(policy.selected_outputs and logical_name in policy.selected_outputs)


def _record_skip(report: ArtifactWriteReport, logical_name: str) -> None:
    if logical_name not in report.skipped:
        report.skipped.append(logical_name)


def _record_write(report: ArtifactWriteReport, logical_name: str, relpath: str) -> None:
    report.outputs[logical_name] = relpath
    if logical_name not in report.written:
        report.written.append(logical_name)


def write_artifacts(*, out: Path, policy: ArtifactWritePolicy, payload: ArtifactPayload) -> ArtifactWriteReport:
    """Persist workflow JSON/H5/CSV artifacts using structured payload."""
    policy = _normalized_policy(policy)
    report = ArtifactWriteReport()
    if not policy.persist_artifacts:
        return report

    core = dict(payload.core or {})
    qec = dict(payload.qec or {})
    analysis = dict(payload.analysis or {})
    optional = dict(payload.optional or {})

    if core.get("circuit") is not None:
        if _should_write(policy, "circuit"):
            write_json(out / "circuit.json", asdict(core["circuit"]))
            _record_write(report, "circuit", "circuit.json")
        else:
            _record_skip(report, "circuit")
    if core.get("backend_config") is not None:
        if _should_write(policy, "backend_config"):
            dump_backend_config(core["backend_config"], out / "backend_config.json")
            _record_write(report, "backend_config", "backend_config.json")
        else:
            _record_skip(report, "backend_config")
    if core.get("normalized") is not None:
        if _should_write(policy, "normalized_circuit"):
            write_json(out / "normalized_circuit.json", asdict(core["normalized"]))
            _record_write(report, "normalized_circuit", "normalized_circuit.json")
        else:
            _record_skip(report, "normalized_circuit")
    if core.get("compile_report") is not None:
        if _should_write(policy, "compile_report"):
            write_json(out / "compile_report.json", core["compile_report"])
            _record_write(report, "compile_report", "compile_report.json")
        else:
            _record_skip(report, "compile_report")
    if core.get("pulse_ir") is not None:
        if _should_write(policy, "pulse_ir"):
            write_json(out / "pulse_ir.json", asdict(core["pulse_ir"]))
            _record_write(report, "pulse_ir", "pulse_ir.json")
        else:
            _record_skip(report, "pulse_ir")
    if core.get("executable_model") is not None:
        if _should_write(policy, "executable_model"):
            write_json(out / "executable_model.json", asdict(core["executable_model"]))
            _record_write(report, "executable_model", "executable_model.json")
        else:
            _record_skip(report, "executable_model")
    if core.get("model_spec") is not None:
        if _should_write(policy, "model_spec"):
            write_json(out / "model_spec.json", asdict(core["model_spec"]))
            _record_write(report, "model_spec", "model_spec.json")
        else:
            _record_skip(report, "model_spec")
    if core.get("trace") is not None:
        if _should_write(policy, "trace"):
            write_trace_h5(core["trace"], out / "trace.h5")
            _record_write(report, "trace", "trace.h5")
        else:
            _record_skip(report, "trace")
    if core.get("pulse_samples_rel"):
        if _should_write(policy, "pulse_samples"):
            _record_write(report, "pulse_samples", str(core["pulse_samples_rel"]))
        else:
            _record_skip(report, "pulse_samples")

    if qec.get("syndrome") is not None:
        if _should_write(policy, "syndrome_frame"):
            write_json(out / "syndrome_frame.json", asdict(qec["syndrome"]))
            _record_write(report, "syndrome_frame", "syndrome_frame.json")
        else:
            _record_skip(report, "syndrome_frame")
    if qec.get("prior_model") is not None:
        if _should_write(policy, "prior_model"):
            write_json(out / "prior_model.json", asdict(qec["prior_model"]))
            _record_write(report, "prior_model", "prior_model.json")
        else:
            _record_skip(report, "prior_model")
    if qec.get("prior_report") is not None:
        if _should_write(policy, "prior_report"):
            write_json(out / "prior_report.json", qec["prior_report"])
            _record_write(report, "prior_report", "prior_report.json")
        else:
            _record_skip(report, "prior_report")
    if qec.get("prior_model") is not None and qec.get("prior_samples_rel"):
        if _should_write(policy, "prior_samples"):
            prior_rel = str(qec["prior_samples_rel"])
            write_prior_samples_npz(qec["prior_model"], out / prior_rel)
            _record_write(report, "prior_samples", prior_rel)
        else:
            _record_skip(report, "prior_samples")
    if qec.get("decoder_input") is not None:
        if _should_write(policy, "decoder_input"):
            write_json(out / "decoder_input.json", asdict(qec["decoder_input"]))
            _record_write(report, "decoder_input", "decoder_input.json")
        else:
            _record_skip(report, "decoder_input")
    if qec.get("decoder_output") is not None:
        if _should_write(policy, "decoder_output"):
            write_json(out / "decoder_output.json", asdict(qec["decoder_output"]))
            _record_write(report, "decoder_output", "decoder_output.json")
        else:
            _record_skip(report, "decoder_output")
    if qec.get("decoder_report") is not None:
        if _should_write(policy, "decoder_report"):
            write_json(out / "decoder_report.json", qec["decoder_report"])
            _record_write(report, "decoder_report", "decoder_report.json")
        else:
            _record_skip(report, "decoder_report")
    if qec.get("logical_error") is not None:
        if _should_write(policy, "logical_error"):
            write_json(out / "logical_error.json", asdict(qec["logical_error"]))
            _record_write(report, "logical_error", "logical_error.json")
        else:
            _record_skip(report, "logical_error")

    analysis_bundle = dict(analysis.get("analysis", {}) or {})
    if analysis_bundle.get("observables") is not None:
        if _should_write(policy, "observables"):
            write_json(out / "observables.json", analysis_bundle.get("observables", {}))
            _record_write(report, "observables", "observables.json")
        else:
            _record_skip(report, "observables")
    if analysis_bundle.get("report") is not None:
        if _should_write(policy, "report"):
            write_json(out / "report.json", analysis_bundle.get("report", {}))
            _record_write(report, "report", "report.json")
        else:
            _record_skip(report, "report")
    if analysis.get("sensitivity_report") is not None:
        if _should_write(policy, "sensitivity_report"):
            write_json(out / "sensitivity_report.json", analysis["sensitivity_report"])
            _record_write(report, "sensitivity_report", "sensitivity_report.json")
        else:
            _record_skip(report, "sensitivity_report")
        if _should_write(policy, "sensitivity_heatmap"):
            write_sensitivity_heatmap(analysis["sensitivity_report"], out / "figures" / "sensitivity_heatmap.png")
            _record_write(report, "sensitivity_heatmap", "figures/sensitivity_heatmap.png")
        else:
            _record_skip(report, "sensitivity_heatmap")
    if analysis.get("error_budget_v2") is not None:
        if _should_write(policy, "error_budget_v2"):
            write_json(out / "error_budget_v2.json", analysis["error_budget_v2"])
            _record_write(report, "error_budget_v2", "error_budget_v2.json")
        else:
            _record_skip(report, "error_budget_v2")
    if analysis.get("settings_report") is not None:
        if _should_write(policy, "settings_report"):
            write_json(out / "settings_report.json", analysis["settings_report"])
            _record_write(report, "settings_report", "settings_report.json")
        else:
            _record_skip(report, "settings_report")

    if optional.get("pauli_plus_analysis") and optional.get("scaling_report") is not None and optional.get("error_budget_pauli_plus") is not None:
        if _should_write(policy, "scaling_report"):
            write_json(out / "scaling_report.json", optional["scaling_report"])
            _record_write(report, "scaling_report", "scaling_report.json")
        else:
            _record_skip(report, "scaling_report")
        if _should_write(policy, "error_budget_pauli_plus"):
            write_json(out / "error_budget_pauli_plus.json", optional["error_budget_pauli_plus"])
            _record_write(report, "error_budget_pauli_plus", "error_budget_pauli_plus.json")
        else:
            _record_skip(report, "error_budget_pauli_plus")
        if optional.get("component_model") is not None:
            if _should_write(policy, "component_ablation"):
                write_component_ablation_csv(
                    component_model=optional["component_model"],
                    budget=optional["error_budget_pauli_plus"],
                    out_path=out / "component_ablation.csv",
                )
                _record_write(report, "component_ablation", "component_ablation.csv")
            else:
                _record_skip(report, "component_ablation")

    if optional.get("decoder_eval") and optional.get("decoder_eval_report") is not None:
        if _should_write(policy, "decoder_eval_report"):
            write_json(out / "decoder_eval_report.json", optional["decoder_eval_report"])
            _record_write(report, "decoder_eval_report", "decoder_eval_report.json")
        else:
            _record_skip(report, "decoder_eval_report")
        if _should_write(policy, "decoder_eval_table"):
            write_decoder_eval_csv(list(optional.get("decoder_eval_rows", []) or []), out / "decoder_eval_table.csv")
            _record_write(report, "decoder_eval_table", "decoder_eval_table.csv")
        else:
            _record_skip(report, "decoder_eval_table")
        if _should_write(policy, "decoder_pareto"):
            write_decoder_pareto_png(optional["decoder_eval_report"], out / "figures" / "decoder_pareto.png")
            _record_write(report, "decoder_pareto", "figures/decoder_pareto.png")
        else:
            _record_skip(report, "decoder_pareto")
        if _should_write(policy, "batch_manifest"):
            write_json(out / "batch_manifest.json", optional.get("decoder_eval_batch_manifest") or {"schema_version": "1.0"})
            _record_write(report, "batch_manifest", "batch_manifest.json")
        else:
            _record_skip(report, "batch_manifest")
        if _should_write(policy, "resume_state"):
            write_json(out / "resume_state.json", optional.get("decoder_eval_resume_state") or {"schema_version": "1.0"})
            _record_write(report, "resume_state", "resume_state.json")
        else:
            _record_skip(report, "resume_state")
        if _should_write(policy, "failed_tasks"):
            write_failed_tasks_jsonl(list(optional.get("failed_eval_tasks", []) or []), out / "failed_tasks.jsonl")
            _record_write(report, "failed_tasks", "failed_tasks.jsonl")
        else:
            _record_skip(report, "failed_tasks")

    if optional.get("cross_engine_compare") is not None:
        if _should_write(policy, "cross_engine_compare"):
            write_json(out / "cross_engine_compare.json", optional["cross_engine_compare"])
            _record_write(report, "cross_engine_compare", "cross_engine_compare.json")
        else:
            _record_skip(report, "cross_engine_compare")

    return report


def export_visualizations(
    *,
    out: Path,
    policy: ArtifactWritePolicy,
    export_plots: bool,
    export_dxf: bool,
    circuit,
    pulse_ir,
    trace,
    analysis: dict,
) -> dict[str, str]:
    """Export optional figure artifacts and return produced logical output map."""
    policy = _normalized_policy(policy)
    if not policy.persist_artifacts:
        return {}

    selected = policy.selected_outputs if policy.artifact_mode == "targeted" else None
    viz_outputs: dict[str, str] = {}
    if export_plots:
        if selected is None or "circuit_diagram" in selected:
            circuit_png = export_circuit_diagram(circuit, out)
            if circuit_png:
                viz_outputs["circuit_diagram"] = circuit_png
        viz_outputs.update(
            export_result_figures(
                pulse_ir,
                trace,
                analysis,
                out,
                export_dxf=export_dxf,
                selected_outputs=selected,
            )
        )
        return viz_outputs

    if export_dxf and (selected is None or "timing_diagram" in selected):
        try:
            EngineeringDrawer.export_dxf(pulse_ir, out / "timing_diagram.dxf", style={"title": "qsim timing"})
            viz_outputs["timing_diagram"] = "timing_diagram.dxf"
        except Exception:
            pass
    return viz_outputs


def gather_dependencies(*, trace, selected_engine_name: str) -> dict[str, str]:
    """Collect package/runtime dependency fingerprints for manifest."""
    deps: dict[str, str] = {}
    for name in ["numpy", "h5py", "PyYAML", "qutip", "qiskit", "ezdxf"]:
        try:
            deps[name] = ilm.version(name)
        except ilm.PackageNotFoundError:
            pass
    deps.update(collect_runtime_dependencies(trace, selected_engine_name))
    return deps


def build_manifest(
    *,
    out: Path,
    cfg_seed: int,
    backend_path: str,
    qasm_text: str,
    dependencies: dict[str, str],
    outputs: dict[str, str],
) -> RunManifest:
    """Build run manifest object without persisting."""
    return RunManifest(
        run_id=out.name,
        random_seed=cfg_seed,
        inputs={
            "backend": str(Path(backend_path)),
            "qasm_inline": "<inline>",
            "qasm_sha256": sha256_text(qasm_text),
        },
        outputs=dict(outputs),
        dependencies=dependencies,
    )


__all__ = [
    "ArtifactPayload",
    "ArtifactWritePolicy",
    "ArtifactWriteReport",
    "build_manifest",
    "export_visualizations",
    "gather_dependencies",
    "write_artifacts",
]
