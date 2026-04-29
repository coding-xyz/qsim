"""Monte-Carlo wave-function solver mode for QuTiP."""

from __future__ import annotations

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.modes.common import base_metadata, build_base_e_ops, standard_trajectory_from_result
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


def run_mcwf(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
    e_ops,
):
    """Run ``qutip.mcsolve`` for quantum-jump trajectories."""
    return setup.qt.mcsolve(
        system.H,
        system.psi0,
        setup.tlist,
        c_ops=solver_inputs.c_ops,
        e_ops=e_ops,
        ntraj=setup.run_config.ntraj,
        options=trajectory_cfg.options,
    )


def run_mcwf_trajectory(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Run MCWF mode and return a normalized trajectory."""
    base_e_ops, readout_expect_ix = build_base_e_ops(engine, setup, system)
    try:
        result = run_mcwf(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
            e_ops=base_e_ops,
        )
    except Exception as exc:
        raise RuntimeError(f"QuTiP execution failed: {exc}") from exc
    return standard_trajectory_from_result(
        engine,
        setup=setup,
        system=system,
        solver_inputs=solver_inputs,
        trajectory_cfg=trajectory_cfg,
        result=result,
        readout_expect_ix=readout_expect_ix,
    )


def run_hybrid_readout(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Run MCWF dynamics with hybrid classical readout feedback."""
    try:
        hybrid = engine._run_hybrid_cqed_mcwf(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )
    except Exception as exc:
        raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

    metadata = base_metadata(setup, solver_inputs)
    metadata["hybrid_update_mode"] = setup.hybrid_update_mode
    metadata.update(dict(hybrid.get("metadata", {}) or {}))
    qstate = dict(hybrid.get("quantum_state_trajectory", {}) or {})
    if not qstate:
        qstate = dict(metadata.pop("quantum_state_trajectory", {}) or {})
    wave_function, density_matrix = engine._quantum_payloads(qstate)
    return Trajectory(
        engine="qutip",
        times=list(hybrid.get("times", setup.tlist.astype(float).tolist()) or []),
        wave_function=wave_function,
        density_matrix=density_matrix,
        metadata=metadata,
    )
