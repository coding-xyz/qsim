from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

SCHEMA_VERSION = "1.0"


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 digest for a file."""
    p = Path(path)
    hasher = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def to_json_dict(obj: Any) -> dict[str, Any]:
    """Convert dataclass object to JSON-serializable dictionary."""
    return asdict(obj)


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write UTF-8 pretty JSON file and return output path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


@dataclass
class CircuitGate:
    """One logical gate operation in circuit IR."""

    name: str
    qubits: list[int] = field(default_factory=list)
    params: list[float] = field(default_factory=list)
    clbits: list[int] = field(default_factory=list)


@dataclass
class CircuitIR:
    """Normalized circuit representation used by compile pipeline."""

    schema_version: str = SCHEMA_VERSION
    format: str = "openqasm3"
    num_qubits: int = 0
    num_clbits: int = 0
    gates: list[CircuitGate] = field(default_factory=list)
    source_qasm: str = ""


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


@dataclass
class Carrier:
    """Carrier tone parameters for pulse modulation."""

    freq: float
    phase: float = 0.0


@dataclass
class PulseSpec:
    """Single pulse segment scheduled on a channel."""

    t0: float
    t1: float
    amp: float
    shape: str
    params: dict[str, Any] = field(default_factory=dict)
    carrier: Carrier | None = None


@dataclass
class ChannelSpec:
    """Collection of pulses for one hardware channel."""

    name: str
    pulses: list[PulseSpec] = field(default_factory=list)


@dataclass
class PulseIR:
    """Pulse-level intermediate representation for one schedule."""

    schema_version: str = SCHEMA_VERSION
    t_end: float = 0.0
    channels: list[ChannelSpec] = field(default_factory=list)


@dataclass
class ExecutableModel:
    """Lowered executable model before numeric model construction."""

    schema_version: str = SCHEMA_VERSION
    level: str = "qubit"
    solver: str = "se"
    h_terms: list[dict[str, Any]] = field(default_factory=list)
    noise_terms: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSpec:
    """Engine-consumable simulation model specification."""

    schema_version: str = SCHEMA_VERSION
    engine: str = "mock"
    solver: str = "se"
    dimension: int = 2
    t_end: float = 0.0
    dt: float = 1.0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    """Normalized simulation output trace."""

    schema_version: str = SCHEMA_VERSION
    engine: str = "mock"
    times: list[float] = field(default_factory=list)
    states: list[list[float]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Observables:
    """Computed analysis observables from a trace."""

    schema_version: str = SCHEMA_VERSION
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Report:
    """High-level analysis report and error budget summary."""

    schema_version: str = SCHEMA_VERSION
    summary: dict[str, Any] = field(default_factory=dict)
    error_budget: dict[str, float] = field(default_factory=dict)


@dataclass
class SyndromeFrame:
    """QEC syndrome data frame for one decoding task."""

    schema_version: str = SCHEMA_VERSION
    rounds: int = 0
    detectors: list[list[int]] = field(default_factory=list)
    observables: list[int] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PriorModel:
    """QEC prior model with graph/hypergraph style weighted terms."""

    schema_version: str = SCHEMA_VERSION
    builder_name: str = "mock_prior"
    builder_rev: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecoderInput:
    """Decoder input payload combining syndrome and prior model."""

    schema_version: str = SCHEMA_VERSION
    syndrome: SyndromeFrame = field(default_factory=SyndromeFrame)
    prior: PriorModel = field(default_factory=PriorModel)
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecoderOutput:
    """Normalized decoder output with correction hints and confidence."""

    schema_version: str = SCHEMA_VERSION
    decoder_name: str = "mock_decoder"
    decoder_rev: str = ""
    status: str = "ok"
    corrections: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogicalErrorSummary:
    """Logical error summary derived from decoder output."""

    schema_version: str = SCHEMA_VERSION
    logical_x: float = 0.0
    logical_z: float = 0.0
    shots: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


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
