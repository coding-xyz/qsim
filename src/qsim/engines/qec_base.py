from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QECAnalysisEngine(ABC):
    """Abstract interface for QEC-oriented Pauli+/Kraus analysis engines.

    Implementations are expected to provide an ``epsilon_d`` estimate for a
    requested code distance and include enough metadata to diagnose whether the
    run used native backend capabilities or fallback heuristics.
    """

    name = "qec_base"

    @abstractmethod
    def run_pauli_plus(
        self,
        model_spec: dict[str, Any],
        *,
        code_distance: int,
        shots: int,
        seed: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run Pauli+ style analysis and return normalized result payload.

        Returns:
            A dictionary that must contain at least:
            - ``epsilon_d``: logical error rate proxy at code distance ``d``.
            - ``engine`` / ``engine_rev``.
            - ``backend`` / ``quality`` and optional diagnostic metadata.
        """
        raise NotImplementedError
