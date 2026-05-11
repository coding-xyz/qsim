"""Model-first workflow API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qsim.analysis import MetricRegistry, build_default_metric_registry
from qsim.schemas.model import ModelRun, ModelSpec, RunArtifacts, RunIdentity, ModelManifest
from qsim.schemas.results import ModelAnalysis, RunResult, Trajectory
from qsim.workflow.contracts import (
    DefaultAnalyserConfig,
    PulseAcquisitionConfig,
    PulseChannelConfig,
    PulseTimingConfig,
    WorkflowDeviceConfig,
    WorkflowPulseConfig,
    WorkflowSolverConfig,
    WorkflowTask,
    WorkflowTaskConfig,
)
from qsim.workflow.task_io import (
    load_analyser_config_file,
    load_device_config_file,
    load_pulse_config_file,
    load_solver_config_file,
    load_task_config_file,
)

from qsim.workflow.model_utils import (
    _UNSET,
    bind_loaded_analyser,
    normalize_named_paths,
)
from qsim.workflow.model_execution import (
    find_run_id,
    run,
    run_all,
    run_analysis,
    run_solver,
    run_study,
)
from qsim.workflow.model_persistence import load_model as _load_model_impl, save_model as _save_model_impl

@dataclass(slots=True)
class ModelConfig:
    """Aggregated configuration for the quantum simulation workflow."""
    task: WorkflowTaskConfig
    device: WorkflowDeviceConfig
    solvers: dict[str, WorkflowSolverConfig]
    pulse: WorkflowPulseConfig = field(default_factory=WorkflowPulseConfig)
    analysers: dict[str, DefaultAnalyserConfig] = field(default_factory=dict)

@dataclass(slots=True)
class ModelState:
    """Lightweight session state for the workflow."""
    last_out_dir: str | None = None
    last_run_id: str | None = None

@dataclass(slots=True)
class ModelRegistry:
    """Central registry for metrics and other shared resources."""
    metrics: MetricRegistry = field(default_factory=build_default_metric_registry)

@dataclass(slots=True)
class Model:
    """Top-down editable model object."""

    config: ModelConfig
    state: ModelState = field(default_factory=ModelState)
    registry: ModelRegistry = field(default_factory=ModelRegistry)
    manifest: ModelManifest = field(default_factory=ModelManifest)
    runs: dict[str, ModelRun] = field(default_factory=dict)
    analyses: dict[str, ModelAnalysis] = field(default_factory=dict)

    # --- Backward Compatibility Properties ---
    @property
    def task(self) -> WorkflowTaskConfig: return self.config.task
    @property
    def device(self) -> WorkflowDeviceConfig: return self.config.device
    @property
    def solvers(self) -> dict[str, WorkflowSolverConfig]: return self.config.solvers
    @property
    def pulse(self) -> WorkflowPulseConfig: return self.config.pulse
    @property
    def analysers(self) -> dict[str, DefaultAnalyserConfig]: return self.config.analysers
    @property
    def metric_registry(self) -> MetricRegistry: return self.registry.metrics
    @property
    def out_dir(self) -> str | None: return self.state.last_out_dir
    @out_dir.setter
    def out_dir(self, value: str | None): self.state.last_out_dir = value

    def __repr__(self) -> str:
        run_ids = sorted(self.runs.keys())
        analysis_ids = sorted(self.analyses.keys())
        return (
            'Model('
            f'solvers={sorted(self.solvers.keys())}, '
            f'analysers={[(analyser_id, cfg.solver_id) for analyser_id, cfg in sorted(self.analysers.items())]}, '
            f'runs={run_ids}, '
            f'analyses={analysis_ids}'
            ')'
        )

    def _clear_solver_results(self, solver_id: str) -> None:
        for run_id in list(self.runs.keys()):
            run_obj = self.runs[run_id]
            if run_obj.identity.solver_id == solver_id:
                self.runs.pop(run_id, None)

    def get_trajectory(self, solver_id: str | None = None, *, study_name: str | None = None) -> Trajectory | None:
        from qsim.workflow.model_utils import require_solver_id
        selected_solver_id = require_solver_id(self, solver_id)
        if study_name is None:
            run_id = find_run_id(self, solver_id=selected_solver_id, study_name_val=None)
            if run_id:
                return self.runs[run_id].result.trajectory
            return None
        run_id = find_run_id(self, solver_id=selected_solver_id, study_name_val=study_name)
        if run_id is None:
            return None
        return self.runs[run_id].result.trajectory

    def get_analysis(self, *, analyser_id: str | None = None, study_name: str | None = None) -> ModelAnalysis | None:
        from qsim.workflow.model_utils import require_analyser_id, safe_study_token
        selected_analyser_id = require_analyser_id(self, analyser_id)
        if study_name is None:
            return self.analyses.get(selected_analyser_id)
        token = safe_study_token(study_name)
        return self.analyses.get(f'{selected_analyser_id}__{token}')

    def find_analysis_for_run(self, run_id: str) -> ModelAnalysis | None:
        """Find the first analysis that depends on the given run ID."""
        return next((a for a in self.analyses.values() if run_id in a.input_run_ids), None)

    def add_solver(self, solver_id: str, solver_cfg: WorkflowSolverConfig) -> None:
        self.solvers[str(solver_id)] = solver_cfg

    def add_analyser(self, analyser_id: str, solver_id: str, analyser_cfg: DefaultAnalyserConfig) -> None:
        from qsim.workflow.model_utils import require_solver_id
        bound_cfg = DefaultAnalyserConfig(**analyser_cfg.to_payload())
        bound_cfg.solver_id = require_solver_id(self, solver_id)
        self.analysers[str(analyser_id)] = bound_cfg

    def register_metric(self, name: str, callable_obj, schema_out: str = 'Metric@1.0') -> str:
        return self.metric_registry.register(name, callable_obj, schema_out=schema_out)

    def save(self, path: str | Path | None = None) -> Path:
        """Persist the current model state to a directory."""
        return _save_model_impl(self, path)

    def run_study(self, *, solver_id: str | None = None, study_name: str | None = None, study_index: int | None = None) -> str:
        """Compile and solve one specific study step into ``model.runs``."""
        return run_study(self, solver_id=solver_id, study_name_val=study_name, study_index=study_index)

    def run_solver(self, solver_id: str | None = None) -> None:
        """Compile and solve one configured solver, running every study step by default."""
        run_solver(self, solver_id=solver_id)

    def run_analysis(self, *, analyser_id: str | None = None, study_name: str | None = None) -> None:
        """Run one analyser against every matching study trajectory into ``model.analyses``."""
        run_analysis(self, analyser_id=analyser_id, study_name_val=study_name)

    def run_all(self) -> None:
        """Run every configured solver and then every configured analyser."""
        run_all(self)

    def run(self) -> None:
        """Run all configured solvers and analysers."""
        run(self)


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
    solver_paths = normalize_named_paths(
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
        analyser_paths = normalize_named_paths(
            None,
            default_id_prefix='analyser',
            fallback_path=task.input.analyser_config_path,
        )
    elif analyser_config is None:
        analyser_paths = {}
    else:
        analyser_paths = normalize_named_paths(
            analyser_config,
            default_id_prefix='analyser',
            fallback_path=None,
        )

    solvers = {solver_id: load_solver_config_file(path) for solver_id, path in solver_paths.items()}
    solver_ids = sorted(solvers.keys())
    analysers = {
        analyser_id: bind_loaded_analyser(
            analyser_id=analyser_id,
            analyser_cfg=load_analyser_config_file(path),
            solver_ids=solver_ids,
        )
        for analyser_id, path in analyser_paths.items()
    }
    device = load_device_config_file(device_path)
    pulse_payload = load_pulse_config_file(pulse_path) if pulse_path else {}
    if isinstance(pulse_payload, dict):
        def _split_payload(raw: dict[str, Any], known: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
            known_items = {k: v for k, v in raw.items() if k in known}
            extras = {k: v for k, v in raw.items() if k not in known}
            return known_items, extras

        known_fields = {'acquisition', 'timing', 'channels', 'extras'}
        known_args = {k: v for k, v in pulse_payload.items() if k in known_fields}
        extra_args = {k: v for k, v in pulse_payload.items() if k not in known_fields}
        extras = known_args.get('extras') or {}
        if isinstance(extras, dict):
            extras.update(extra_args)
        else:
            extras = extra_args

        acquisition_known, acquisition_extras = _split_payload(
            dict(known_args.get('acquisition', {}) or {}),
            {'shots', 'averaging', 'trigger_source', 'extras'},
        )
        timing_known, timing_extras = _split_payload(
            dict(known_args.get('timing', {}) or {}),
            {'clock_rate_Hz', 'sample_rate_Hz', 'precision_s', 'extras'},
        )
        acquisition_known_extras = dict(acquisition_known.pop('extras', {}) or {})
        timing_known_extras = dict(timing_known.pop('extras', {}) or {})

        pulse = WorkflowPulseConfig(
            acquisition=PulseAcquisitionConfig(
                **acquisition_known,
                extras={
                    **acquisition_known_extras,
                    **acquisition_extras,
                },
            ),
            timing=PulseTimingConfig(
                **timing_known,
                extras={
                    **timing_known_extras,
                    **timing_extras,
                },
            ),
            channels={
                str(channel_id): (
                    channel_cfg if isinstance(channel_cfg, PulseChannelConfig)
                    else PulseChannelConfig(
                        **{
                            k: v
                            for k, v in dict(channel_cfg or {}).items()
                            if k in {'type', 'amplitude', 'duration_ns', 'phase', 'frequency_Hz'}
                        },
                        extras={
                            k: v
                            for k, v in dict(channel_cfg or {}).items()
                            if k not in {'type', 'amplitude', 'duration_ns', 'phase', 'frequency_Hz'}
                        },
                    )
                )
                for channel_id, channel_cfg in dict(known_args.get('channels', {}) or {}).items()
            },
            extras=extras or None,
        )
    else:
        pulse = pulse_payload
    config = ModelConfig(
        task=task,
        device=device,
        solvers=solvers,
        pulse=pulse,
        analysers=analysers,
    )
    return Model(config=config)


def load_model(path: str | Path) -> Model:
    """Load a persisted model directory created by ``Model.save``."""
    return _load_model_impl(Model, create_model, path)


__all__ = ['Model', 'create_model', 'load_model']
