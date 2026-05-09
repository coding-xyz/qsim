"""HEOM solver mode for the QuTiP backend."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from math import comb
from typing import Any

import numpy as np

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.modes.common import build_base_e_ops, standard_trajectory_from_result
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


HEOM_UNITS = {
    "time_unit": "s",
    "hamiltonian_unit": "rad/s",
    "vk_unit": "1/s",
    "ck_unit": "(rad/s)^2",
}


@dataclass
class BathExpansionOptions:
    """Typed HEOM bath-expansion controls for one source kind."""

    method: str = "multi_lorentzian"
    nterms: int = 6
    grid: str = "log"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, default_method: str = "multi_lorentzian", default_nterms: int = 6) -> "BathExpansionOptions":
        raw = dict(data or {})
        return cls(
            method=str(raw.get("method", default_method) or default_method),
            nterms=int(raw.get("nterms", raw.get("num_exponents", default_nterms)) or default_nterms),
            grid=str(raw.get("grid", "log") or "log"),
        )


@dataclass
class HeomSolverOptions:
    """Typed QuTiP HEOM solver options."""

    max_depth: int = 3
    max_ados: int = 5000
    max_dense_memory_mb: float = 0.0
    dephasing_coupling: str = "auto"
    bath_expansion: dict[str, BathExpansionOptions] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_backend_options(cls, data: dict[str, Any] | None) -> "HeomSolverOptions":
        raw = dict(data or {})
        default_nterms = int(raw.get("nterms", raw.get("num_exponents", 6)) or 6)
        expansion_raw = dict(raw.get("bath_expansion", {}) or {})
        bath_expansion = {
            "one_over_f": BathExpansionOptions.from_dict(
                expansion_raw.get("one_over_f", {}),
                default_method="multi_lorentzian",
                default_nterms=default_nterms,
            ),
            "ou": BathExpansionOptions.from_dict(
                expansion_raw.get("ou", {}),
                default_method="direct_exponential",
                default_nterms=1,
            ),
        }
        return cls(
            max_depth=int(raw.get("max_depth", raw.get("depth", 3)) or 3),
            max_ados=int(raw.get("max_ados", 5000) or 0),
            max_dense_memory_mb=float(raw.get("max_dense_memory_mb", 0.0) or 0.0),
            dephasing_coupling=str(raw.get("dephasing_coupling", "auto") or "auto"),
            bath_expansion=bath_expansion,
            raw=raw,
        )

    def expansion_for(self, kind: str) -> BathExpansionOptions:
        return self.bath_expansion.get(str(kind).strip().lower(), BathExpansionOptions())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["bath_expansion"] = {key: asdict(value) for key, value in self.bath_expansion.items()}
        return data


@dataclass
class HeomBathSummary:
    """Typed summary of one HEOM bath realization."""

    target: int
    targets: list[int]
    source_id: str
    model: str
    interpretation: str
    coupling_operator: str
    coupling_scale: float
    coupling_convention_source: str
    units: dict[str, str]
    expansion_method: str
    expansion_grid: str
    num_exponents: int
    sum_ck_real: float
    max_ck_real: float
    min_vk_real: float
    max_vk_real: float


@dataclass
class HeomRunSummary:
    """Typed summary serialized onto trajectory metadata."""

    options: HeomSolverOptions
    bath_count: int
    uses_liouvillian: bool
    markovian_c_ops: int
    approximation: str
    fit_method: str
    units: dict[str, str]
    size: dict[str, int | float]
    baths: list[HeomBathSummary]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.options.to_dict(),
            "bath_count": self.bath_count,
            "uses_liouvillian": self.uses_liouvillian,
            "markovian_c_ops": self.markovian_c_ops,
            "approximation": self.approximation,
            "fit_method": self.fit_method,
            "units": dict(self.units),
            **dict(self.size),
            "baths": [asdict(item) for item in self.baths],
        }


def _heom_options(setup: QutipPlan) -> dict[str, Any]:
    return dict(setup.run_config.backend_options.get("heom", {}) or {})


def _typed_heom_options(setup: QutipPlan) -> HeomSolverOptions:
    return HeomSolverOptions.from_backend_options(_heom_options(setup))


def _one_over_f_exponents(
    *,
    amp: float,
    fmin: float,
    fmax: float,
    exponent: float,
    nterms: int,
    t_end: float,
) -> tuple[list[float], list[float]]:
    """Approximate classical 1/f dephasing noise with real HEOM exponents."""
    if amp <= 0.0:
        return [], []
    configured_fmin = float(fmin or 0.0)
    fmin = max(configured_fmin, 1e-6) if configured_fmin > 0.0 else max(1.0 / max(100.0 * t_end, 1e-9), 1e-6)
    fmax = max(1.01 * fmin, float(fmax or 0.0))
    edges_hz = np.logspace(np.log10(fmin), np.log10(fmax), int(max(1, nterms)) + 1)
    rates_hz = np.sqrt(edges_hz[:-1] * edges_hz[1:])
    widths_hz = np.diff(edges_hz)
    weights = widths_hz / np.maximum(rates_hz, 1e-18) ** float(exponent)
    weights = weights / max(float(np.sum(weights)), 1e-18)
    vk = (2.0 * math.pi * rates_hz).astype(float)
    ck = (float(amp) ** 2 * weights).astype(float)
    return ck.tolist(), vk.tolist()


def _dephasing_coupling_operator(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    target: int,
    opts: HeomSolverOptions | dict[str, Any],
    source_operator: str = "",
):
    convention_value = opts.dephasing_coupling if isinstance(opts, HeomSolverOptions) else opts.get("dephasing_coupling", "auto")
    convention = str(convention_value).strip().lower()
    if convention == "auto" and source_operator:
        convention = str(source_operator).strip().lower()
    model_type = str(setup.model_type).strip().lower()
    if convention in {"sigma_z_over_2", "0.5*sigma_z", "half_sigma_z"}:
        return 0.5 * system.z_ops[target], 0.5, "0.5*sigma_z", "config"
    if convention in {"sigma_z", "bare_sigma_z"}:
        return system.z_ops[target], 1.0, "sigma_z", "config"
    if convention in {"number", "number_operator", "n"}:
        return system.z_ops[target], 1.0, "number_operator", "config"
    if convention != "auto":
        raise ValueError(
            "Unsupported HEOM dephasing_coupling. "
            "Use auto, sigma_z_over_2, sigma_z, or number_operator."
        )
    if model_type == "qubit_network":
        return 0.5 * system.z_ops[target], 0.5, "0.5*sigma_z", "auto"
    return system.z_ops[target], 1.0, "number_operator", "auto"


def _shared_dephasing_coupling_operator(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    targets: list[int],
    opts: HeomSolverOptions | dict[str, Any],
    source_operator: str = "",
):
    terms = []
    coupling_scale = 0.0
    coupling_operator = ""
    coupling_source = ""
    for target in targets:
        op, scale, op_label, source = _dephasing_coupling_operator(
            setup=setup,
            system=system,
            target=target,
            opts=opts,
            source_operator=source_operator,
        )
        terms.append(op)
        coupling_scale = scale
        coupling_operator = op_label
        coupling_source = source
    if not terms:
        raise ValueError("HEOM dephasing coupling requires at least one target.")
    total = terms[0]
    for op in terms[1:]:
        total = total + op
    return total, coupling_scale, coupling_operator, coupling_source


def _estimate_ado_count(*, num_exponents: int, max_depth: int) -> int:
    return comb(int(num_exponents) + int(max_depth), int(max_depth))


def _hilbert_dim(system: QutipSystem) -> int:
    h0 = system.H[0] if isinstance(system.H, list) and system.H else system.H
    shape = getattr(h0, "shape", None)
    if shape and len(shape) >= 1:
        return int(shape[0])
    return 0


def _summary_num_exponents(item: dict[str, Any] | HeomBathSummary) -> int:
    return int(item.num_exponents if isinstance(item, HeomBathSummary) else item.get("num_exponents", 0))


def _check_heom_size(*, summaries: list[dict[str, Any] | HeomBathSummary], max_depth: int, opts: HeomSolverOptions | dict[str, Any], system: QutipSystem) -> dict[str, int | float]:
    total_exponents = int(sum(_summary_num_exponents(item) for item in summaries))
    estimated_ados = int(_estimate_ado_count(num_exponents=total_exponents, max_depth=max_depth))
    hilbert_dim = _hilbert_dim(system)
    liouville_dim = int(hilbert_dim * hilbert_dim) if hilbert_dim > 0 else 0
    estimated_complex_variables = int(estimated_ados * liouville_dim)
    estimated_dense_memory_mb = float(estimated_complex_variables * 16.0 / (1024.0**2))
    max_ados = int(opts.max_ados if isinstance(opts, HeomSolverOptions) else opts.get("max_ados", 5000) or 0)
    max_dense_memory_mb = float(
        opts.max_dense_memory_mb if isinstance(opts, HeomSolverOptions) else opts.get("max_dense_memory_mb", 0.0) or 0.0
    )
    if max_ados > 0 and estimated_ados > max_ados:
        raise ValueError(
            "HEOM hierarchy is too large: "
            f"estimated_ados={estimated_ados}, max_ados={max_ados}, "
            f"num_exponents={total_exponents}, max_depth={max_depth}. "
            "Increase backend_options.heom.max_ados or reduce nterms/max_depth."
        )
    if max_dense_memory_mb > 0.0 and estimated_dense_memory_mb > max_dense_memory_mb:
        raise ValueError(
            "HEOM estimated dense state is too large: "
            f"estimated_dense_memory_MB={estimated_dense_memory_mb:.3g}, "
            f"max_dense_memory_MB={max_dense_memory_mb:.3g}, "
            f"estimated_ados={estimated_ados}, liouville_dim={liouville_dim}. "
            "Increase backend_options.heom.max_dense_memory_mb or reduce nterms/max_depth/system size."
        )
    return {
        "num_exponents": total_exponents,
        "estimated_ados": estimated_ados,
        "max_ados": max_ados,
        "hilbert_dim": hilbert_dim,
        "liouville_dim": liouville_dim,
        "estimated_complex_variables": estimated_complex_variables,
        "estimated_dense_memory_MB": estimated_dense_memory_mb,
        "max_dense_memory_MB": max_dense_memory_mb,
    }


def _channel_noise_model(item: Any, selected_noise: str) -> str:
    for name in ("kind", "model", "noise_model"):
        value = getattr(item, name, None)
        if value:
            return str(value).strip().lower()
    if isinstance(item, dict):
        for name in ("kind", "model", "noise_model"):
            value = item.get(name)
            if value:
                return str(value).strip().lower()
    return selected_noise


def build_heom_baths(*, setup: QutipPlan, system: QutipSystem):
    """Build HEOM baths for classical colored dephasing approximations."""
    try:
        from qutip.solver.heom import BosonicBath
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM support unavailable: {exc}") from exc

    opts = _typed_heom_options(setup)
    baths = []
    summaries: list[HeomBathSummary] = []
    selected_noise = str(setup.model_spec.noise.selected_model or "").strip().lower()
    for item in setup.model_spec.noise.stochastic_channels:
        targets = [int(target) for target in list(getattr(item, "targets", []) or [int(item.q)])]
        targets = [target for target in targets if 0 <= target < setup.n_qubits]
        if not targets:
            continue
        channel_noise = _channel_noise_model(item, selected_noise)
        if channel_noise in {"one_over_f", "1/f", "pink"}:
            expansion = opts.expansion_for("one_over_f")
            if expansion.method not in {"multi_lorentzian", "log_bin", "heuristic_log_bin"}:
                raise ValueError(f"Unsupported one_over_f HEOM bath expansion method: {expansion.method}")
            if expansion.grid != "log":
                raise ValueError(f"Unsupported one_over_f HEOM bath expansion grid: {expansion.grid}")
            ck_real, vk_real = _one_over_f_exponents(
                amp=float(item.one_over_f_amp_rad_s),
                fmin=float(item.one_over_f_fmin),
                fmax=float(item.one_over_f_fmax or 0.5 / max(setup.dt, 1e-12)),
                exponent=float(item.one_over_f_exponent),
                nterms=int(expansion.nterms),
                t_end=float(setup.tlist[-1]) if setup.tlist.size else setup.dt,
            )
            label = "one_over_f"
        elif channel_noise == "ou":
            expansion = opts.expansion_for("ou")
            if expansion.method not in {"direct_exponential", "multi_lorentzian"}:
                raise ValueError(f"Unsupported OU HEOM bath expansion method: {expansion.method}")
            tau = max(1e-12, float(item.ou_tau))
            ck_real = [float(item.ou_sigma_rad_s) ** 2]
            vk_real = [1.0 / tau]
            label = "ou"
        else:
            continue
        if not ck_real:
            continue
        coupling_op, coupling_scale, coupling_operator, coupling_source = _shared_dephasing_coupling_operator(
            setup=setup,
            system=system,
            targets=targets,
            opts=opts,
            source_operator=str(getattr(item, "operator", "") or ""),
        )
        tag_targets = "_".join(str(target) for target in targets)
        baths.append(
            BosonicBath(
                coupling_op,
                ck_real=ck_real,
                vk_real=vk_real,
                ck_imag=[],
                vk_imag=[],
                tag=f"{label}_q{tag_targets}",
            )
        )
        summaries.append(
            HeomBathSummary(
                target=targets[0],
                targets=targets,
                source_id=str(getattr(item, "id", "") or ""),
                model=label,
                interpretation="classical colored dephasing approximation via real bath correlation",
                coupling_operator=coupling_operator,
                coupling_scale=coupling_scale,
                coupling_convention_source=coupling_source,
                units=dict(HEOM_UNITS),
                expansion_method=str(expansion.method),
                expansion_grid=str(expansion.grid),
                num_exponents=len(ck_real),
                sum_ck_real=sum(ck_real),
                max_ck_real=max(ck_real),
                min_vk_real=min(vk_real),
                max_vk_real=max(vk_real),
            )
        )
    if not baths:
        raise ValueError("HEOM mode requires at least one stochastic one_over_f or OU channel.")
    return (baths[0] if len(baths) == 1 else baths), summaries


def _heom_system_generator(*, setup: QutipPlan, system: QutipSystem, solver_inputs: QutipSolverInputs):
    hamiltonian = setup.qt.QobjEvo(system.H)
    c_ops = list(solver_inputs.c_ops or [])
    if c_ops:
        return setup.qt.liouvillian(hamiltonian, c_ops), True
    return hamiltonian, False


def run_heom(
    *,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
    e_ops,
):
    """Run ``qutip.solver.heom.HEOMSolver`` for non-Markovian dephasing."""
    try:
        from qutip.solver.heom import HEOMSolver
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM support unavailable: {exc}") from exc

    opts = _typed_heom_options(setup)
    max_depth = int(opts.max_depth)
    bath, summaries = build_heom_baths(setup=setup, system=system)
    size = _check_heom_size(summaries=summaries, max_depth=max_depth, opts=opts, system=system)
    generator, uses_liouvillian = _heom_system_generator(setup=setup, system=system, solver_inputs=solver_inputs)
    solver = HEOMSolver(generator, bath, max_depth=max_depth, options=trajectory_cfg.options)
    state0 = setup.qt.ket2dm(system.psi0) if getattr(system.psi0, "isket", False) else system.psi0
    result = solver.run(state0, setup.tlist, e_ops=e_ops)
    return result, summaries, size, uses_liouvillian


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
        result, bath_summaries, size, uses_liouvillian = run_heom(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
            e_ops=base_e_ops,
        )
    except Exception as exc:
        raise RuntimeError(f"QuTiP HEOM execution failed: {exc}") from exc
    opts = _typed_heom_options(setup)
    max_depth = int(opts.max_depth)
    trajectory = standard_trajectory_from_result(
        engine,
        setup=setup,
        system=system,
        solver_inputs=solver_inputs,
        trajectory_cfg=trajectory_cfg,
        result=result,
        readout_expect_ix=readout_expect_ix,
    )
    summary = HeomRunSummary(
        options=opts,
        bath_count=len(bath_summaries),
        uses_liouvillian=uses_liouvillian,
        markovian_c_ops=len(solver_inputs.c_ops or []),
        approximation="classical colored dephasing represented by real HEOM bath correlations",
        fit_method="heuristic log-bin OU/Lorentzian component approximation, not least-squares spectral fitting",
        units=dict(HEOM_UNITS),
        size=size,
        baths=bath_summaries,
    )
    trajectory.metadata["heom"] = summary.to_dict()
    return trajectory
