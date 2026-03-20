"""Canonical unit-bearing field names for hardware and noise configs."""

from __future__ import annotations

from typing import Any

PULSE_KEYS = {
    "gate_duration_ns",
    "measure_duration_ns",
    "rect_edge_ns",
    "readout_edge_ns",
    "reset_measure_duration_ns",
    "reset_deplete_duration_ns",
    "reset_latency_duration_ns",
    "reset_pi_duration_ns",
    "reset_measure_amp",
    "reset_deplete_amp",
    "reset_pi_amp",
    "reset_cond_on",
    "reset_apply_feedback",
    "xy_freq_Hz",
    "ro_freq_Hz",
}

LOWERING_HARDWARE_KEYS = PULSE_KEYS | {
    "schedule_policy",
    "reset_feedback_policy",
}

MODEL_HARDWARE_KEYS = LOWERING_HARDWARE_KEYS | {
    "qubits",
    "simulation_level",
    "dimension",
    "control_scale",
    "transmon_levels",
    "cavity_nmax",
    "qubit_freq_Hz",
    "qubit_freqs_Hz",
    "anharmonicity_Hz",
    "cavity_freq_Hz",
    "g_cavity_Hz",
    "couplings",
    "gamma1_Hz",
    "gamma_phi_Hz",
    "gamma_up_Hz",
    "T1_s",
    "T2_s",
    "Tphi_s",
    "Tup_s",
}

COUPLING_KEYS = {"i", "j", "g_Hz", "kind"}

NOISE_KEYS = {
    "model",
    "type",
    "one_over_f",
    "readout_error",
    "gamma1_Hz",
    "gamma1_per_qubit_Hz",
    "gamma_phi_Hz",
    "gamma_phi_per_qubit_Hz",
    "gamma_up_Hz",
    "gamma_up_per_qubit_Hz",
    "T1_s",
    "T1_per_qubit_s",
    "T2_s",
    "T2_per_qubit_s",
    "Tphi_s",
    "Tphi_per_qubit_s",
    "Tup_s",
    "Tup_per_qubit_s",
    "one_over_f_amp_Hz",
    "one_over_f_fmin_Hz",
    "one_over_f_fmax_Hz",
    "one_over_f_exponent",
    "ou_sigma_Hz",
    "ou_tau_s",
}

NS_TO_S = 1e-9


def reject_unknown_keys(section: str, payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Unsupported keys in {section}: {unknown}")


def reject_unknown_coupling_keys(couplings: list[Any]) -> None:
    for idx, coupling in enumerate(couplings):
        if not isinstance(coupling, dict):
            continue
        unknown = sorted(set(coupling) - COUPLING_KEYS)
        if unknown:
            raise ValueError(f"Unsupported keys in device.couplings[{idx}]: {unknown}")
