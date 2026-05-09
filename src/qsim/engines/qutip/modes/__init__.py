"""Solver-mode entry points for the QuTiP backend."""

from __future__ import annotations

from typing import Any

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest
from qsim.engines.qutip.modes.heom import run_heom_trajectory
from qsim.engines.qutip.modes.mcwf import run_hybrid_readout, run_mcwf_trajectory
from qsim.engines.qutip.modes.me import run_me_trajectory
from qsim.engines.qutip.modes.se import run_se_trajectory
from qsim.engines.qutip.modes.sme import run_monitored_sme


_TRAJECTORY_RUNNERS = {
    "se": run_se_trajectory,
    "me": run_me_trajectory,
    "mcwf": run_mcwf_trajectory,
    "heom": run_heom_trajectory,
}


def run_solver_mode(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Dispatch the prepared model to the selected QuTiP solver-mode module."""
    if setup.readout_mode == "monitored_sme":
        return run_monitored_sme(
            engine=engine,
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )
    if setup.readout_mode == "hybrid_classical" and system.cavity_a is not None and system.cavity_n is not None:
        return run_hybrid_readout(
            engine=engine,
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )
    try:
        runner = _TRAJECTORY_RUNNERS[setup.solver]
    except KeyError as exc:
        raise ValueError(f"Unsupported QuTiP solver mode: {setup.solver}") from exc
    return runner(
        engine=engine,
        setup=setup,
        system=system,
        solver_inputs=solver_inputs,
        trajectory_cfg=trajectory_cfg,
    )


__all__ = ["run_hybrid_readout", "run_monitored_sme", "run_solver_mode"]
