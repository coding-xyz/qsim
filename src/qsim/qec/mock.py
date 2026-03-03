"""Mock prior and decoder implementations for local workflow testing."""

from __future__ import annotations

import hashlib

from qsim.common.schemas import (
    DecoderInput,
    DecoderOutput,
    LogicalErrorSummary,
    PriorModel,
    SyndromeFrame,
    utc_now_iso,
)
from qsim.qec.interfaces import IDecoder, IPriorBuilder


def _short_rev(value: str) -> str:
    """Return a short deterministic revision fingerprint."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


class MockPriorBuilder(IPriorBuilder):
    """Minimal prior builder used as M1 placeholder."""

    name = "mock_prior"

    def build(self, syndrome: SyndromeFrame, context: dict | None = None) -> PriorModel:
        """Build a simple chain-like prior graph from syndrome dimensions."""
        ctx = context or {}
        rounds = max(1, int(syndrome.rounds or 1))
        nodes = [{"id": i, "kind": "detector"} for i in range(len(syndrome.detectors))]
        edges = [
            {"u": i, "v": i + 1, "weight": 1.0 / rounds}
            for i in range(max(0, len(nodes) - 1))
        ]
        rev = _short_rev(f"{self.name}:{rounds}:{len(nodes)}")
        return PriorModel(
            builder_name=self.name,
            builder_rev=rev,
            nodes=nodes,
            edges=edges,
            metadata={"generated_at": utc_now_iso(), "context": ctx},
        )


class MockDecoder(IDecoder):
    """Minimal decoder used as M1 placeholder."""

    name = "mock_decoder"

    def run(self, decoder_input: DecoderInput, options: dict | None = None) -> DecoderOutput:
        """Emit deterministic placeholder corrections and confidence."""
        opts = options or {}
        n = len(decoder_input.syndrome.detectors)
        corrections = [{"type": "flip", "target": i} for i in range(min(2, n))]
        rev = _short_rev(f"{self.name}:{n}:{len(corrections)}")
        confidence = 0.5 if n > 0 else 1.0
        return DecoderOutput(
            decoder_name=self.name,
            decoder_rev=rev,
            status="ok",
            corrections=corrections,
            confidence=confidence,
            metadata={"options": opts, "input_nodes": len(decoder_input.prior.nodes)},
        )


def summarize_logical_error(decoder_output: DecoderOutput, shots: int) -> LogicalErrorSummary:
    """Build a deterministic placeholder logical-error summary.

    Args:
        decoder_output: Decoder output to summarize.
        shots: Effective shot count used for normalization.

    Returns:
        ``LogicalErrorSummary`` with synthetic logical-X/Z rates.
    """
    s = max(1, int(shots))
    base = min(1.0, max(0.0, 1.0 - float(decoder_output.confidence)))
    return LogicalErrorSummary(
        logical_x=base,
        logical_z=min(1.0, base * 0.8),
        shots=s,
        metadata={"decoder_name": decoder_output.decoder_name, "status": decoder_output.status},
    )
