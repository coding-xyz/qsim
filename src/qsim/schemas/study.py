"""Study and analysis request schema for model specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
@dataclass
class AnalysisRequestSpec:
    """Trajectory data requested by analyser configuration.

    Attributes:
        trajectory: Specification of the required trajectory data (e.g., 
            which channels or times are needed).
        config: Analyser-specific configuration parameters.
    """

    trajectory: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class StudySpec:
    """Study metadata selected for this model build.

    A `StudySpec` describes a collection of related simulation runs, 
    typically representing a parameter sweep or a structured experiment.

    Attributes:
        steps: List of all steps/configurations in the study.
        primary_step: The specific configuration used for the current run.
        summary: Overall study metadata and aggregated results.
    """

    steps: list[dict[str, Any]] = field(default_factory=list)
    primary_step: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


