"""Decoder selection, execution, and report helpers for QEC workflows."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict
from typing import Any

from qsim.common.schemas import DecoderInput, DecoderOutput, LogicalErrorSummary
from qsim.qec.interfaces import IDecoder


def _short_rev(value: str) -> str:
    """Return a short deterministic revision fingerprint."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


class MWPMDecoder(IDecoder):
    """Lightweight MWPM-style decoder placeholder for P0-M3."""

    name = "mwpm"

    def run(self, decoder_input: DecoderInput, options: dict | None = None) -> DecoderOutput:
        """Decode with parity-pairing heuristic over detector columns."""
        opts = options or {}
        rows = decoder_input.syndrome.detectors
        n_cols = len(rows[0]) if rows else 0
        # Pair odd-parity detector columns and mark flips.
        odd_cols: list[int] = []
        for c in range(n_cols):
            parity = sum(int(r[c]) for r in rows) % 2
            if parity == 1:
                odd_cols.append(c)
        corrections = [{"type": "flip", "target": c} for c in odd_cols]
        confidence = 1.0 / (1.0 + len(odd_cols))
        rev = _short_rev(f"{self.name}:{len(rows)}:{n_cols}:{len(corrections)}")
        return DecoderOutput(
            decoder_name=self.name,
            decoder_rev=rev,
            status="ok",
            corrections=corrections,
            confidence=float(confidence),
            metadata={"options": opts, "strategy": "parity_pairing"},
        )


class BPDecoder(IDecoder):
    """Lightweight BP-style decoder placeholder for P0-M3."""

    name = "bp"

    def run(self, decoder_input: DecoderInput, options: dict | None = None) -> DecoderOutput:
        """Decode with iterative column-wise belief updates."""
        opts = options or {}
        rows = decoder_input.syndrome.detectors
        n_cols = len(rows[0]) if rows else 0
        iters = max(1, int(opts.get("max_iter", 6)))
        damping = float(opts.get("damping", 0.5))
        # Simple column-wise belief update from syndrome frequencies.
        beliefs = [0.5 for _ in range(n_cols)]
        for _ in range(iters):
            for c in range(n_cols):
                freq = sum(int(r[c]) for r in rows) / max(1, len(rows))
                beliefs[c] = damping * beliefs[c] + (1.0 - damping) * freq
        corrections = [{"type": "flip", "target": c} for c, b in enumerate(beliefs) if b > 0.5]
        # Confidence drops as entropy increases.
        entropy = 0.0
        for b in beliefs:
            p = min(1.0 - 1e-9, max(1e-9, float(b)))
            entropy += -(p * math.log(p) + (1.0 - p) * math.log(1.0 - p))
        entropy /= max(1, len(beliefs))
        confidence = max(0.0, min(1.0, 1.0 - entropy))
        rev = _short_rev(f"{self.name}:{len(rows)}:{n_cols}:{iters}:{damping:.3f}")
        status = "ok" if iters >= 2 else "warning"
        return DecoderOutput(
            decoder_name=self.name,
            decoder_rev=rev,
            status=status,
            corrections=corrections,
            confidence=float(confidence),
            metadata={"options": opts, "strategy": "column_belief"},
        )


def get_decoder(name: str) -> IDecoder:
    """Return decoder implementation by name.

    Supports ``mwpm`` and ``bp``. Unknown names fall back to ``MockDecoder``.
    """
    key = (name or "mwpm").lower()
    if key == "bp":
        return BPDecoder()
    if key == "mwpm":
        return MWPMDecoder()
    from qsim.qec.mock import MockDecoder

    return MockDecoder()


def summarize_logical_error(decoder_output: DecoderOutput, shots: int) -> LogicalErrorSummary:
    """Build logical error summary from decoder output.

    Args:
        decoder_output: Decoder output containing confidence/corrections.
        shots: Effective shot count used for normalization.

    Returns:
        ``LogicalErrorSummary`` with synthetic logical-X/Z rates.
    """
    s = max(1, int(shots))
    base = min(1.0, max(0.0, 1.0 - float(decoder_output.confidence)))
    # Use correction load as a simple logical-Z inflation term.
    load = min(1.0, len(decoder_output.corrections) / max(1, s))
    return LogicalErrorSummary(
        logical_x=base,
        logical_z=min(1.0, 0.8 * base + 0.2 * load),
        shots=s,
        metadata={"decoder_name": decoder_output.decoder_name, "status": decoder_output.status},
    )


def build_decoder_report(
    decoder_input: DecoderInput,
    decoder_output: DecoderOutput,
    elapsed_s: float,
) -> dict[str, Any]:
    """Create a structured decoder report.

    The report is designed for persistent artifacts and manifest linkage.
    """
    return {
        "schema_version": "1.0",
        "decoder_name": decoder_output.decoder_name,
        "decoder_rev": decoder_output.decoder_rev,
        "status": decoder_output.status,
        "elapsed_s": float(elapsed_s),
        "num_corrections": len(decoder_output.corrections),
        "confidence": float(decoder_output.confidence),
        "input_summary": {
            "rounds": int(decoder_input.syndrome.rounds),
            "num_rows": len(decoder_input.syndrome.detectors),
            "num_cols": len(decoder_input.syndrome.detectors[0]) if decoder_input.syndrome.detectors else 0,
            "prior_nodes": len(decoder_input.prior.nodes),
            "prior_edges": len(decoder_input.prior.edges),
        },
        "decoder_output_snapshot": asdict(decoder_output),
    }
