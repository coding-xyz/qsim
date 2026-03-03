"""QuantumToolbox.jl engine adapter exposed through the qsim engine API."""

from __future__ import annotations

from qsim.common.schemas import ModelSpec
from qsim.engines.base import Engine
from qsim.engines.julia_bridge import JuliaBridgeRunner


class JuliaQuantumToolboxEngine(Engine):
    """Julia QuantumToolbox engine adapter (native bridge only)."""

    name = "julia_quantumtoolbox"
    _bridge = JuliaBridgeRunner(engine_package="quantumtoolbox")

    def run(self, model_spec: ModelSpec, run_options: dict | None = None):
        run_options = run_options or {}
        return self._bridge.run(model_spec, run_options=run_options)
