"""Dataclasses and JSON helpers for qsim workflow schemas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

SCHEMA_VERSION = "1.0"
COMPLEX_JSON_TAG = "__qsim_complex__"


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


def json_safe(value: Any) -> Any:
    """Convert nested values into a JSON-safe representation."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, complex):
        return {COMPLEX_JSON_TAG: [float(value.real), float(value.imag)]}
    if hasattr(value, "tolist"):
        try:
            return json_safe(value.tolist())
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def json_restore(value: Any) -> Any:
    """Restore nested values previously converted by ``json_safe``."""
    if isinstance(value, dict):
        if set(value.keys()) == {COMPLEX_JSON_TAG}:
            pair = list(value.get(COMPLEX_JSON_TAG, []) or [])
            if len(pair) >= 2:
                return complex(float(pair[0]), float(pair[1]))
        return {str(k): json_restore(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_restore(item) for item in value]
    return value


def make_series_payload(
    values: list[list[float]] | list[float],
    *,
    quantity: str,
    description: str,
    series_labels: list[str] | None = None,
    unit: str = "",
) -> dict[str, Any]:
    """Build a named time-series payload for classical trajectory channels."""
    if values and isinstance(values[0], (int, float)):
        rows = [[float(v)] for v in list(values)]  # type: ignore[index]
    else:
        rows = [[float(v) for v in row] for row in list(values)]  # type: ignore[arg-type]
    if series_labels is None and rows:
        series_labels = [f"s{i}" for i in range(len(rows[0]))]
    return {
        "quantity": str(quantity),
        "description": str(description),
        "unit": str(unit or ""),
        "series_labels": list(series_labels or []),
        "values": rows,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write UTF-8 pretty JSON file and return output path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
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

    @property
    def analysis(self) -> str:
        return str(self.analysis_pipeline)

    @analysis.setter
    def analysis(self, value: str) -> None:
        self.analysis_pipeline = str(value)


@dataclass
class Carrier:
    """Carrier tone parameters for pulse modulation."""

    freq: float
    phase: float = 0.0


@dataclass
class PulseSpec:
    """Single pulse segment scheduled on a channel."""

    t0_s: float
    t1_s: float
    amp: float
    shape: str
    params: dict[str, Any] = field(default_factory=dict)
    carrier: Carrier | None = None

    @property
    def duration_s(self) -> float:
        return float(self.t1_s) - float(self.t0_s)

    @property
    def t0_ns(self) -> float:
        return round(float(self.t0_s) * 1e9, 12)

    @property
    def t1_ns(self) -> float:
        return round(float(self.t1_s) * 1e9, 12)

    @property
    def duration_ns(self) -> float:
        return round(self.duration_s * 1e9, 12)


@dataclass
class ChannelSpec:
    """Collection of pulses for one hardware channel."""

    name: str
    pulses: list[PulseSpec] = field(default_factory=list)


@dataclass
class PulseIR:
    """Pulse-level intermediate representation for one schedule."""

    schema_version: str = SCHEMA_VERSION
    t_end_s: float = 0.0
    channels: list[ChannelSpec] = field(default_factory=list)

    @property
    def t_end_ns(self) -> float:
        return round(float(self.t_end_s) * 1e9, 12)


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
