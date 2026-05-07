"""Collapse-operator and stochastic-noise lowering for QuTiP."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from qsim.engines.qutip.runtime import QutipPlan, QutipRunConfig, QutipSolverInputs, QutipSystem


def build_collapse_and_noise(
    engine,
    setup: QutipPlan,
    system: QutipSystem,
) -> QutipSolverInputs:
    """Build QuTiP collapse operators and append stochastic noise terms."""
    model_spec = setup.model_spec
    model_type = setup.model_type
    n_qubits = setup.n_qubits
    c_ops = []
    cavity_a = system.cavity_a
    if engine._is_cqed_model(model_type) and cavity_a is not None:
        readout_chain = setup.readout_chain
        cavity_kappa_int = max(0.0, 2.0 * math.pi * float(readout_chain.get("kappa_int_Hz", 0.0)))
        cavity_kappa_ext = max(0.0, 2.0 * math.pi * float(readout_chain.get("kappa_ext_Hz", 0.0)))
        if cavity_kappa_int > 0.0:
            c_ops.append(math.sqrt(cavity_kappa_int) * cavity_a)
        if cavity_kappa_ext > 0.0 and setup.readout_mode != "monitored_sme":
            c_ops.append(math.sqrt(cavity_kappa_ext) * cavity_a)

    for item in model_spec.noise.collapse_channels:
        target = int(item.target)
        if target < 0 or target >= n_qubits:
            continue
        kind = str(item.kind or "relaxation").lower()
        rate = max(0.0, float(item.rate_rad_s))
        if rate <= 0:
            continue
        if kind == "relaxation":
            c_ops.append(math.sqrt(rate) * system.lower_ops[target])
        elif kind == "dephasing":
            c_ops.append(engine._dephasing_collapse_prefactor(rate, model_type) * system.z_ops[target])
        elif kind == "excitation":
            c_ops.append(math.sqrt(rate) * system.raise_ops[target])

    selected_noise, seed = _append_stochastic_noise(engine, setup, system, setup.run_config)
    return QutipSolverInputs(c_ops=c_ops, selected_noise=selected_noise, seed=seed)


def _append_stochastic_noise(
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    run_config: QutipRunConfig,
) -> tuple[str, int]:
    model_spec = setup.model_spec
    selected_noise = str(model_spec.noise.selected_model or "markovian_lindblad").lower()
    stochastic = list(model_spec.noise.stochastic_channels)
    seed = int(run_config.seed)
    if setup.solver == "heom":
        return selected_noise, seed
    rng = np.random.default_rng(seed)
    if selected_noise in {"one_over_f", "ou"} and stochastic:
        for item in stochastic:
            target = int(item.q)
            if target < 0 or target >= setup.n_qubits:
                continue
            if selected_noise == "one_over_f":
                series = engine._one_over_f_trace(
                    tlist=setup.tlist,
                    amp=float(item.one_over_f_amp_rad_s),
                    fmin=float(item.one_over_f_fmin),
                    fmax=float(item.one_over_f_fmax or 0.5 / max(setup.dt, 1e-12)),
                    exponent=float(item.one_over_f_exponent),
                    ncomp=int(run_config.one_over_f_components),
                    rng=rng,
                )
            else:
                series = engine._ou_trace(
                    tlist=setup.tlist,
                    sigma=float(item.ou_sigma_rad_s),
                    tau=float(item.ou_tau),
                    rng=rng,
                )
            system.H.append(
                [
                    system.z_ops[target],
                    lambda t, _a=None, s=series, x=setup.tlist: float(np.interp(float(t), x, s)),
                ]
            )
    return selected_noise, seed
