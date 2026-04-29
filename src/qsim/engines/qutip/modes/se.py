"""Schrodinger-equation solver mode for QuTiP."""

from __future__ import annotations

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.modes.common import build_base_e_ops, standard_trajectory_from_result
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


def run_se(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    trajectory_cfg: QutipTrajectoryRequest,
    e_ops,
):
    """Run ``qutip.sesolve`` for closed-system dynamics."""
    return setup.qt.sesolve(
        system.H,
        system.psi0,
        setup.tlist,
        e_ops=e_ops,
        options=trajectory_cfg.options,
    )


def run_se_trajectory(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Run SE mode and return a normalized trajectory."""
    base_e_ops, readout_expect_ix = build_base_e_ops(engine, setup, system)
    try:
        result = run_se(
            setup=setup,
            system=system,
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
