"""Analysis pass and metric registry orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Callable

from qsim.analysis.passes import default_analysis_pass
from qsim.common.schemas import ModelSpec, Trajectory


def _build_rev(name: str, *, kind: str) -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    return hashlib.sha256(f"{kind}:{name}:{stamp}".encode("utf-8")).hexdigest()[:12]


@dataclass
class _Entry:
    name: str
    callable_obj: callable
    schema_in: str
    schema_out: str
    analysis_rev: str


@dataclass
class _MetricEntry:
    name: str
    callable_obj: Callable[[Trajectory, ModelSpec, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]
    schema_out: str
    metric_rev: str


class AnalysisRegistry:
    """Registry for named analysis passes with revision IDs."""

    def __init__(self):
        self._entries: dict[str, _Entry] = {}
        self.register("default", default_analysis_pass, "Trajectory@1.0", "Report@1.0")

    def register(self, name: str, callable_obj: callable, schema_in: str, schema_out: str) -> str:
        """Register a named pass and return its generated revision ID."""
        analysis_rev = _build_rev(name, kind="analysis")
        self._entries[name] = _Entry(
            name=name,
            callable_obj=callable_obj,
            schema_in=schema_in,
            schema_out=schema_out,
            analysis_rev=analysis_rev,
        )
        return analysis_rev

    def get(self, name: str) -> _Entry:
        """Fetch a registry entry by pass name."""
        if name not in self._entries:
            raise KeyError(f"Unknown analysis pass: {name}")
        return self._entries[name]


class MetricRegistry:
    """Registry for named analyser metrics."""

    def __init__(self):
        self._entries: dict[str, _MetricEntry] = {}

    def register(
        self,
        name: str,
        callable_obj: Callable[[Trajectory, ModelSpec, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]],
        schema_out: str = "Metric@1.0",
    ) -> str:
        metric_name = str(name).strip().lower()
        if not metric_name:
            raise ValueError("Metric name must be non-empty.")
        metric_rev = _build_rev(metric_name, kind="metric")
        self._entries[metric_name] = _MetricEntry(
            name=metric_name,
            callable_obj=callable_obj,
            schema_out=schema_out,
            metric_rev=metric_rev,
        )
        return metric_rev

    def get(self, name: str) -> _MetricEntry:
        metric_name = str(name).strip().lower()
        if metric_name not in self._entries:
            raise KeyError(f"Unknown metric: {name}")
        return self._entries[metric_name]

    def has(self, name: str) -> bool:
        return str(name).strip().lower() in self._entries

    def names(self) -> list[str]:
        return sorted(self._entries.keys())


class AnalysisRunner:
    """Execute analysis passes selected by pipeline name."""

    def __init__(self, registry: AnalysisRegistry):
        self.registry = registry

    def run(self, Trajectory: Trajectory, model_spec: ModelSpec, pipeline: str = "default") -> dict:
        """Run an analysis pass and attach pass metadata."""
        if pipeline.startswith("custom:"):
            name = pipeline.split(":", 1)[1]
        else:
            name = pipeline
        entry = self.registry.get(name)
        out = entry.callable_obj(Trajectory, model_spec)
        out["analysis_rev"] = entry.analysis_rev
        out["analysis_name"] = name
        return out
