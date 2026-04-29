"""Shared trajectory assembly helpers for QuTiP solver modes."""

from __future__ import annotations

from typing import Any

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.dynamics.postprocess import attach_postprocessed_readout
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


def base_metadata(setup: QutipPlan, solver_inputs: QutipSolverInputs) -> dict[str, Any]:
    """Build common trajectory metadata for QuTiP mode outputs."""
    model_spec = setup.model_spec
    return {
        "solver": setup.solver,
        "model_type": setup.model_type,
        "num_qubits": setup.n_qubits,
        "num_controls": len(model_spec.hamiltonian.control_terms),
        "num_readout_controls": len(model_spec.readout.controls if model_spec.readout else []),
        "num_collapse_ops": len(solver_inputs.c_ops),
        "selected_noise": solver_inputs.selected_noise,
        "frame_mode": setup.frame_mode,
        "rwa": setup.rwa,
    }


def build_base_e_ops(engine, setup: QutipPlan, system: QutipSystem) -> tuple[list[Any], dict[str, Any]]:
    """Build expectation operators needed by standard solver modes."""
    base_e_ops = list(system.e_ops)
    readout_expect_ix: dict[str, Any] = {}
    if engine._is_cqed_model(setup.model_type) and system.cavity_a is not None and system.cavity_n is not None:
        readout_expect_ix["cavity_a"] = len(base_e_ops)
        base_e_ops.append(system.cavity_a)
        readout_expect_ix["cavity_n"] = len(base_e_ops)
        base_e_ops.append(system.cavity_n)
        lowering_ix: list[int] = []
        for op in system.lower_ops:
            lowering_ix.append(len(base_e_ops))
            base_e_ops.append(op)
        readout_expect_ix["qubit_lowering"] = lowering_ix
    return base_e_ops, readout_expect_ix


def standard_trajectory_from_result(
    engine,
    *,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
    result,
    readout_expect_ix: dict[str, Any],
) -> Trajectory:
    """Convert a standard QuTiP solver result to a normalized trajectory."""
    solver = setup.solver
    tlist = setup.tlist
    quantum_state_trajectory = engine._extract_quantum_state_trajectory(
        result,
        solver,
        trajectory_cfg.requested_state_kind,
    )
    wave_function, density_matrix = engine._quantum_payloads(quantum_state_trajectory)
    metadata = base_metadata(setup, solver_inputs)
    attach_postprocessed_readout(
        engine,
        metadata=metadata,
        setup=setup,
        system=system,
        solver_inputs=solver_inputs,
        result=result,
        readout_expect_ix=readout_expect_ix,
    )
    return Trajectory(
        engine="qutip",
        times=tlist.astype(float).tolist(),
        wave_function=wave_function,
        density_matrix=density_matrix,
        metadata=metadata,
    )
