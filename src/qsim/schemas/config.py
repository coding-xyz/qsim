"""Legacy backend execution config schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION


@dataclass
class BackendConfig:
    """Backend execution configuration loaded from YAML."""

    schema_version: str = SCHEMA_VERSION
    level: str = "qubit"
    noise: str = "deterministic"
    solver: str = "se"
    analysis_pipeline: str = "default"
    truncation: dict[str, int] = field(default_factory=dict)
    sweep: list[dict[str, Any]] = field(default_factory=list)
    seed: int = 1234

    @property
    def analysis(self) -> str:
        """Compatibility alias for ``analysis_pipeline``."""
        return str(self.analysis_pipeline)

    @analysis.setter
    def analysis(self, value: str) -> None:
        """Update ``analysis_pipeline`` through the legacy alias."""
        self.analysis_pipeline = str(value)


