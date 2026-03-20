"""QuantumToolbox.jl engine implementation exposed through the qsim engine API."""

from __future__ import annotations

from qsim.common.schemas import ModelSpec
from qsim.engines.base import Engine
from qsim.engines.julia_runtime import JuliaRuntimeRunner


class QToolboxEngine(Engine):
    """QuantumToolbox.jl-backed dynamics engine."""

    name = "qtoolbox"
    _runtime = JuliaRuntimeRunner(engine_package="quantumtoolbox")

    def run(self, model_spec: ModelSpec, run_options: dict | None = None):
        return self._runtime.run(model_spec, run_options=dict(run_options or {}))


__all__ = ["QToolboxEngine"]
