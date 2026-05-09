"""Noise lowering into engine-neutral ``NoiseSpec``."""

from __future__ import annotations

from typing import Any

from qsim.backend.config import DeviceConfig, NoiseConfig
from qsim.backend.model.common import TWO_PI, expand_value, qubit_field
from qsim.common.schemas import (
    CollapseChannelSpec,
    ControlCrosstalkSpec,
    NoiseSourceSpec,
    NoiseSpec,
    PerQubitRateSpec,
    ReadoutCrosstalkSpec,
    StochasticChannelSpec,
)


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


def _component_target(component_id: str, fallback: int) -> str:
    return str(component_id or f"q{fallback}")


def _target_to_qubit(target: str | int, component_index: dict[str, int], num_qubits: int) -> int | None:
    if isinstance(target, int):
        idx = int(target)
    else:
        token = str(target).strip()
        if token in component_index:
            idx = component_index[token]
        elif token.startswith("q") and token[1:].isdigit():
            idx = int(token[1:])
        elif token.isdigit():
            idx = int(token)
        else:
            return None
    return idx if 0 <= idx < num_qubits else None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in dict(override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _collect_authored_sources(noise: NoiseConfig, hw: DeviceConfig) -> tuple[list[NoiseSourceSpec], list[ControlCrosstalkSpec], list[ReadoutCrosstalkSpec]]:
    sources: list[NoiseSourceSpec] = []
    control_crosstalk = [ControlCrosstalkSpec.from_dict(item) for item in list(hw.control_crosstalk or [])]
    readout_crosstalk = [ReadoutCrosstalkSpec.from_dict(item) for item in list(hw.readout_crosstalk or [])]

    for idx, component in enumerate(hw.components):
        component_noise = dict(component.noise or {})
        for raw_source in list(component_noise.get("sources", []) or []):
            if not isinstance(raw_source, dict):
                continue
            data = dict(raw_source)
            data.setdefault("targets", [_component_target(component.id, idx)])
            sources.append(NoiseSourceSpec.from_dict(data))

    for raw_source in list(hw.shared_noise or []):
        if isinstance(raw_source, dict):
            sources.append(NoiseSourceSpec.from_dict(raw_source))

    for raw_source in list(noise.sources or []):
        if isinstance(raw_source, dict):
            source = NoiseSourceSpec.from_dict(raw_source)
            if not source.id:
                raise ValueError("noise.sources entries require stable id values for task/study authoring.")
            sources.append(source)

    seen_ids: set[str] = set()
    for source in sources:
        if not source.id:
            continue
        if source.id in seen_ids:
            raise ValueError(f"Duplicate noise source id: {source.id}")
        seen_ids.add(source.id)

    if noise.overrides:
        by_id = {item.id: item for item in sources if item.id}
        for source_id, override in dict(noise.overrides).items():
            source = by_id.get(str(source_id))
            if source is None:
                raise ValueError(f"noise.overrides references unknown source id: {source_id}")
            if not isinstance(override, dict):
                continue
            merged = _deep_merge(source.to_dict(), override)
            by_id[str(source_id)] = NoiseSourceSpec.from_dict(merged)
        sources = [by_id.get(item.id, item) if item.id else item for item in sources]

    if noise.enabled_sources:
        enabled = set(noise.enabled_sources)
        unknown = sorted(enabled - seen_ids)
        if unknown:
            raise ValueError(f"noise.enabled_sources references unknown source ids: {unknown}")
        sources = [item for item in sources if not item.id or item.id in enabled]
    if noise.disabled_sources:
        disabled = set(noise.disabled_sources)
        unknown = sorted(disabled - seen_ids)
        if unknown:
            raise ValueError(f"noise.disabled_sources references unknown source ids: {unknown}")
        sources = [item for item in sources if not item.id or item.id not in disabled]
    return sources, control_crosstalk, readout_crosstalk


def _source_targets(source: NoiseSourceSpec, component_index: dict[str, int], num_qubits: int) -> list[int]:
    targets = [_target_to_qubit(target, component_index, num_qubits) for target in source.targets]
    resolved = [int(target) for target in targets if target is not None]
    return resolved


def _source_rate_Hz(source: NoiseSourceSpec, key: str) -> float:
    rate = dict(source.rate or {})
    value = rate.get(key)
    if value is None:
        return 0.0
    return max(0.0, float(value))


def _source_T_rate_Hz(source: NoiseSourceSpec, t_key: str, gamma_key: str) -> float:
    gamma = _source_rate_Hz(source, gamma_key)
    if gamma > 0.0:
        return gamma
    rate = dict(source.rate or {})
    T = float(rate.get(t_key, 0.0) or 0.0)
    return 1.0 / T if T > 0.0 else 0.0


def _append_source_realizations(
    *,
    sources: list[NoiseSourceSpec],
    component_index: dict[str, int],
    num_qubits: int,
    collapse_ops: list[CollapseChannelSpec],
    stochastic_noise: list[StochasticChannelSpec],
) -> None:
    for source in sources:
        kind = str(source.kind or "").strip().lower()
        targets = _source_targets(source, component_index, num_qubits)
        if not targets:
            continue
        operator = str(source.operator or "").strip().lower()
        if kind == "markovian":
            if operator in {"lowering", "sigma_minus", "relaxation"}:
                rate_Hz = _source_T_rate_Hz(source, "T1_s", "gamma1_Hz")
                channel_kind = "relaxation"
            elif operator in {"raising", "sigma_plus", "excitation"}:
                rate_Hz = _source_T_rate_Hz(source, "Tup_s", "gamma_up_Hz")
                channel_kind = "excitation"
            elif operator in {"sigma_z", "sigma_z_over_2", "number", "dephasing"}:
                rate_Hz = _source_T_rate_Hz(source, "Tphi_s", "gamma_phi_Hz")
                channel_kind = "dephasing"
            else:
                continue
            if rate_Hz <= 0.0:
                continue
            for target in targets:
                collapse_ops.append(
                    CollapseChannelSpec(
                        target=target,
                        kind=channel_kind,
                        rate_Hz=rate_Hz,
                        rate_rad_s=TWO_PI * rate_Hz,
                    )
                )
        elif kind in {"one_over_f", "1/f", "pink"}:
            amplitude = dict(source.amplitude or {})
            band = list(source.band_Hz or [])
            rms_Hz = float(amplitude.get("rms_Hz", amplitude.get("amp_Hz", 0.0)) or 0.0)
            fmin = float(band[0]) if len(band) >= 1 else 0.0
            fmax = float(band[1]) if len(band) >= 2 else 0.0
            stochastic_noise.append(
                StochasticChannelSpec(
                    q=targets[0],
                    id=source.id,
                    kind="one_over_f",
                    targets=targets,
                    operator=source.operator or "sigma_z_over_2",
                    correlation=dict(source.correlation or {}),
                    one_over_f_amp_Hz=rms_Hz,
                    one_over_f_amp_rad_s=TWO_PI * rms_Hz,
                    one_over_f_fmin=fmin,
                    one_over_f_fmax=fmax,
                    one_over_f_exponent=1.0 if source.exponent is None else float(source.exponent),
                )
            )
        elif kind in {"ou", "ornstein_uhlenbeck"}:
            amplitude = dict(source.amplitude or {})
            spectrum = dict(source.spectrum or {})
            sigma_Hz = float(amplitude.get("sigma_Hz", amplitude.get("rms_Hz", 0.0)) or 0.0)
            tau_s = float(amplitude.get("tau_s", spectrum.get("tau_s", 1.0)) or 1.0)
            stochastic_noise.append(
                StochasticChannelSpec(
                    q=targets[0],
                    id=source.id,
                    kind="ou",
                    targets=targets,
                    operator=source.operator or "sigma_z_over_2",
                    correlation=dict(source.correlation or {}),
                    ou_sigma_Hz=sigma_Hz,
                    ou_sigma_rad_s=TWO_PI * sigma_Hz,
                    ou_tau=max(1e-9, tau_s),
                )
            )


def _stochastic_channel_is_active(item: StochasticChannelSpec, selected_model: str) -> bool:
    kind = str(item.kind or selected_model or "").strip().lower()
    if kind in {"one_over_f", "1/f", "pink"}:
        return float(item.one_over_f_amp_rad_s) > 0.0
    if kind == "ou":
        return float(item.ou_sigma_rad_s) > 0.0
    return bool(item.id)


def lower_noise(
    noise: NoiseConfig,
    hw: DeviceConfig,
    raw_qubits: list[dict[str, Any]],
    num_qubits: int,
    dt_s: float,
) -> NoiseSpec:
    """Lower normalized noise/device config to collapse and stochastic channels."""
    component_index = {f"q{idx}": idx for idx in range(num_qubits)}
    for idx, component in enumerate(hw.components[:num_qubits]):
        if component.id:
            component_index[str(component.id)] = idx
    authored_sources, control_crosstalk, readout_crosstalk = _collect_authored_sources(noise, hw)
    legacy_sources: list[NoiseSourceSpec] = []

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
            legacy_sources.append(
                NoiseSourceSpec(
                    id=f"q{q}_legacy_T1",
                    kind="markovian",
                    targets=[f"q{q}"],
                    operator="lowering",
                    rate={"gamma1_Hz": g1},
                    metadata={"source": "legacy_local_rate"},
                )
            )
        if gphi > 0:
            collapse_ops.append(CollapseChannelSpec(target=q, kind="dephasing", rate_Hz=gphi, rate_rad_s=TWO_PI * gphi))
            legacy_sources.append(
                NoiseSourceSpec(
                    id=f"q{q}_legacy_Tphi",
                    kind="markovian",
                    targets=[f"q{q}"],
                    operator="sigma_z_over_2",
                    rate={"gamma_phi_Hz": gphi},
                    metadata={"source": "legacy_local_rate", "Tphi_s_convention": "physical_off_diagonal_coherence_time"},
                )
            )
        if gup > 0:
            collapse_ops.append(CollapseChannelSpec(target=q, kind="excitation", rate_Hz=gup, rate_rad_s=TWO_PI * gup))
            legacy_sources.append(
                NoiseSourceSpec(
                    id=f"q{q}_legacy_Tup",
                    kind="markovian",
                    targets=[f"q{q}"],
                    operator="raising",
                    rate={"gamma_up_Hz": gup},
                    metadata={"source": "legacy_local_rate"},
                )
            )
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
    selected_model = _noise_model(noise)
    if selected_model in {"one_over_f", "1/f", "pink"}:
        for q, amp_Hz in enumerate(of_amp):
            if float(amp_Hz) <= 0.0:
                continue
            legacy_sources.append(
                NoiseSourceSpec(
                    id=f"q{q}_legacy_1overf",
                    kind="one_over_f",
                    targets=[f"q{q}"],
                    operator="sigma_z_over_2",
                    amplitude={"rms_Hz": float(amp_Hz), "definition": "integrated_rms_over_band"},
                    band_Hz=[float(of_fmin[q]), float(of_fmax[q])],
                    exponent=float(of_exp[q]),
                    psd_convention="one_sided",
                    metadata={"source": "legacy_stochastic_channel"},
                )
            )
    elif selected_model == "ou":
        for q, sigma_Hz in enumerate(ou_sigma):
            if float(sigma_Hz) <= 0.0:
                continue
            legacy_sources.append(
                NoiseSourceSpec(
                    id=f"q{q}_legacy_ou",
                    kind="ou",
                    targets=[f"q{q}"],
                    operator="sigma_z_over_2",
                    amplitude={"sigma_Hz": float(sigma_Hz), "tau_s": float(ou_tau[q])},
                    metadata={"source": "legacy_stochastic_channel"},
                )
            )

    _append_source_realizations(
        sources=authored_sources,
        component_index=component_index,
        num_qubits=num_qubits,
        collapse_ops=collapse_ops,
        stochastic_noise=stochastic_noise,
    )
    stochastic_kinds = {str(item.kind or "").lower() for item in stochastic_noise if str(item.kind or "").strip()}
    if selected_model not in {"one_over_f", "ou"} and stochastic_kinds:
        selected_model = sorted(stochastic_kinds)[0] if len(stochastic_kinds) == 1 else "source_ir"
    active_stochastic = [item for item in stochastic_noise if _stochastic_channel_is_active(item, selected_model)]
    realizations: list[dict[str, Any]] = []
    if collapse_ops:
        realizations.append({"kind": "lindblad_collapse_channels", "channels": [item.to_dict() for item in collapse_ops]})
    if active_stochastic:
        realizations.append({"kind": "stochastic_channels", "channels": [item.to_dict() for item in active_stochastic]})
    if control_crosstalk:
        realizations.append(
            {"kind": "control_crosstalk_transfers", "transfers": [item.to_dict() for item in control_crosstalk]}
        )
    if readout_crosstalk:
        realizations.append({"kind": "readout_crosstalk", "channels": [item.to_dict() for item in readout_crosstalk]})

    return NoiseSpec(
        selected_model=selected_model,
        readout_error=float(noise.get("readout_error", 0.0) or 0.0),
        sources=[*authored_sources, *legacy_sources],
        realizations=realizations,
        control_crosstalk=control_crosstalk,
        readout_crosstalk=readout_crosstalk,
        collapse_channels=collapse_ops,
        stochastic_channels=stochastic_noise,
        per_qubit_rates=per_qubit_rates,
        supported=["relaxation", "dephasing", "excitation", "one_over_f", "ou"],
        unsupported=["non_markovian_memory_kernel"],
        warnings=[],
    )
