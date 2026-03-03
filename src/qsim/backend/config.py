"""Backend configuration loading, validation, and persistence helpers."""

from __future__ import annotations

from pathlib import Path
import json

import yaml

from qsim.common.schemas import BackendConfig


_ALLOWED_LEVEL = {"qubit", "nlevel", "cqed", "io"}
_ALLOWED_NOISE = {"deterministic", "lindblad", "sde", "tls", "hybrid"}
_ALLOWED_SOLVER = {"se", "me", "mcwf", "io"}


def load_backend_config(yaml_path: str | Path) -> BackendConfig:
    """Load and validate backend config from YAML file."""
    raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8")) or {}
    cfg = BackendConfig(
        level=str(raw.get("level", "qubit")),
        noise=str(raw.get("noise", "deterministic")),
        solver=str(raw.get("solver", "se")),
        analysis_pipeline=str(raw.get("analysis_pipeline", "default")),
        truncation=dict(raw.get("truncation", {})),
        sweep=list(raw.get("sweep", [])),
        seed=int(raw.get("seed", 1234)),
    )
    validate_backend_config(cfg)
    return cfg


def validate_backend_config(cfg: BackendConfig) -> None:
    """Validate ``BackendConfig`` fields and value domains."""
    if cfg.level not in _ALLOWED_LEVEL:
        raise ValueError(f"Invalid level: {cfg.level}")
    if cfg.noise not in _ALLOWED_NOISE:
        raise ValueError(f"Invalid noise: {cfg.noise}")
    if cfg.solver not in _ALLOWED_SOLVER:
        raise ValueError(f"Invalid solver: {cfg.solver}")
    if not isinstance(cfg.truncation, dict):
        raise ValueError("truncation must be a mapping")


def dump_backend_config(cfg: BackendConfig, out_path: str | Path) -> Path:
    """Write ``BackendConfig`` as pretty JSON and return output path."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
