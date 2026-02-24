from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from qsim.analysis.passes import default_analysis_pass
from qsim.common.schemas import ModelSpec, Trace


@dataclass
class _Entry:
    name: str
    callable_obj: callable
    schema_in: str
    schema_out: str
    analysis_rev: str


class AnalysisRegistry:
    """Registry for analysis passes with version-like revision IDs."""

    def __init__(self):
        self._entries: dict[str, _Entry] = {}
        self.register("default", default_analysis_pass, "Trace@1.0", "Report@1.0")

    def register(self, name: str, callable_obj: callable, schema_in: str, schema_out: str) -> str:
        """Register a named pass and return generated analysis revision ID."""
        stamp = datetime.now(timezone.utc).isoformat()
        analysis_rev = hashlib.sha256(f"{name}:{stamp}".encode("utf-8")).hexdigest()[:12]
        self._entries[name] = _Entry(
            name=name,
            callable_obj=callable_obj,
            schema_in=schema_in,
            schema_out=schema_out,
            analysis_rev=analysis_rev,
        )
        return analysis_rev

    def get(self, name: str) -> _Entry:
        """Fetch registry entry by pass name."""
        if name not in self._entries:
            raise KeyError(f"Unknown analysis pass: {name}")
        return self._entries[name]


class AnalysisRunner:
    """Execute an analysis pass selected by pipeline name."""

    def __init__(self, registry: AnalysisRegistry):
        self.registry = registry

    def run(self, trace: Trace, model_spec: ModelSpec, pipeline: str = "default") -> dict:
        """Run analysis and attach metadata fields ``analysis_rev`` and ``analysis_name``."""
        if pipeline.startswith("custom:"):
            name = pipeline.split(":", 1)[1]
        else:
            name = pipeline
        entry = self.registry.get(name)
        out = entry.callable_obj(trace, model_spec)
        out["analysis_rev"] = entry.analysis_rev
        out["analysis_name"] = name
        return out
