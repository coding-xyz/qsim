"""Noise lowering into engine-neutral ``NoiseSpec``."""

from __future__ import annotations

from typing import Any

from qsim.backend.config import DeviceConfig, NoiseConfig
from qsim.backend.model.common import TWO_PI, expand_value, qubit_field
from qsim.common.schemas import CollapseChannelSpec, NoiseSpec, PerQubitRateSpec, StochasticChannelSpec


def _local_or_device(noise: NoiseConfig, hw: DeviceConfig, key: str, qubit_default: object) -> object:
    noise_value = getattr(noise.local, key)
    if noise_value is not None:
        return noise_value
    device_value = getattr(hw, key)
    return qubit_default if device_value is None else device_value


def _stochastic_value(noise: NoiseConfig, key: str, default: object) -> object:
    value = getattr(noise.stochastic, key)
    return default if value is None else value


def _noise_model(noise: NoiseConfig) -> str:
    return str(noise.model)


def lower_noise(
    noise: NoiseConfig,
    hw: DeviceConfig,
    raw_qubits: list[dict[str, Any]],
    num_qubits: int,
    dt_s: float,
) -> NoiseSpec:
    """Lower normalized noise/device config to collapse and stochastic channels."""
    qubit_gamma1 = qubit_field(raw_qubits, "gamma1_Hz", 0.0) if raw_qubits else None
    qubit_gamma_phi = qubit_field(raw_qubits, "gamma_phi_Hz", 0.0) if raw_qubits else None
    qubit_gamma_up = qubit_field(raw_qubits, "gamma_up_Hz", 0.0) if raw_qubits else None
    qubit_T1 = qubit_field(raw_qubits, "T1_s", 0.0) if raw_qubits else None
    qubit_T2 = qubit_field(raw_qubits, "T2_s", 0.0) if raw_qubits else None
    qubit_Tphi = qubit_field(raw_qubits, "Tphi_s", 0.0) if raw_qubits else None
    qubit_Tup = qubit_field(raw_qubits, "Tup_s", 0.0) if raw_qubits else None

    gamma1_cfg = expand_value(_local_or_device(noise, hw, "gamma1_Hz", qubit_gamma1 or 0.0), num_qubits, 0.0)
    gamma_phi_cfg = expand_value(_local_or_device(noise, hw, "gamma_phi_Hz", qubit_gamma_phi or 0.0), num_qubits, 0.0)
    gamma_up_cfg = expand_value(_local_or_device(noise, hw, "gamma_up_Hz", qubit_gamma_up or 0.0), num_qubits, 0.0)
    T1_cfg = expand_value(_local_or_device(noise, hw, "T1_s", qubit_T1), num_qubits, 0.0)
    T2_cfg = expand_value(_local_or_device(noise, hw, "T2_s", qubit_T2), num_qubits, 0.0)
    Tphi_cfg = expand_value(_local_or_device(noise, hw, "Tphi_s", qubit_Tphi), num_qubits, 0.0)
    Tup_cfg = expand_value(_local_or_device(noise, hw, "Tup_s", qubit_Tup), num_qubits, 0.0)

    collapse_ops: list[CollapseChannelSpec] = []
    per_qubit_rates: list[PerQubitRateSpec] = []
    for q in range(num_qubits):
        g1 = max(0.0, float(gamma1_cfg[q]))
        gphi = max(0.0, float(gamma_phi_cfg[q]))
        gup = max(0.0, float(gamma_up_cfg[q]))
        T1 = float(T1_cfg[q])
        T2 = float(T2_cfg[q])
        Tphi = float(Tphi_cfg[q])
        Tup = float(Tup_cfg[q])
        if g1 <= 0.0 and T1 > 0.0:
            g1 = 1.0 / T1
        if gup <= 0.0 and Tup > 0.0:
            gup = 1.0 / Tup
        if gphi <= 0.0:
            if Tphi > 0.0:
                gphi = 1.0 / Tphi
            elif T2 > 0.0:
                gphi = max(0.0, (1.0 / T2) - 0.5 * (g1 + gup))

        if g1 > 0:
            collapse_ops.append(CollapseChannelSpec(target=q, kind="relaxation", rate_Hz=g1, rate_rad_s=TWO_PI * g1))
        if gphi > 0:
            collapse_ops.append(CollapseChannelSpec(target=q, kind="dephasing", rate_Hz=gphi, rate_rad_s=TWO_PI * gphi))
        if gup > 0:
            collapse_ops.append(CollapseChannelSpec(target=q, kind="excitation", rate_Hz=gup, rate_rad_s=TWO_PI * gup))
        per_qubit_rates.append(
            PerQubitRateSpec(
                q=q,
                gamma1_Hz=g1,
                gamma_phi_Hz=gphi,
                gamma_up_Hz=gup,
                gamma1_rad_s=TWO_PI * g1,
                gamma_phi_rad_s=TWO_PI * gphi,
                gamma_up_rad_s=TWO_PI * gup,
            )
        )

    of_amp = expand_value(_stochastic_value(noise, "one_over_f_amp_Hz", 0.0), num_qubits, 0.0)
    of_fmin = expand_value(_stochastic_value(noise, "one_over_f_fmin_Hz", 1e-3), num_qubits, 1e-3)
    of_fmax = expand_value(_stochastic_value(noise, "one_over_f_fmax_Hz", 0.5 / max(dt_s, 1e-12)), num_qubits, 0.5 / max(dt_s, 1e-12))
    of_exp = expand_value(_stochastic_value(noise, "one_over_f_exponent", 1.0), num_qubits, 1.0)
    ou_sigma = expand_value(_stochastic_value(noise, "ou_sigma_Hz", 0.0), num_qubits, 0.0)
    ou_tau = expand_value(_stochastic_value(noise, "ou_tau_s", 1.0), num_qubits, 1.0)
    stochastic_noise = [
        StochasticChannelSpec(
            q=q,
            one_over_f_amp_Hz=float(of_amp[q]),
            one_over_f_amp_rad_s=TWO_PI * float(of_amp[q]),
            one_over_f_fmin=float(of_fmin[q]),
            one_over_f_fmax=float(of_fmax[q]),
            one_over_f_exponent=float(of_exp[q]),
            ou_sigma_Hz=float(ou_sigma[q]),
            ou_sigma_rad_s=TWO_PI * float(ou_sigma[q]),
            ou_tau=max(1e-9, float(ou_tau[q])),
        )
        for q in range(num_qubits)
    ]

    return NoiseSpec(
        selected_model=_noise_model(noise),
        readout_error=float(noise.get("readout_error", 0.0) or 0.0),
        collapse_channels=collapse_ops,
        stochastic_channels=stochastic_noise,
        per_qubit_rates=per_qubit_rates,
        supported=["relaxation", "dephasing", "excitation", "one_over_f", "ou"],
        unsupported=["non_markovian_memory_kernel"],
        warnings=[],
    )
