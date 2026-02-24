from __future__ import annotations

import math

from qsim.common.schemas import ModelSpec, Trace
from qsim.engines.base import Engine


class JuliaQuantumToolboxEngine(Engine):
    """Mock Julia QuantumToolbox engine adapter."""

    name = "julia_quantumtoolbox"

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trace:
        """Return synthetic oscillatory trace matching engine interface."""
        run_options = run_options or {}
        n = max(2, int(model_spec.t_end / max(model_spec.dt, 1e-9)) + 1)
        times = [i * model_spec.dt for i in range(n)]
        w = float(run_options.get("omega", 0.02))
        states = [[0.5 * (1.0 + math.cos(w * t)), 0.5 * (1.0 - math.cos(w * t))] for t in times]
        return Trace(engine="julia-quantumtoolbox-mock", times=times, states=states, metadata={"solver": model_spec.solver})
