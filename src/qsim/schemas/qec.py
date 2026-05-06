"""Quantum error-correction IR and decoder schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION


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


