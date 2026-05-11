"""Utilities for workflow models."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
import time
import shutil
from pathlib import Path
from typing import Any

from qsim.schemas.utils import json_restore
from qsim.workflow.contracts import DefaultAnalyserConfig, WorkflowSolverConfig

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

def public_value(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): public_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    return value

def read_json(path: Path) -> dict[str, Any]:
    return dict(json_restore(json.loads(path.read_text(encoding='utf-8'))))

def is_small_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))

def summarize_runtime_payload(value: Any) -> dict[str, Any]:
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

def compact_runtime_details(details: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(details or {})
    compact: dict[str, Any] = {}
    bulky_keys = {'quantum_state_trajectory', 'readout_observables', 'measurement_records', 'jump_events'}
    for key, value in raw.items():
        if key in bulky_keys:
            compact[key] = summarize_runtime_payload(value)
            continue
        if is_small_scalar(value):
            compact[key] = value
            continue
        if isinstance(value, dict):
            if all(is_small_scalar(child) for child in value.values()) and len(value) <= 24:
                compact[key] = dict(value)
            else:
                compact[key] = summarize_runtime_payload(value)
            continue
        if isinstance(value, list):
            if len(value) <= 24 and all(is_small_scalar(item) for item in value):
                compact[key] = list(value)
            else:
                compact[key] = summarize_runtime_payload(value)
            continue
        compact[key] = summarize_runtime_payload(value)
    return compact

def clear_managed_save_paths(out: Path) -> None:
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

def normalize_named_paths(
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

def bind_loaded_analyser(
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

def effective_analyser_payload(
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

def safe_study_token(value: str) -> str:
    import re
    token = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
    return token.strip("_") or "study"

def study_name(study: dict[str, Any], study_index: int | None) -> str | None:
    if not study:
        return None
    raw = str(study.get('name', '') or '').strip()
    if raw:
        return raw
    if study_index is None:
        return None
    return f'study_{study_index}'

def require_solver_id(model: Any, solver_id: str | None) -> str:
    if solver_id:
        if solver_id not in model.solvers:
            raise KeyError(f'Unknown solver_id: {solver_id}')
        return solver_id
    if len(model.solvers) == 1:
        return next(iter(model.solvers))
    raise ValueError('solver_id is required when the model has multiple solvers.')

def require_analyser_id(model: Any, analyser_id: str | None) -> str:
    if analyser_id:
        if analyser_id not in model.analysers:
            raise KeyError(f'Unknown analyser_id: {analyser_id}')
        return analyser_id
    if len(model.analysers) == 1:
        return next(iter(model.analysers))
    raise ValueError('analyser_id is required when the model has multiple analysers.')

def compact_payload(current: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    """Remove keys from current that match values in default."""
    return {
        k: v for k, v in current.items()
        if k not in default or v != default[k]
    }

def format_study_id(base_id: str, study: dict[str, Any], study_index: int | None, total_studies: int) -> str:
    """Standardize ID generation for studies."""
    if total_studies <= 1:
        return base_id
    name = study_name(study, study_index)
    if not name:
        return base_id
    return f'{base_id}__{safe_study_token(name)}'
