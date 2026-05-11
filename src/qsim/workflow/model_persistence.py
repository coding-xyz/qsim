"""Persistence logic for workflow models."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from qsim.common.schemas import write_json
from qsim.schemas.model import ModelRun, RunArtifacts, RunIdentity, RunStatus, ModelSpec
from qsim.schemas.results import (
    AnalysisOutput,
    AnalysisScope,
    IQAnalysis,
    MetricSeries,
    MetricsOutput,
    ModelAnalysis,
    ReadoutAnalysis,
    RunProvenance,
    RunResult,
    ShotData,
)
from qsim.schemas.solver import FrameSpec, SolverSpec, TimeSpec
from qsim.schemas.study import AnalysisRequestSpec, StudySpec
from qsim.schemas.system import ModelStructureSpec, SystemCavitySpec, SystemCouplingSummarySpec, SystemQubitSpec, SystemSpec
from qsim.schemas.hamiltonian import HamiltonianSpec
from qsim.schemas.noise import NoiseSpec
from qsim.schemas.readout import ReadoutSpec
from qsim.schemas.circuit import CircuitSpec
from qsim.workflow.contracts import (
    PulseAcquisitionConfig,
    PulseChannelConfig,
    PulseTimingConfig,
    TaskInputConfig,
    WorkflowFeatureFlags,
    WorkflowFrameOptions,
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowPulseConfig,
    WorkflowRunOptions,
    WorkflowSolverConfig,
    WorkflowTask,
)
from qsim.workflow.output import write_trajectory_h5
from qsim.pulse.visualize import load_trajectory_h5

from qsim.workflow.model_utils import (
    public_value,
    read_json,
    clear_managed_save_paths,
    compact_payload,
)


def _restore_workflow_pulse_config(payload: dict[str, Any] | None) -> WorkflowPulseConfig:
    raw = dict(payload or {})
    acquisition_raw = dict(raw.get("acquisition", {}) or {})
    timing_raw = dict(raw.get("timing", {}) or {})
    return WorkflowPulseConfig(
        acquisition=PulseAcquisitionConfig(
            shots=int(acquisition_raw.get("shots", 1000) or 1000),
            averaging=int(acquisition_raw.get("averaging", 1) or 1),
            trigger_source=str(acquisition_raw.get("trigger_source", "internal") or "internal"),
            extras={k: v for k, v in acquisition_raw.items() if k not in {"shots", "averaging", "trigger_source"}},
        ),
        timing=PulseTimingConfig(
            clock_rate_Hz=float(timing_raw.get("clock_rate_Hz", 1e9) or 1e9),
            sample_rate_Hz=float(timing_raw.get("sample_rate_Hz", 1e9) or 1e9),
            precision_s=float(timing_raw.get("precision_s", 1e-12) or 1e-12),
            extras={k: v for k, v in timing_raw.items() if k not in {"clock_rate_Hz", "sample_rate_Hz", "precision_s"}},
        ),
        channels={
            str(channel_id): (
                channel_cfg if isinstance(channel_cfg, PulseChannelConfig)
                else PulseChannelConfig(
                    **{
                        k: v
                        for k, v in dict(channel_cfg or {}).items()
                        if k in {"type", "amplitude", "duration_ns", "phase", "frequency_Hz"}
                    },
                    extras={
                        k: v
                        for k, v in dict(channel_cfg or {}).items()
                        if k not in {"type", "amplitude", "duration_ns", "phase", "frequency_Hz"}
                    },
                )
            )
            for channel_id, channel_cfg in dict(raw.get("channels", {}) or {}).items()
        },
        extras=dict(raw.get("extras", {}) or {}) or None,
    )


def _restore_workflow_task(payload: dict[str, Any] | None) -> WorkflowTask:
    raw = dict(payload or {})
    input_raw = dict(raw.get("input", {}) or {})
    run_raw = dict(raw.get("run", {}) or {})
    features_raw = dict(raw.get("features", {}) or {})
    output_raw = dict(raw.get("output", {}) or {})
    return WorkflowTask(
        input=WorkflowInput(**input_raw),
        run=WorkflowRunOptions(**run_raw),
        features=WorkflowFeatureFlags(**features_raw),
        output=WorkflowOutputOptions(**output_raw),
        template=raw.get("template"),
        targets=list(raw.get("targets", []) or []) or None,
        tags=list(raw.get("tags", []) or []),
    )


def _restore_model_spec(payload: dict[str, Any] | None) -> ModelSpec | None:
    if not payload:
        return None
    raw = dict(payload)
    return ModelSpec(
        circuit=CircuitSpec.from_dict(raw.get("circuit")) if raw.get("circuit") else None,
        solver=SolverSpec(**dict(raw.get("solver", {}) or {})),
        time=TimeSpec(**dict(raw.get("time", {}) or {})),
        frame=FrameSpec(**dict(raw.get("frame", {}) or {})),
        system=SystemSpec(
            model_type=str(dict(raw.get("system", {}) or {}).get("model_type", "qubit_network")),
            simulation_level=str(dict(raw.get("system", {}) or {}).get("simulation_level", "qubit")),
            dimension=int(dict(raw.get("system", {}) or {}).get("dimension", 2) or 2),
            components=list(dict(raw.get("system", {}) or {}).get("components", []) or []),
            connections=list(dict(raw.get("system", {}) or {}).get("connections", []) or []),
            structure=ModelStructureSpec.from_dict(dict(raw.get("system", {}) or {}).get("structure")),
            assumptions=dict(dict(raw.get("system", {}) or {}).get("assumptions", {}) or {}),
            qubits=SystemQubitSpec(**dict(dict(raw.get("system", {}) or {}).get("qubits", {}) or {})),
            cavity=SystemCavitySpec(**dict(dict(raw.get("system", {}) or {}).get("cavity", {}) or {})),
            couplings=SystemCouplingSummarySpec(**dict(dict(raw.get("system", {}) or {}).get("couplings", {}) or {})),
        ),
        hamiltonian=HamiltonianSpec(**dict(raw.get("hamiltonian", {}) or {})),
        noise=NoiseSpec(**dict(raw.get("noise", {}) or {})),
        readout=ReadoutSpec(**dict(raw.get("readout", {}) or {})) if raw.get("readout") else None,
        analysis_request=AnalysisRequestSpec(**dict(raw.get("analysis_request", {}) or {})) if raw.get("analysis_request") else None,
        study=StudySpec(**dict(raw.get("study", {}) or {})) if raw.get("study") else None,
        metadata=dict(raw.get("metadata", {}) or {}),
    )


def _restore_metrics_output(payload: dict[str, Any] | None) -> MetricsOutput | None:
    if not payload:
        return None
    items: dict[str, MetricSeries] = {}
    for name, series in dict(payload.get("metric_items", {}) or {}).items():
        items[str(name)] = MetricSeries(
            times=list(dict(series or {}).get("times", []) or []),
            values=list(dict(series or {}).get("values", []) or []),
        )
    return MetricsOutput(metric_items=items)


def _restore_readout_analysis(payload: dict[str, Any] | None) -> ReadoutAnalysis | None:
    if not payload:
        return None
    raw = dict(payload)
    shots = [
        ShotData(
            timestamp=float(dict(item or {}).get("timestamp", 0.0) or 0.0),
            value=dict(item or {}).get("value"),
            metadata=dict(dict(item or {}).get("metadata", {}) or {}),
        )
        for item in list(raw.get("shots", []) or [])
    ]
    return ReadoutAnalysis(
        signals=dict(raw.get("signals", {}) or {}),
        demodulation=dict(raw.get("demodulation", {}) or {}),
        shots=shots,
    )


def _restore_iq_analysis(payload: dict[str, Any] | None) -> IQAnalysis | None:
    if not payload:
        return None
    raw = dict(payload)
    return IQAnalysis(
        centroids=dict(raw.get("centroids", {}) or {}),
        confusion_matrix=dict(raw.get("confusion_matrix", {}) or {}),
        assignment_fidelity=float(raw.get("assignment_fidelity", 0.0) or 0.0),
        noise_sigma=float(raw.get("noise_sigma", 0.0) or 0.0),
        snr=float(raw.get("snr", 0.0) or 0.0),
    )


def _restore_analysis_output(payload: dict[str, Any] | None) -> AnalysisOutput:
    raw = dict(payload or {})
    return AnalysisOutput(
        metrics=_restore_metrics_output(dict(raw.get("metrics", {}) or {})) if raw.get("metrics") is not None else None,
        readout=_restore_readout_analysis(dict(raw.get("readout", {}) or {})) if raw.get("readout") is not None else None,
        iq=_restore_iq_analysis(dict(raw.get("iq", {}) or {})) if raw.get("iq") is not None else None,
    )

def save_model(model: Any, path: str | Path | None = None) -> Path:
    """Persist the current model state to a directory following hierarchical structure."""
    out = Path(path or model.out_dir or model.task.output.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        clear_managed_save_paths(out)
    except OSError:
        stamp = int(time.time() * 1000)
        out = out.parent / f'{out.name}_save_{stamp}'
        out.mkdir(parents=True, exist_ok=True)

    # 1. Config Layer
    config_dir = out / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Task
    task_payload = {
        'schema_version': '1.0',
        'target': list(model.task.target) if isinstance(model.task.target, list) else model.task.target,
        'input': {
            'qasm_text': model.task.input.qasm_text,
            'device_config': 'device.json',
            'pulse_config': 'pulse.json',
            'param_bindings': dict(model.task.input.param_bindings or {}) or None,
        },
        'output': public_value(model.task.output),
        'features': compact_payload(
            public_value(model.task.features),
            public_value(WorkflowFeatureFlags()),
        ),
        'tags': list(model.task.tags or []),
    }
    write_json(config_dir / 'task.json', task_payload)
    
    # Device & Pulse
    write_json(config_dir / 'device.json', {
        'schema_version': '1.0',
        'device': public_value(model.device.device) or {},
        'noise': public_value(model.device.noise) or {},
    })
    write_json(config_dir / 'pulse.json', {
        'schema_version': '1.0', 
        'pulse': public_value(model.pulse) or {}
    })

    # Solvers & Analysers
    solvers_dir = config_dir / 'solvers'
    analysers_dir = config_dir / 'analysers'
    solvers_dir.mkdir(parents=True, exist_ok=True)
    analysers_dir.mkdir(parents=True, exist_ok=True)

    solver_manifest: dict[str, str] = {}
    for sid, scfg in model.solvers.items():
        rel = f'config/solvers/{sid}.json'
        solver_payload = compact_payload(
            public_value(scfg),
            public_value(WorkflowSolverConfig()),
        )
        if "run" in solver_payload and isinstance(solver_payload["run"], dict):
            solver_payload["run"] = compact_payload(
                dict(solver_payload["run"]),
                public_value(WorkflowSolverConfig().run),
            )
        if "backend" in solver_payload and isinstance(solver_payload["backend"], dict):
            solver_payload["backend"] = compact_payload(
                dict(solver_payload["backend"]),
                public_value(WorkflowSolverConfig().backend),
            )
        if "frame" in solver_payload and isinstance(solver_payload["frame"], dict):
            solver_payload["frame"] = compact_payload(
                dict(solver_payload["frame"]),
                public_value(WorkflowSolverConfig().frame),
            )
        write_json(solvers_dir / f'{sid}.json', solver_payload)
        solver_manifest[sid] = rel

    analyser_manifest: dict[str, str] = {}
    for aid, acfg in model.analysers.items():
        rel = f'config/analysers/{aid}.json'
        analyser_payload = compact_payload(
            public_value(acfg),
            public_value(DefaultAnalyserConfig()),
        )
        write_json(analysers_dir / f'{aid}.json', analyser_payload)
        analyser_manifest[aid] = rel

    # 2. Runs Layer
    runs_dir = out / 'runs'
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run_id, run_obj in model.runs.items():
        run_root = runs_dir / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        
        # Identity & Task
        write_json(run_root / 'identity.json', public_value(run_obj.identity))
        write_json(run_root / 'runtime_task.json', public_value(run_obj.runtime_task))
        
        # Artifacts
        art_dir = run_root / 'artifacts'
        art_dir.mkdir(parents=True, exist_ok=True)
        arts = run_obj.artifacts
        if arts.compile_report: write_json(art_dir / 'compile_report.json', public_value(arts.compile_report))
        if arts.pulse_ir: write_json(art_dir / 'pulse_ir.json', public_value(arts.pulse_ir))
        if arts.executable_model: write_json(art_dir / 'executable_model.json', public_value(arts.executable_model))
        if arts.model_spec: write_json(art_dir / 'model_spec.json', public_value(arts.model_spec))
        if arts.decoder_outputs: write_json(art_dir / 'decoder_outputs.json', public_value(arts.decoder_outputs))
        write_json(art_dir / 'timings.json', public_value(arts.timings))

        # Result
        res_dir = run_root / 'result'
        res_dir.mkdir(parents=True, exist_ok=True)
        if run_obj.result:
            write_json(res_dir / 'provenance.json', public_value(run_obj.result.provenance))
            write_json(res_dir / 'runtime_metadata.json', public_value(run_obj.result.runtime_metadata))
            if run_obj.result.trajectory:
                write_trajectory_h5(run_obj.result.trajectory, res_dir / 'trajectory.h5')

    # 3. Analyses Layer
    analyses_dir = out / 'analyses'
    analyses_dir.mkdir(parents=True, exist_ok=True)
    for aid, analysis in model.analyses.items():
        write_json(analyses_dir / f'{aid}.json', public_value(analysis))

    # 4. Manifest
    write_json(out / 'model_manifest.json', {
        'schema_version': '3.0',
        'config': {
            'task': 'config/task.json',
            'device': 'config/device.json',
            'pulse': 'config/pulse.json',
            'solvers': solver_manifest,
            'analysers': analyser_manifest,
        },
        'state': {
            'last_out_dir': model.state.last_out_dir,
            'last_run_id': model.state.last_run_id,
        }
    })
    return out

def load_model(model_class: Any, create_model_func: Any, path: str | Path) -> Any:
    """Load a persisted model directory following hierarchical structure."""
    root = Path(path)
    manifest = read_json(root / 'model_manifest.json')
    cfg_manifest = manifest.get('config', {})
    
    # 1. Reconstruct Model using create_model_func (loads config layer)
    # Use .resolve() to ensure absolute paths, avoiding issues with relative path resolution
    model = create_model_func(
        task_config=(root / cfg_manifest.get('task', 'config/task.json')).resolve(),
        solver_config={sid: (root / rel).resolve() for sid, rel in dict(cfg_manifest.get('solvers', {}) or {}).items()},
        device_config=(root / cfg_manifest.get('device', 'config/device.json')).resolve(),
        pulse_config=(root / cfg_manifest.get('pulse', 'config/pulse.json')).resolve(),
        analyser_config={aid: (root / rel).resolve() for aid, rel in dict(cfg_manifest.get('analysers', {}) or {}).items()},
    )
    
    # 2. Restore State
    state_manifest = manifest.get('state', {})
    model.state.last_out_dir = state_manifest.get('last_out_dir')
    model.state.last_run_id = state_manifest.get('last_run_id')
    
    # 3. Restore Runs
    runs_dir = root / 'runs'
    if runs_dir.exists():
        for run_root in sorted([p for p in runs_dir.iterdir() if p.is_dir()]):
            run_id = run_root.name
            
            # Identity & Task
            ident_payload = read_json(run_root / 'identity.json')
            identity = RunIdentity(**ident_payload)
            
            runtime_task_payload = read_json(run_root / 'runtime_task.json')
            runtime_task = _restore_workflow_task(runtime_task_payload)
            
            # Artifacts
            art_dir = run_root / 'artifacts'
            artifacts = RunArtifacts()
            if art_dir.exists():
                if (art_dir / 'compile_report.json').exists():
                    artifacts.compile_report = read_json(art_dir / 'compile_report.json')
                if (art_dir / 'pulse_ir.json').exists():
                    artifacts.pulse_ir = read_json(art_dir / 'pulse_ir.json')
                if (art_dir / 'executable_model.json').exists():
                    artifacts.executable_model = read_json(art_dir / 'executable_model.json')
                if (art_dir / 'model_spec.json').exists():
                    artifacts.model_spec = _restore_model_spec(read_json(art_dir / 'model_spec.json'))
                if (art_dir / 'decoder_outputs.json').exists():
                    artifacts.decoder_outputs = read_json(art_dir / 'decoder_outputs.json')
                if (art_dir / 'timings.json').exists():
                    artifacts.timings = read_json(art_dir / 'timings.json')
            
            # Result
            res_dir = run_root / 'result'
            result = None
            if res_dir.exists():
                traj_path = res_dir / 'trajectory.h5'
                trajectory = load_trajectory_h5(traj_path) if traj_path.exists() else None
                if trajectory:
                    provenance_payload = read_json(res_dir / 'provenance.json')
                    provenance = RunProvenance(**provenance_payload)
                    runtime_meta = read_json(res_dir / 'runtime_metadata.json') if (res_dir / 'runtime_metadata.json').exists() else {}
                    result = RunResult(
                        result_id=run_id,
                        trajectory=trajectory,
                        provenance=provenance,
                        runtime_metadata=runtime_meta,
                    )
            
            model.runs[run_id] = ModelRun(
                identity=identity,
                runtime_task=runtime_task,
                artifacts=artifacts,
                result=result,
                status=RunStatus.COMPLETED if result is not None else RunStatus.PENDING,
            )

    # 4. Restore Analyses
    analyses_root = root / 'analyses'
    if analyses_root.exists():
        for a_path in analyses_root.glob('*.json'):
            payload = read_json(a_path)
            # Handle AnalysisScope Enum conversion from string
            scope_val = payload.get('scope', 'single_run')
            try:
                scope = AnalysisScope(scope_val)
            except ValueError:
                scope = AnalysisScope.SINGLE_RUN
                
            # Restore typed AnalysisOutput
            analysis_output = _restore_analysis_output(dict(payload.get('output', {}) or {}))

            model.analyses[a_path.stem] = ModelAnalysis(
                analysis_id=a_path.stem,
                analyser_id=str(payload.get('analyser_id', a_path.stem)),
                input_run_ids=list(payload.get('input_run_ids', [])),
                scope=scope,
                output=analysis_output,
                schema_version=str(payload.get('schema_version', '1.0'))
            )
    
    return model
