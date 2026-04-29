"""Executable-model to solver-model conversion utilities."""

from __future__ import annotations

from typing import Any
from typing import Protocol

from qsim.backend.config import normalize_model_build_config
from qsim.backend.model.lowering import (
    lower_couplings,
    lower_frame,
    lower_hamiltonian,
    lower_noise,
    lower_readout,
    lower_sampled_channels,
    lower_study,
    lower_system,
    lower_system_context,
    lower_time,
)
from qsim.common.schemas import (
    AnalysisRequestSpec,
    CircuitIR,
    CircuitSpec,
    ExecutableModel,
    ModelSpec,
    SolverSpec,
)


class IModelBuilder(Protocol):
    """Protocol for building executable model spec from lowered artifacts."""

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
        frame: dict[str, Any] | None = None,
        solver_run: dict[str, Any] | None = None,
        analyser: dict[str, Any] | None = None,
        study: list[dict[str, Any]] | None = None,
        primary_step: dict[str, Any] | None = None,
        circuit: CircuitIR | CircuitSpec | None = None,
    ) -> ModelSpec:
        ...


class DefaultModelBuilder:
    """Assemble ``ModelSpec`` from engine-neutral lowering stages."""

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
        frame: dict[str, Any] | None = None,
        solver_run: dict[str, Any] | None = None,
        analyser: dict[str, Any] | None = None,
        study: list[dict[str, Any]] | None = None,
        primary_step: dict[str, Any] | None = None,
        circuit: CircuitIR | CircuitSpec | None = None,
    ) -> ModelSpec:
        """Construct normalized ``ModelSpec`` consumed by simulation engines."""
        pulse_sample_cfg = dict(pulse_samples or {})
        config = normalize_model_build_config(
            device=hw,
            noise=noise,
            solver_run=solver_run,
            frame=frame,
            analyser=analyser,
            study=study,
            primary_step=primary_step,
        )

        study_spec = lower_study(config.study)
        time_spec = lower_time(executable, pulse_sample_cfg, config.solver)
        system_context = lower_system_context(executable, config.device, study_spec)
        channels = lower_sampled_channels(config.device, pulse_sample_cfg, system_context.num_qubits)
        frame_spec = lower_frame(config.frame, config.device, system_context.raw_qubits, channels, system_context.num_qubits)
        couplings = lower_couplings(config.device, system_context.num_qubits)

        solver_options = {
            key: value
            for key, value in config.solver.to_dict().items()
            if key not in {"dt_s", "t_end_s", "t_padding_s", "seed", "ntraj", "mcwf_ntraj"}
        }

        return ModelSpec(
            engine="qutip",
            circuit=(
                circuit
                if isinstance(circuit, CircuitSpec)
                else CircuitSpec.from_circuit_ir(circuit) if isinstance(circuit, CircuitIR) else None
            ),
            solver=SolverSpec(
                mode=str(executable.solver),
                engine="qutip",
                seed=config.solver.seed,
                ntraj=config.solver.ntraj,
                options=solver_options,
            ),
            time=time_spec,
            frame=frame_spec.spec,
            system=lower_system(executable, config.device, study_spec, system_context, frame_spec),
            hamiltonian=lower_hamiltonian(executable, channels, couplings),
            noise=lower_noise(config.noise, config.device, system_context.raw_qubits, system_context.num_qubits, time_spec.dt_s),
            readout=lower_readout(executable, study_spec, system_context, channels),
            analysis_request=AnalysisRequestSpec(
                trajectory=config.analysis.trajectory,
                config=config.analysis.to_dict(),
            ),
            study=study_spec,
            metadata={"noise_terms": list(executable.noise_terms)},
        )
