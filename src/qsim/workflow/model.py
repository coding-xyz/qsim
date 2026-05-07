"""Model-first workflow API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any

import numpy as np

from qsim.analysis import MetricRegistry, build_default_metric_registry
from qsim.common.schemas import Trajectory, write_json
from qsim.pulse.visualize import load_trajectory_h5
from qsim.workflow.contracts import (
    DefaultAnalyserConfig,
    WorkflowDeviceConfig,
    WorkflowFeatureFlags,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
    compose_workflow_task,
)
from qsim.workflow.output import resolve_writable_out_dir, write_trajectory_h5
from qsim.workflow.planner import build_execution_plan
from qsim.workflow.stages import parse_compile_lower_model, run_analysis_stage, run_decode_stage, run_engine_stage
from qsim.workflow.task_io import (
    load_analyser_config_file,
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
    load_task_config_file,
)

_UNSET = object()

_MANAGED_TOP_LEVEL_FILES = {
    'task.json',
    'device.json',
    'pulse.json',
    'circuit.json',
    'normalized_circuit.json',
    'model_manifest.json',
    # Legacy persistence artifacts from the older workflow layout.
    'backend_config.json',
    'compile_report.json',
    'pulse_ir.json',
    'executable_model.json',
    'model_spec.json',
    'trace.h5',
    'analysis_trace.json',
    'analysis_metrics.json',
    'analysis_readout.json',
    'analysis_iq.json',
    'report.json',
    'settings_report.json',
    'timings.json',
    'run_manifest.json',
    'runtime_metadata.json',
}


def _public_value(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _public_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding='utf-8')))


def _is_small_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _summarize_runtime_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        summary: dict[str, Any] = {'kind': 'dict', 'size': len(value)}
        if 'snapshots' in value and isinstance(value.get('snapshots'), list):
            summary['snapshots'] = len(value.get('snapshots') or [])
        if 'runs' in value and isinstance(value.get('runs'), list):
            summary['runs'] = len(value.get('runs') or [])
        if 'actual_kind' in value:
            summary['actual_kind'] = value.get('actual_kind')
        if 'requested_kind' in value:
            summary['requested_kind'] = value.get('requested_kind')
        return summary
    if isinstance(value, list):
        return {'kind': 'list', 'size': len(value)}
    return {'kind': type(value).__name__}


def _compact_runtime_details(details: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(details or {})
    compact: dict[str, Any] = {}
    bulky_keys = {'quantum_state_trajectory', 'readout_observables', 'measurement_records', 'jump_events'}
    for key, value in raw.items():
        if key in bulky_keys:
            compact[key] = _summarize_runtime_payload(value)
            continue
        if _is_small_scalar(value):
            compact[key] = value
            continue
        if isinstance(value, dict):
            if all(_is_small_scalar(child) for child in value.values()) and len(value) <= 24:
                compact[key] = dict(value)
            else:
                compact[key] = _summarize_runtime_payload(value)
            continue
        if isinstance(value, list):
            if len(value) <= 24 and all(_is_small_scalar(item) for item in value):
                compact[key] = list(value)
            else:
                compact[key] = _summarize_runtime_payload(value)
            continue
        compact[key] = _summarize_runtime_payload(value)
    return compact


def _clear_managed_save_paths(out: Path) -> None:
    def _retry_unlink(path: Path) -> None:
        for _ in range(20):
            try:
                path.unlink()
                return
            except PermissionError:
                try:
                    os.chmod(path, 0o666)
                except OSError:
                    pass
                time.sleep(0.05)
        path.unlink()

    def _on_rmtree_error(func, path_str, _exc_info) -> None:
        try:
            os.chmod(path_str, 0o666)
        except OSError:
            pass
        func(path_str)

    for name in _MANAGED_TOP_LEVEL_FILES:
        path = out / name
        if path.exists():
            try:
                _retry_unlink(path)
            except PermissionError:
                pass
    for dirname in ('results',):
        path = out / dirname
        if path.exists():
            for _ in range(20):
                try:
                    shutil.rmtree(path, onerror=_on_rmtree_error)
                    break
                except PermissionError:
                    time.sleep(0.05)
            else:
                shutil.rmtree(path, onerror=_on_rmtree_error)


def _normalize_named_paths(
    value: str | Path | dict[str, str | Path] | None,
    *,
    default_id_prefix: str,
    fallback_path: str | None,
) -> dict[str, str]:
    if isinstance(value, dict):
        normalized: dict[str, str] = {}
        for key, raw in value.items():
            normalized[str(key)] = str(Path(raw).resolve())
        return normalized
    if value is not None:
        return {f'{default_id_prefix}_0': str(Path(value).resolve())}
    if fallback_path:
        return {f'{default_id_prefix}_0': str(Path(fallback_path).resolve())}
    return {}


def _bind_loaded_analyser(
    *,
    analyser_id: str,
    analyser_cfg: DefaultAnalyserConfig,
    solver_ids: list[str],
) -> DefaultAnalyserConfig:
    bound_cfg = DefaultAnalyserConfig(**analyser_cfg.to_payload())
    bound_solver_id = str(bound_cfg.solver_id or '').strip()
    if bound_solver_id:
        if bound_solver_id not in solver_ids:
            raise KeyError(f'Analyser `{analyser_id}` references unknown solver_id `{bound_solver_id}`.')
        bound_cfg.solver_id = bound_solver_id
        return bound_cfg
    if len(solver_ids) == 1:
        bound_cfg.solver_id = solver_ids[0]
        return bound_cfg
    raise ValueError(
        f'Analyser `{analyser_id}` must declare solver_id when the model has multiple solvers.'
    )


def _effective_analyser_payload(
    analyser_cfg: DefaultAnalyserConfig | None,
    *,
    solver_cfg: WorkflowSolverConfig,
) -> dict[str, Any]:
    if analyser_cfg is not None:
        payload = analyser_cfg.to_payload()
        if payload:
            return payload
    requested_kind = 'wave_function' if str(solver_cfg.run.solver_mode or '').strip().lower() == 'mcwf' else 'density_matrix'
    return {
        'trajectory': {
            'quantum': requested_kind,
            'save_times': 'all',
            'save_final_state': True,
            'save_jump_events': False,
            'save_measurement_records': True,
        }
    }


@dataclass(slots=True)
class AnalysisResult:
    """Derived analyser outputs."""

    analyser_id: str | None = None
    trajectory_id: str | None = None
    metrics: dict[str, Any] | None = None
    readout: dict[str, Any] | None = None
    iq: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None
    error_budget: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.analyser_id:
            payload["analyser_id"] = str(self.analyser_id)
        if self.trajectory_id:
            payload["trajectory_id"] = str(self.trajectory_id)
        if self.metrics:
            payload["metrics"] = dict(self.metrics)
        if self.readout:
            payload["readout"] = dict(self.readout)
        if self.iq:
            payload["iq"] = dict(self.iq)
        if self.report:
            payload["report"] = dict(self.report)
        if self.sensitivity:
            payload["sensitivity"] = dict(self.sensitivity)
        if self.error_budget:
            payload["error_budget"] = dict(self.error_budget)
        return payload

    def __getattribute__(self, name: str):
        if name == "__annotations__":
            cls_annotations = type(self).__dict__.get("__annotations__", {})
            payload_keys = set(object.__getattribute__(self, "to_payload")().keys())
            return {key: value for key, value in cls_annotations.items() if key in payload_keys}
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        return f"AnalysisResult({self.to_payload()!r})"


@dataclass(slots=True)
class SolverRunResult:
    """Per-solver runtime artifacts and aligned results."""

    solver_id: str | None = None
    study_name: str | None = None
    study_index: int | None = None
    runtime_task: WorkflowTask | None = None
    compile_report: dict[str, Any] | None = None
    pulse_ir: Any | None = None
    executable_model: Any | None = None
    model_spec: Any | None = None
    trajectory: Trajectory | None = None
    analyses: dict[str, AnalysisResult] = field(default_factory=dict)
    decoder_outputs: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ModelResults:
    """All runtime outputs aligned by solver/analyser ids."""

    solver_runs: dict[str, SolverRunResult] = field(default_factory=dict)

    def ensure_solver(self, solver_id: str) -> SolverRunResult:
        if solver_id not in self.solver_runs:
            self.solver_runs[solver_id] = SolverRunResult()
        return self.solver_runs[solver_id]

    def study_run_ids(self, solver_id: str) -> list[str]:
        return sorted(
            run_id
            for run_id, result in self.solver_runs.items()
            if (result.solver_id or run_id) == solver_id and result.study_name
        )

    @property
    def trajectories(self) -> dict[str, Trajectory]:
        flattened = {
            solver_id: result.trajectory
            for solver_id, result in self.solver_runs.items()
            if result.trajectory is not None
        }
        aliases: dict[str, tuple[tuple[float, str], Trajectory]] = {}
        for run_id, result in self.solver_runs.items():
            if result.trajectory is None:
                continue
            solver_id = result.solver_id or run_id
            if solver_id in flattened:
                continue
            order = float(result.study_index) if result.study_index is not None else math.inf
            key = ((order, run_id))
            current = aliases.get(solver_id)
            if current is None or key < current[0]:
                aliases[solver_id] = (key, result.trajectory)
        for solver_id, (_, trajectory) in aliases.items():
            flattened[solver_id] = trajectory
        return flattened

    @property
    def analyses(self) -> dict[str, AnalysisResult]:
        flattened: dict[str, AnalysisResult] = {}
        for result in self.solver_runs.values():
            for analyser_id, analysis in result.analyses.items():
                flattened[analyser_id] = analysis
        return flattened


@dataclass(slots=True)
class Model:
    """Top-down editable model object."""

    task: WorkflowTaskConfig
    device: WorkflowDeviceConfig
    pulse: dict[str, Any]
    solvers: dict[str, WorkflowSolverConfig]
    analysers: dict[str, DefaultAnalyserConfig] = field(default_factory=dict)
    metric_registry: MetricRegistry = field(default_factory=build_default_metric_registry)
    out_dir: str | None = None
    circuit: Any | None = None
    normalized_circuit: Any | None = None
    results: ModelResults = field(default_factory=ModelResults)

    def __repr__(self) -> str:
        trajectory_ids = sorted(self.results.trajectories.keys())
        analysis_ids = sorted(self.results.analyses.keys())
        return (
            'Model('
            f'solvers={sorted(self.solvers.keys())}, '
            f'analysers={[(analyser_id, cfg.solver_id) for analyser_id, cfg in sorted(self.analysers.items())]}, '
            f'trajectories={trajectory_ids}, '
            f'analyses={analysis_ids}'
            ')'
        )

    @staticmethod
    def _safe_study_token(value: str) -> str:
        token = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
        return token.strip("_") or "study"

    def _study_entries(self, solver_cfg: WorkflowSolverConfig) -> list[tuple[int | None, dict[str, Any]]]:
        entries = [dict(step) for step in list(solver_cfg.study or []) if isinstance(step, dict)]
        if not entries:
            return [(None, {})]
        return [(idx, step) for idx, step in enumerate(entries)]

    def _study_name(self, study: dict[str, Any], study_index: int | None) -> str | None:
        if not study:
            return None
        raw = str(study.get('name', '') or '').strip()
        if raw:
            return raw
        if study_index is None:
            return None
        return f'study_{study_index}'

    def _run_id_for_study(
        self,
        *,
        solver_id: str,
        study: dict[str, Any],
        study_index: int | None,
        total_studies: int,
    ) -> str:
        if total_studies <= 1:
            return solver_id
        study_name = self._study_name(study, study_index)
        if not study_name:
            return solver_id
        return f'{solver_id}__{self._safe_study_token(study_name)}'

    def _analysis_id_for_study(
        self,
        *,
        analyser_id: str,
        study: dict[str, Any],
        study_index: int | None,
        total_studies: int,
    ) -> str:
        if total_studies <= 1:
            return analyser_id
        study_name = self._study_name(study, study_index)
        if not study_name:
            return analyser_id
        return f'{analyser_id}__{self._safe_study_token(study_name)}'

    def _clone_solver_cfg_with_single_study(
        self,
        solver_cfg: WorkflowSolverConfig,
        *,
        study: dict[str, Any],
    ) -> WorkflowSolverConfig:
        return WorkflowSolverConfig(
            backend=type(solver_cfg.backend)(**asdict(solver_cfg.backend)),
            run=type(solver_cfg.run)(**asdict(solver_cfg.run)),
            frame=type(solver_cfg.frame)(**asdict(solver_cfg.frame)),
            study=[dict(study)] if study else None,
        )

    def _clear_solver_results(self, solver_id: str) -> None:
        for run_id in list(self.results.solver_runs.keys()):
            result = self.results.solver_runs[run_id]
            if (result.solver_id or run_id) == solver_id:
                self.results.solver_runs.pop(run_id, None)

    def _find_run_id(
        self,
        *,
        solver_id: str,
        study_name: str | None = None,
    ) -> str | None:
        candidates: list[tuple[str, SolverRunResult]] = [
            (run_id, bundle)
            for run_id, bundle in self.results.solver_runs.items()
            if (bundle.solver_id or run_id) == solver_id and bundle.trajectory is not None
        ]
        if study_name is None:
            if len(candidates) == 1:
                return candidates[0][0]
            return None
        wanted = str(study_name).strip()
        for run_id, bundle in candidates:
            if str(bundle.study_name or '').strip() == wanted:
                return run_id
        return None

    @staticmethod
    def _nearest_centroid(point: complex, centroids: dict[str, complex]) -> str:
        if not centroids:
            return ""
        return min(centroids, key=lambda label: abs(point - centroids[label]))

    @staticmethod
    def _study_label(bundle: SolverRunResult, analysis: AnalysisResult) -> str | None:
        runtime_task = bundle.runtime_task
        if runtime_task is not None:
            task_input = getattr(runtime_task, "input", None)
            study_steps = list(getattr(task_input, "study", []) or []) if task_input is not None else []
            if study_steps:
                prep_state = dict(study_steps[0].get("prep_state", {}) or {})
                prep_label = str(prep_state.get("label", "") or "").strip()
                if prep_label:
                    return prep_label
        iq_payload = dict(analysis.iq or {})
        labels = [str(item).strip() for item in list(iq_payload.get("labels", []) or []) if str(item).strip()]
        if labels:
            return labels[0]
        study_name = str(bundle.study_name or "").strip()
        if study_name:
            return study_name
        return None

    def _build_multi_study_iq_summary(self, analysis_items: list[tuple[SolverRunResult, AnalysisResult]]) -> dict[str, Any] | None:
        if len(analysis_items) <= 1:
            return None
        centroids: dict[str, complex] = {}
        clouds: dict[str, list[list[float]]] = {}
        study_map: dict[str, str] = {}
        noise_sigmas: list[float] = []
        for bundle, analysis in analysis_items:
            iq_payload = dict(analysis.iq or {})
            label = self._study_label(bundle, analysis)
            if not label:
                continue
            centroid_map = dict(iq_payload.get('centroids', {}) or {})
            centroid_raw = None
            if label in centroid_map:
                centroid_raw = centroid_map.get(label)
            elif centroid_map:
                centroid_raw = next(iter(centroid_map.values()))
            if not isinstance(centroid_raw, list | tuple) or len(centroid_raw) < 2:
                continue
            centroids[label] = complex(float(centroid_raw[0]), float(centroid_raw[1]))
            cloud_source = dict(iq_payload.get('synthetic_clouds', {}) or {})
            raw_cloud = cloud_source.get(label)
            if raw_cloud is None and cloud_source:
                raw_cloud = next(iter(cloud_source.values()))
            clouds[label] = [
                [float(point[0]), float(point[1])]
                for point in list(raw_cloud or [])
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ]
            study_map[label] = str(bundle.study_name or '')
            try:
                noise_sigmas.append(float(iq_payload.get('noise_sigma', 0.0) or 0.0))
            except Exception:
                pass
        labels = list(centroids.keys())
        if len(labels) <= 1:
            return None
        confusion = np.zeros((len(labels), len(labels)), dtype=int)
        for i, label in enumerate(labels):
            for point_raw in clouds.get(label, []):
                point = complex(float(point_raw[0]), float(point_raw[1]))
                pred = self._nearest_centroid(point, centroids)
                if pred in labels:
                    confusion[i, labels.index(pred)] += 1
        assignment_fidelity = float(np.trace(confusion) / max(1, confusion.sum())) if confusion.size else 0.0
        pairwise_distances = [
            abs(centroids[a] - centroids[b])
            for i, a in enumerate(labels)
            for b in labels[i + 1 :]
        ]
        noise_sigma = float(np.mean(noise_sigmas)) if noise_sigmas else 0.0
        cluster_separation = float(min(pairwise_distances) / max(noise_sigma, 1.0e-12)) if pairwise_distances else 0.0
        snr = float((np.mean(pairwise_distances) if pairwise_distances else 0.0) / max(2.0 * noise_sigma, 1.0e-12))
        return {
            "schema_version": "1.0",
            "labels": labels,
            "centroids": {label: [float(val.real), float(val.imag)] for label, val in centroids.items()},
            "synthetic_clouds": clouds,
            "confusion_matrix": {"labels": labels, "values": confusion.astype(int).tolist()},
            "assignment_fidelity": assignment_fidelity,
            "cluster_separation": cluster_separation,
            "snr": snr,
            "study_map": study_map,
        }

    def _require_solver_id(self, solver_id: str | None) -> str:
        if solver_id:
            if solver_id not in self.solvers:
                raise KeyError(f'Unknown solver_id: {solver_id}')
            return solver_id
        if len(self.solvers) == 1:
            return next(iter(self.solvers))
        raise ValueError('solver_id is required when the model has multiple solvers.')

    def _require_analyser_id(self, analyser_id: str | None) -> str:
        if analyser_id:
            if analyser_id not in self.analysers:
                raise KeyError(f'Unknown analyser_id: {analyser_id}')
            return analyser_id
        if len(self.analysers) == 1:
            return next(iter(self.analysers))
        raise ValueError('analyser_id is required when the model has multiple analysers.')

    def _compose_runtime_task(
        self,
        *,
        solver_cfg: WorkflowSolverConfig,
        analyser_cfg: DefaultAnalyserConfig | None,
    ) -> WorkflowTask:
        device_cfg = WorkflowDeviceConfig(
            device=dict(self.device.device or {}) or None,
            pulse={**dict(self.device.pulse or {}), **dict(self.pulse or {})} or None,
            noise=dict(self.device.noise or {}) or None,
        )
        if analyser_cfg is None:
            default_payload = _effective_analyser_payload(analyser_cfg, solver_cfg=solver_cfg)
            effective_analyser = DefaultAnalyserConfig(
                trajectory=dict(default_payload.get('trajectory', {}) or {}) or None,
            )
        else:
            effective_analyser = analyser_cfg
        return compose_workflow_task(
            self.task,
            solver_cfg,
            device_cfg,
            effective_analyser,
            backend_source=self.task.input.solver_config_path,
        )

    def _run_one_solver_study(
        self,
        *,
        solver_id: str,
        solver_cfg: WorkflowSolverConfig,
        study: dict[str, Any],
        study_index: int | None,
        total_studies: int,
    ) -> str:
        selected_solver_id = self._require_solver_id(solver_id)
        default_analyser = None
        if self.analysers:
            bound = [cfg for cfg in self.analysers.values() if str(cfg.solver_id or '').strip() == selected_solver_id]
            default_analyser = bound[0] if bound else None
        single_solver_cfg = self._clone_solver_cfg_with_single_study(solver_cfg, study=study)
        task = self._compose_runtime_task(solver_cfg=single_solver_cfg, analyser_cfg=default_analyser)
        run_id = self._run_id_for_study(
            solver_id=selected_solver_id,
            study=study,
            study_index=study_index,
            total_studies=total_studies,
        )
        study_name = self._study_name(study, study_index)

        run_started_at = time.perf_counter()
        timings: dict[str, float] = {}
        preferred_out = Path(task.output.out_dir)
        if total_studies > 1 and study_name:
            preferred_out = preferred_out / self._safe_study_token(study_name)
        out = resolve_writable_out_dir(preferred_out)
        self.out_dir = str(out)
        plan = build_execution_plan(task)

        started_at = time.perf_counter()
        parsed = parse_compile_lower_model(
            qasm_text=task.input.qasm_text,
            backend_path=task.input.backend_path,
            backend_config=task.input.backend_config,
            out=out,
            device=(task.input.device_model or task.input.device),
            pulse=task.input.pulse,
            frame=task.input.frame,
            analyser=task.input.analyser,
            study=task.input.study,
            schedule_policy=task.input.schedule_policy,
            reset_feedback_policy=task.input.reset_feedback_policy,
            noise=task.input.noise,
            solver_run={
                'dt_s': task.run.dt_s,
                't_end_s': task.run.t_end_s,
                't_padding_s': task.run.t_padding_s,
                'seed': task.run.seed,
                'ntraj': task.run.mcwf_ntraj,
                'qutip_options': task.run.qutip_options,
                'native_options': task.run.native_options,
                'backend_options': task.run.backend_options,
                'one_over_f_components': task.run.one_over_f_components,
            },
            solver_mode=task.run.solver_mode,
            param_bindings=task.input.param_bindings,
            persist_artifacts=task.output.persist_artifacts,
        )
        timings.update(parsed.get('timings', {}))
        timings['build'] = time.perf_counter() - started_at
        self.circuit = parsed['circuit']
        self.normalized_circuit = parsed['normalized']

        started_at = time.perf_counter()
        trajectory = run_engine_stage(
            model_spec=parsed['model_spec'],
            cfg=parsed['cfg'],
            engine=task.run.engine,
            allow_mock_fallback=task.run.allow_mock_fallback,
            julia_bin=task.run.julia_bin,
            julia_depot_path=task.run.julia_depot_path,
            julia_timeout_s=task.run.julia_timeout_s,
            mcwf_ntraj=task.run.mcwf_ntraj,
        )
        timings['solver'] = time.perf_counter() - started_at

        decoded = {
            'logical_error': None,
            'decoder_input': None,
            'decoder_output': None,
            'decoder_report': None,
            'prior_model': None,
            'prior_report': None,
            'syndrome': None,
        }
        if plan.run_decode:
            started_at = time.perf_counter()
            decoded = run_decode_stage(
                trajectory=trajectory,
                circuit=parsed['circuit'],
                model_spec=parsed['model_spec'],
                engine=task.run.engine,
                cfg=parsed['cfg'],
                prior_backend=task.run.prior_backend,
                decoder=task.run.decoder,
                decoder_options=task.run.decoder_options,
            )
            timings['decode'] = time.perf_counter() - started_at

        timings['total'] = time.perf_counter() - run_started_at
        bundle = self.results.ensure_solver(run_id)
        bundle.analyses = {}
        bundle.solver_id = selected_solver_id
        bundle.study_name = study_name
        bundle.study_index = study_index
        bundle.runtime_task = task
        bundle.compile_report = _public_value(parsed['compile_report'])
        bundle.pulse_ir = parsed['pulse_ir']
        bundle.executable_model = parsed['executable']
        bundle.model_spec = parsed['model_spec']
        bundle.trajectory = trajectory
        bundle.decoder_outputs = decoded
        bundle.runtime_metadata = {
            'engine_requested': task.run.engine,
            'engine_used': trajectory.engine,
            'solver_mode': str(task.run.solver_mode or parsed['model_spec'].solver),
            'targets': list(plan.targets),
            'template': str(plan.template),
            'timings': timings,
            'details': _compact_runtime_details(dict(trajectory.metadata or {}).get('details', {})),
            'out_dir': str(out),
            'solver_id': selected_solver_id,
            'run_id': run_id,
            'study_name': study_name,
            'study_index': study_index,
        }
        return run_id

    def run_study(
        self,
        *,
        solver_id: str | None = None,
        study_name: str | None = None,
        study_index: int | None = None,
    ) -> str:
        """Compile and solve one specific study step into ``model.results``."""
        selected_solver_id = self._require_solver_id(solver_id)
        solver_cfg = self.solvers[selected_solver_id]
        entries = self._study_entries(solver_cfg)
        chosen_index: int | None = None
        chosen_study: dict[str, Any] | None = None
        if study_name is not None:
            wanted = str(study_name).strip()
            for idx, step in entries:
                if str(self._study_name(step, idx) or '').strip() == wanted:
                    chosen_index = idx
                    chosen_study = dict(step)
                    break
            if chosen_study is None:
                raise KeyError(f'Unknown study `{wanted}` for solver `{selected_solver_id}`.')
        elif study_index is not None:
            for idx, step in entries:
                if idx == study_index:
                    chosen_index = idx
                    chosen_study = dict(step)
                    break
            if chosen_study is None:
                raise IndexError(f'Unknown study index `{study_index}` for solver `{selected_solver_id}`.')
        else:
            if len(entries) != 1:
                raise ValueError(f'study_name or study_index is required for solver `{selected_solver_id}` with multiple study steps.')
            chosen_index, chosen_study = entries[0]
        assert chosen_study is not None
        run_id = self._run_id_for_study(
            solver_id=selected_solver_id,
            study=chosen_study,
            study_index=chosen_index,
            total_studies=len(entries),
        )
        self.results.solver_runs.pop(run_id, None)
        if len(entries) > 1:
            aggregate_bundle = self.results.solver_runs.get(selected_solver_id)
            if aggregate_bundle is not None:
                aggregate_bundle.analyses = {}
        return self._run_one_solver_study(
            solver_id=selected_solver_id,
            solver_cfg=solver_cfg,
            study=chosen_study,
            study_index=chosen_index,
            total_studies=len(entries),
        )

    def run_solver(self, solver_id: str | None = None) -> None:
        """Compile and solve one configured solver, running every study step by default."""
        selected_solver_id = self._require_solver_id(solver_id)
        solver_cfg = self.solvers[selected_solver_id]
        self._clear_solver_results(selected_solver_id)
        entries = self._study_entries(solver_cfg)
        for idx, step in entries:
            self._run_one_solver_study(
                solver_id=selected_solver_id,
                solver_cfg=solver_cfg,
                study=dict(step),
                study_index=idx,
                total_studies=len(entries),
            )

    def run_analysis(self, *, analyser_id: str | None = None, study_name: str | None = None) -> None:
        """Run one analyser against every matching study trajectory into ``model.results``."""
        selected_analyser_id = self._require_analyser_id(analyser_id)
        analyser_cfg = self.analysers[selected_analyser_id]
        selected_solver_id = self._require_solver_id(analyser_cfg.solver_id)
        matching_runs = [
            (run_id, bundle)
            for run_id, bundle in self.results.solver_runs.items()
            if (bundle.solver_id or run_id) == selected_solver_id and bundle.trajectory is not None
        ]
        if study_name is not None:
            matching_runs = [
                (run_id, bundle)
                for run_id, bundle in matching_runs
                if str(bundle.study_name or '').strip() == str(study_name).strip()
            ]
        if not matching_runs:
            raise ValueError(f'Solver `{selected_solver_id}` has not been run yet.')

        per_study_analyses: list[tuple[SolverRunResult, AnalysisResult]] = []
        total_studies = len(matching_runs)
        for run_id, solver_bundle in matching_runs:
            cfg = getattr(solver_bundle.runtime_task, 'input', None).backend_config if solver_bundle.runtime_task else None
            if cfg is None:
                raise ValueError(f'Missing runtime task/backend config for solver `{selected_solver_id}`.')
            logical_error = None
            if solver_bundle.decoder_outputs:
                logical_error = solver_bundle.decoder_outputs.get('logical_error')

            started_at = time.perf_counter()
            analyzed = run_analysis_stage(
                trajectory=solver_bundle.trajectory,
                model_spec=solver_bundle.model_spec,
                pulse_ir=solver_bundle.pulse_ir,
                pulse_cfg={**dict(self.device.pulse or {}), **dict(self.pulse or {})},
                cfg=cfg,
                logical_error=logical_error,
                analyser_cfg=analyser_cfg.to_payload(),
                metric_registry=self.metric_registry,
            )
            analysis_bundle = dict(analyzed.get('analysis', {}) or {})
            analysis_run_id = self._analysis_id_for_study(
                analyser_id=selected_analyser_id,
                study={"name": solver_bundle.study_name} if solver_bundle.study_name else {},
                study_index=solver_bundle.study_index,
                total_studies=total_studies,
            )
            analysis_result = AnalysisResult(
                analyser_id=analysis_run_id,
                trajectory_id=run_id,
                metrics=dict(analysis_bundle.get('metrics', {}) or {}) or None,
                readout=dict(analysis_bundle.get('readout', {}) or {}) or None,
                iq=dict(analysis_bundle.get('iq', {}) or {}) or None,
                report=dict(analysis_bundle.get('report', {}) or {}) or None,
                sensitivity=_public_value(analyzed.get('sensitivity_report')),
                error_budget=_public_value(analyzed.get('error_budget_v2')),
            )
            solver_bundle.analyses[analysis_run_id] = analysis_result
            per_study_analyses.append((solver_bundle, analysis_result))
            runtime_meta = dict(solver_bundle.runtime_metadata or {})
            timings = dict(runtime_meta.get('timings', {}) or {})
            timings[f'analysis:{selected_analyser_id}'] = time.perf_counter() - started_at
            runtime_meta['timings'] = timings
            solver_bundle.runtime_metadata = runtime_meta

        if study_name is None:
            aggregate_bundle = self.results.ensure_solver(selected_solver_id)
            aggregate_bundle.solver_id = selected_solver_id
            aggregate_bundle.study_name = None
            summary_iq = self._build_multi_study_iq_summary(per_study_analyses)
            if total_studies == 1:
                aggregate_bundle.analyses[selected_analyser_id] = per_study_analyses[0][1]
            elif summary_iq is not None:
                aggregate_bundle.analyses[selected_analyser_id] = AnalysisResult(
                    analyser_id=selected_analyser_id,
                    trajectory_id=selected_solver_id,
                    iq=summary_iq,
                )

    def run_all(self) -> None:
        """Run every configured solver and then every configured analyser."""
        for solver_id in sorted(self.solvers.keys()):
            self.run_solver(solver_id)
        for analyser_id in sorted(self.analysers.keys()):
            self.run_analysis(analyser_id=analyser_id)

    def run(self) -> None:
        """Run all configured solvers and analysers."""
        self.run_all()

    def get_trajectory(self, solver_id: str | None = None, *, study_name: str | None = None) -> Trajectory | None:
        selected_solver_id = self._require_solver_id(solver_id)
        if study_name is None:
            bundle = self.results.ensure_solver(selected_solver_id)
            if bundle.trajectory is not None:
                return bundle.trajectory
        run_id = self._find_run_id(solver_id=selected_solver_id, study_name=study_name)
        if run_id is None:
            if study_name is None:
                raise ValueError(f'study_name is required to disambiguate solver `{selected_solver_id}` results.')
            return None
        return self.results.ensure_solver(run_id).trajectory

    def get_analysis(self, *, analyser_id: str | None = None, study_name: str | None = None) -> AnalysisResult | None:
        selected_analyser_id = self._require_analyser_id(analyser_id)
        if study_name is None:
            direct = self.results.analyses.get(selected_analyser_id)
            if direct is not None:
                return direct
            return None
        token = self._safe_study_token(study_name)
        return self.results.analyses.get(f'{selected_analyser_id}__{token}')

    def add_solver(self, solver_id: str, solver_cfg: WorkflowSolverConfig) -> None:
        self.solvers[str(solver_id)] = solver_cfg

    def add_analyser(self, analyser_id: str, solver_id: str, analyser_cfg: DefaultAnalyserConfig) -> None:
        bound_cfg = DefaultAnalyserConfig(**analyser_cfg.to_payload())
        bound_cfg.solver_id = self._require_solver_id(solver_id)
        self.analysers[str(analyser_id)] = bound_cfg

    def register_metric(self, name: str, callable_obj, schema_out: str = 'Metric@1.0') -> str:
        return self.metric_registry.register(name, callable_obj, schema_out=schema_out)

    def save(self, path: str | Path | None = None) -> Path:
        """Persist the current model state to a directory."""
        out = Path(path or self.out_dir or self.task.output.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        try:
            _clear_managed_save_paths(out)
        except OSError:
            stamp = int(time.time() * 1000)
            out = out.parent / f'{out.name}_save_{stamp}'
            out.mkdir(parents=True, exist_ok=True)
        default_features = _public_value(WorkflowFeatureFlags())
        current_features = _public_value(self.task.features) or {}
        feature_payload = {key: value for key, value in current_features.items() if value != default_features.get(key)}
        task_payload = {
            'schema_version': '1.0',
            'target': list(self.task.target) if isinstance(self.task.target, list) else self.task.target,
            'input': {
                'qasm_text': self.task.input.qasm_text,
                'device_config': 'device.json',
                'pulse_config': 'pulse.json',
                'param_bindings': dict(self.task.input.param_bindings or {}) or None,
            },
            'output': _public_value(self.task.output),
            'features': feature_payload,
            'tags': list(self.task.tags or []),
        }
        if task_payload['input']['param_bindings'] is None:
            task_payload['input'].pop('param_bindings')
        write_json(out / 'task.json', task_payload)
        write_json(
            out / 'device.json',
            {
                'schema_version': '1.0',
                'device': _public_value(self.device.device) or {},
                'noise': _public_value(self.device.noise) or {},
            },
        )
        write_json(out / 'pulse.json', {'schema_version': '1.0', 'pulse': _public_value(self.pulse) or {}})

        solvers_dir = out / 'solvers'
        analysers_dir = out / 'analysers'
        solvers_dir.mkdir(parents=True, exist_ok=True)
        analysers_dir.mkdir(parents=True, exist_ok=True)

        solver_manifest: dict[str, str] = {}
        analyser_manifest: dict[str, str] = {}
        default_solver = _public_value(WorkflowSolverConfig())
        for solver_id, solver_cfg in self.solvers.items():
            current_solver = _public_value(solver_cfg)
            solver_payload = {
                'schema_version': '1.0',
                'backend': {
                    key: value
                    for key, value in dict(current_solver.get('backend', {}) or {}).items()
                    if value != dict(default_solver.get('backend', {}) or {}).get(key)
                },
                'run': {
                    key: value
                    for key, value in dict(current_solver.get('run', {}) or {}).items()
                    if value != dict(default_solver.get('run', {}) or {}).get(key)
                },
                'frame': {
                    key: value
                    for key, value in dict(current_solver.get('frame', {}) or {}).items()
                    if value != dict(default_solver.get('frame', {}) or {}).get(key)
                },
                'study': current_solver.get('study') or None,
            }
            if not solver_payload['backend']:
                solver_payload.pop('backend')
            if not solver_payload['run']:
                solver_payload.pop('run')
            if not solver_payload['frame']:
                solver_payload.pop('frame')
            if solver_payload.get('study') is None:
                solver_payload.pop('study')
            rel = f'solvers/{solver_id}.json'
            write_json(out / rel, solver_payload)
            solver_manifest[solver_id] = rel

        for analyser_id, analyser_cfg in self.analysers.items():
            analyser_payload = {'schema_version': '1.0'}
            for key, value in (_public_value(analyser_cfg) or {}).items():
                if value not in (None, [], {}, ''):
                    analyser_payload[key] = value
            rel = f'analysers/{analyser_id}.json'
            write_json(out / rel, analyser_payload)
            analyser_manifest[analyser_id] = rel

        if self.circuit is not None:
            write_json(out / 'circuit.json', _public_value(self.circuit))
        if self.normalized_circuit is not None:
            write_json(out / 'normalized_circuit.json', _public_value(self.normalized_circuit))

        results_dir = out / 'results'
        for solver_id, bundle in self.results.solver_runs.items():
            solver_dir = results_dir / solver_id
            solver_dir.mkdir(parents=True, exist_ok=True)
            if bundle.compile_report is not None:
                write_json(solver_dir / 'compile_report.json', _public_value(bundle.compile_report))
            if bundle.pulse_ir is not None:
                write_json(solver_dir / 'pulse_ir.json', _public_value(bundle.pulse_ir))
            if bundle.executable_model is not None:
                write_json(solver_dir / 'executable_model.json', _public_value(bundle.executable_model))
            if bundle.model_spec is not None:
                write_json(solver_dir / 'model_spec.json', _public_value(bundle.model_spec))
            if bundle.runtime_metadata is not None:
                write_json(solver_dir / 'runtime_metadata.json', _public_value(bundle.runtime_metadata))
            if bundle.decoder_outputs is not None:
                write_json(solver_dir / 'decoder_outputs.json', _public_value(bundle.decoder_outputs))
            if bundle.trajectory is not None:
                write_trajectory_h5(bundle.trajectory, solver_dir / 'trajectory.h5')
            if bundle.analyses:
                analyses_dir = solver_dir / 'analyses'
                analyses_dir.mkdir(parents=True, exist_ok=True)
                for analyser_id, analysis in bundle.analyses.items():
                    analysis_payload = _public_value(analysis)
                    if isinstance(analysis_payload, dict):
                        analysis_payload = {key: value for key, value in analysis_payload.items() if value not in (None, {}, [], '')}
                        analysis_payload['analyser_id'] = analyser_id
                        analysis_payload['trajectory_id'] = analysis_payload.get('trajectory_id', solver_id)
                    write_json(analyses_dir / f'{analyser_id}.json', analysis_payload)

        write_json(
            out / 'model_manifest.json',
            {
                'schema_version': '2.0',
                'task': 'task.json',
                'device': 'device.json',
                'pulse': 'pulse.json',
                'solvers': solver_manifest,
                'analysers': analyser_manifest,
            },
        )
        return out


def create_model(
    *,
    task_config: str | Path,
    solver_config: str | Path | dict[str, str | Path] | None = None,
    device_config: str | Path | None = None,
    pulse_config: str | Path | None = None,
    analyser_config: str | Path | dict[str, str | Path] | None | object = _UNSET,
) -> Model:
    """Build a top-down editable model object from config files."""
    task = load_task_config_file(
        task_config,
        require_solver_config=(solver_config is None),
        require_device_config=(device_config is None),
        require_analyser_config=False,
    )
    solver_paths = _normalize_named_paths(
        solver_config,
        default_id_prefix='solver',
        fallback_path=task.input.solver_config_path,
    )
    if not solver_paths:
        raise ValueError('At least one solver config is required.')
    device_path = str(device_config) if device_config is not None else task.input.device_config_path
    pulse_path = str(pulse_config) if pulse_config is not None else task.input.pulse_config_path
    if not device_path:
        raise ValueError('task/device config path is required.')

    if analyser_config is _UNSET:
        analyser_paths = _normalize_named_paths(
            None,
            default_id_prefix='analyser',
            fallback_path=task.input.analyser_config_path,
        )
    elif analyser_config is None:
        analyser_paths = {}
    else:
        analyser_paths = _normalize_named_paths(
            analyser_config,
            default_id_prefix='analyser',
            fallback_path=None,
        )

    solvers = {solver_id: load_solver_config_file(path) for solver_id, path in solver_paths.items()}
    solver_ids = sorted(solvers.keys())
    analysers = {
        analyser_id: _bind_loaded_analyser(
            analyser_id=analyser_id,
            analyser_cfg=load_analyser_config_file(path),
            solver_ids=solver_ids,
        )
        for analyser_id, path in analyser_paths.items()
    }
    device = load_device_config_file(device_path)
    pulse = load_pulse_config_file(pulse_path) if pulse_path else {}
    return Model(task=task, device=device, pulse=pulse, solvers=solvers, analysers=analysers)


def load_model(path: str | Path) -> Model:
    """Load a persisted model directory created by ``Model.save``."""
    root = Path(path)
    manifest = _read_json(root / 'model_manifest.json')
    model = create_model(
        task_config=root / str(manifest.get('task', 'task.json')),
        solver_config={key: root / rel for key, rel in dict(manifest.get('solvers', {}) or {}).items()},
        device_config=root / str(manifest.get('device', 'device.json')),
        pulse_config=root / str(manifest.get('pulse', 'pulse.json')),
        analyser_config={key: root / rel for key, rel in dict(manifest.get('analysers', {}) or {}).items()},
    )
    results_dir = root / 'results'
    if results_dir.exists():
        for solver_dir in sorted([p for p in results_dir.iterdir() if p.is_dir()]):
            run_id = solver_dir.name
            bundle = model.results.ensure_solver(run_id)
            trajectory_path = solver_dir / 'trajectory.h5'
            if trajectory_path.exists():
                bundle.trajectory = load_trajectory_h5(trajectory_path)
            for attr_name, filename in (
                ('compile_report', 'compile_report.json'),
                ('pulse_ir', 'pulse_ir.json'),
                ('executable_model', 'executable_model.json'),
                ('model_spec', 'model_spec.json'),
                ('runtime_metadata', 'runtime_metadata.json'),
                ('decoder_outputs', 'decoder_outputs.json'),
            ):
                file_path = solver_dir / filename
                if file_path.exists():
                    setattr(bundle, attr_name, _read_json(file_path))
            runtime_meta = dict(bundle.runtime_metadata or {})
            bundle.solver_id = str(runtime_meta.get('solver_id', run_id))
            bundle.study_name = str(runtime_meta.get('study_name')).strip() or None if runtime_meta.get('study_name') is not None else None
            bundle.study_index = int(runtime_meta.get('study_index')) if runtime_meta.get('study_index') is not None else None
            analyses_dir = solver_dir / 'analyses'
            if analyses_dir.exists():
                for analysis_path in sorted(analyses_dir.glob('*.json')):
                    payload = _read_json(analysis_path)
                    analysis_id = str(payload.get('analyser_id')).strip() or analysis_path.stem
                    bundle.analyses[analysis_id] = AnalysisResult(
                        analyser_id=analysis_id,
                        trajectory_id=str(payload.get('trajectory_id')).strip() or None if payload.get('trajectory_id') is not None else run_id,
                        metrics=dict(payload.get('metrics', {}) or {}) or None,
                        readout=dict(payload.get('readout', {}) or {}) or None,
                        iq=dict(payload.get('iq', {}) or {}) or None,
                        report=dict(payload.get('report', {}) or {}) or None,
                        sensitivity=dict(payload.get('sensitivity', {}) or {}) or None,
                        error_budget=dict(payload.get('error_budget', {}) or {}) or None,
                    )
    return model


__all__ = ['AnalysisResult', 'Model', 'ModelResults', 'SolverRunResult', 'create_model', 'load_model']
