"""HEOM solver mode for the QuTiP backend."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.modes.common import build_base_e_ops, standard_trajectory_from_result
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


def _heom_options(setup: QutipPlan) -> dict[str, Any]:
    return dict(setup.run_config.backend_options.get("heom", {}) or {})


def _one_over_f_exponents(
    *,
    amp: float,
    fmin: float,
    fmax: float,
    exponent: float,
    nterms: int,
    t_end: float,
) -> tuple[list[float], list[float]]:
    """Approximate a one-over-f dephasing spectrum with real HEOM exponents."""
    if amp <= 0.0:
        return [], []
    configured_fmin = float(fmin or 0.0)
    fmin = max(configured_fmin, 1e-6) if configured_fmin > 0.0 else max(1.0 / max(100.0 * t_end, 1e-9), 1e-6)
    fmax = max(1.01 * fmin, float(fmax or 0.0))
    rates_hz = np.logspace(np.log10(fmin), np.log10(fmax), int(max(1, nterms)))
    weights = 1.0 / np.maximum(rates_hz, 1e-18) ** float(exponent)
    weights = weights / max(float(np.sum(weights)), 1e-18)
    vk = (2.0 * math.pi * rates_hz).astype(float)
    ck = (float(amp) ** 2 * weights).astype(float)
    return ck.tolist(), vk.tolist()


def build_heom_baths(*, setup: QutipPlan, system: QutipSystem):
    """Build QuTiP HEOM baths from the model's stochastic dephasing channels."""
    try:
        from qutip.solver.heom import BosonicBath
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM support unavailable: {exc}") from exc

    opts = _heom_options(setup)
    nterms = int(opts.get("nterms", opts.get("num_exponents", 6)))
    baths = []
    summaries = []
    selected_noise = str(setup.model_spec.noise.selected_model or "").strip().lower()
    for item in setup.model_spec.noise.stochastic_channels:
        target = int(item.q)
        if target < 0 or target >= setup.n_qubits:
            continue
        if selected_noise in {"one_over_f", "1/f", "pink"}:
            ck_real, vk_real = _one_over_f_exponents(
                amp=float(item.one_over_f_amp_rad_s),
                fmin=float(item.one_over_f_fmin),
                fmax=float(item.one_over_f_fmax or 0.5 / max(setup.dt, 1e-12)),
                exponent=float(item.one_over_f_exponent),
                nterms=nterms,
                t_end=float(setup.tlist[-1]) if setup.tlist.size else setup.dt,
            )
            label = "one_over_f"
        elif selected_noise == "ou":
            tau = max(1e-12, float(item.ou_tau))
            ck_real = [float(item.ou_sigma_rad_s) ** 2]
            vk_real = [1.0 / tau]
            label = "ou"
        else:
            continue
        if not ck_real:
            continue
        baths.append(
            BosonicBath(
                system.z_ops[target],
                ck_real=ck_real,
                vk_real=vk_real,
                ck_imag=[],
                vk_imag=[],
                tag=f"{label}_q{target}",
            )
        )
        summaries.append(
            {
                "target": target,
                "model": label,
                "num_exponents": len(ck_real),
                "max_ck_real": max(ck_real),
                "min_vk_real": min(vk_real),
                "max_vk_real": max(vk_real),
            }
        )
    if not baths:
        raise ValueError("HEOM mode requires at least one stochastic one_over_f or OU channel.")
    return (baths[0] if len(baths) == 1 else baths), summaries


def run_heom(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
    e_ops,
):
    """Run ``qutip.solver.heom.HEOMSolver`` for non-Markovian dephasing."""
    del solver_inputs
    try:
        from qutip.solver.heom import HEOMSolver
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM support unavailable: {exc}") from exc

    opts = _heom_options(setup)
    max_depth = int(opts.get("max_depth", opts.get("depth", 3)))
    bath, _summaries = build_heom_baths(setup=setup, system=system)
    hamiltonian = setup.qt.QobjEvo(system.H)
    solver = HEOMSolver(hamiltonian, bath, max_depth=max_depth, options=trajectory_cfg.options)
    state0 = setup.qt.ket2dm(system.psi0) if getattr(system.psi0, "isket", False) else system.psi0
    return solver.run(state0, setup.tlist, e_ops=e_ops)


def run_heom_trajectory(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Run HEOM mode and return a normalized trajectory."""
    base_e_ops, readout_expect_ix = build_base_e_ops(engine, setup, system)
    try:
        result = run_heom(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
            e_ops=base_e_ops,
        )
        _bath, bath_summaries = build_heom_baths(setup=setup, system=system)
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM execution failed: {exc}") from exc
    trajectory = standard_trajectory_from_result(
        engine,
        setup=setup,
        system=system,
        solver_inputs=solver_inputs,
        trajectory_cfg=trajectory_cfg,
        result=result,
        readout_expect_ix=readout_expect_ix,
    )
    trajectory.metadata["heom"] = {
        "max_depth": int(_heom_options(setup).get("max_depth", _heom_options(setup).get("depth", 3))),
        "bath_count": len(bath_summaries),
        "baths": bath_summaries,
    }
    return trajectory
