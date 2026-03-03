"""Protocol interfaces for prior builders and decoders."""

from __future__ import annotations

from typing import Protocol

from qsim.common.schemas import DecoderInput, DecoderOutput, PriorModel, SyndromeFrame


class IPriorBuilder(Protocol):
    """Protocol for QEC prior-model builders."""

    def build(self, syndrome: SyndromeFrame, context: dict | None = None) -> PriorModel:
        """Build a ``PriorModel`` from syndrome observations.

        Args:
            syndrome: Detection-event frame produced by the pipeline.
            context: Optional execution context (engine/solver/qubit count, etc.).

        Returns:
            A prior graph/model used by decoders.
        """
        ...


class IDecoder(Protocol):
    """Protocol for QEC decoder implementations."""

    def run(self, decoder_input: DecoderInput, options: dict | None = None) -> DecoderOutput:
        """Run decoder inference over a syndrome + prior bundle.

        Args:
            decoder_input: Structured input including syndrome and prior.
            options: Optional runtime options (seed/hyperparameters).

        Returns:
            ``DecoderOutput`` with corrections, confidence, and status.
        """
        ...
