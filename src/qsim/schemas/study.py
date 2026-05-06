"""Study and analysis request schema for model specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
@dataclass
class AnalysisRequestSpec:
    """Trajectory data requested by analyser configuration."""

    trajectory: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class StudySpec:
    """Study metadata selected for this model build."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    primary_step: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


