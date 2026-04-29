"""HEOM solver mode placeholder for the QuTiP backend."""

from __future__ import annotations

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


def run_heom(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
    e_ops,
):
    """Run HEOM dynamics once bath/hierarchy specs are available."""
    del setup, system, solver_inputs, trajectory_cfg, e_ops
    raise NotImplementedError("QuTiP HEOM mode requires typed bath/hierarchy specs before it can run.")


def run_heom_trajectory(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """HEOM trajectory entry point reserved for non-Markovian bath support."""
    del engine, setup, system, solver_inputs, trajectory_cfg
    raise NotImplementedError("QuTiP HEOM mode is not implemented yet.")
