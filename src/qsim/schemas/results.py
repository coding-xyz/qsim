"""Trajectory, analysis result, and run manifest schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION, sha256_file, utc_now_iso


@dataclass
class Trajectory:
    """Normalized simulation output trajectory."""

    schema_version: str = SCHEMA_VERSION
    engine: str = "mock"
    times: list[float] = field(default_factory=list)
    wave_function: dict[str, Any] | None = None
    density_matrix: dict[str, Any] | None = None
    classical: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a compact payload containing only populated trajectory fields."""
        payload: dict[str, Any] = {
            "schema_version": str(self.schema_version),
            "engine": str(self.engine),
            "times": list(self.times or []),
        }
        if self.wave_function:
            payload["wave_function"] = dict(self.wave_function)
        if self.density_matrix:
            payload["density_matrix"] = dict(self.density_matrix)
        if self.classical:
            payload["classical"] = dict(self.classical)
        if self.measurements:
            payload["measurements"] = dict(self.measurements)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def __getattribute__(self, name: str):
        if name == "__annotations__":
            cls_annotations = type(self).__dict__.get("__annotations__", {})
            payload_keys = set(object.__getattribute__(self, "to_payload")().keys())
            return {key: value for key, value in cls_annotations.items() if key in payload_keys}
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        return f"Trajectory({self.to_payload()!r})"


@dataclass
class Observables:
    """Computed analysis observables from a trajectory."""

    schema_version: str = SCHEMA_VERSION
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Report:
    """High-level analysis report and error budget summary."""

    schema_version: str = SCHEMA_VERSION
    summary: dict[str, Any] = field(default_factory=dict)
    error_budget: dict[str, float] = field(default_factory=dict)



@dataclass
class RunManifest:
    """Run-level manifest linking inputs, outputs, and digests."""

    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    random_seed: int = 0
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    dependency_fingerprint: str = ""
    digests: dict[str, str] = field(default_factory=dict)

    def finalize_digests(self, out_dir: str | Path) -> None:
        """Compute file digests for all declared outputs."""
        base = Path(out_dir)
        for rel in self.outputs.values():
            p = base / rel
            if p.exists() and p.is_file():
                self.digests[str(rel)] = sha256_file(p)

    def finalize_dependency_fingerprint(self) -> None:
        """Compute deterministic fingerprint from dependency versions."""
        canonical = json.dumps(self.dependencies, sort_keys=True, separators=(",", ":"))
        self.dependency_fingerprint = _sha256_text(canonical)

