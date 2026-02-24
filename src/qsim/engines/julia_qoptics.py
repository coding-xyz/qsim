from __future__ import annotations

import math

from qsim.common.schemas import ModelSpec, Trace
from qsim.engines.base import Engine


class JuliaQuantumOpticsEngine(Engine):
    """Mock Julia QuantumOptics engine adapter."""

    name = "julia_quantumoptics"

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trace:
        """Return synthetic trace matching engine interface."""
        run_options = run_options or {}
        n = max(2, int(model_spec.t_end / max(model_spec.dt, 1e-9)) + 1)
        times = [i * model_spec.dt for i in range(n)]
        tau = float(run_options.get("tau", 200.0))
        states = [[math.exp(-t / max(tau, 1e-9)), 1.0 - math.exp(-t / max(tau, 1e-9))] for t in times]
        return Trace(engine="julia-quantumoptics-mock", times=times, states=states, metadata={"solver": model_spec.solver})
