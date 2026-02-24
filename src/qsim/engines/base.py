from __future__ import annotations

from abc import ABC, abstractmethod

from qsim.common.schemas import ModelSpec, Trace


class Engine(ABC):
    """Abstract base class for simulation backends."""

    name = "base"

    @abstractmethod
    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trace:
        """Run simulation and return normalized ``Trace``."""
        raise NotImplementedError
