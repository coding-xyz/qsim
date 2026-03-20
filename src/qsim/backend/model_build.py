"""Executable-model to solver-model conversion utilities."""

from __future__ import annotations

import math
import re
from typing import Any
from typing import Protocol

from qsim.common.unit_schema import (
    MODEL_HARDWARE_KEYS,
    NOISE_KEYS,
    NS_TO_S,
    reject_unknown_coupling_keys,
    reject_unknown_keys,
)
from qsim.common.schemas import ExecutableModel, ModelSpec


class IModelBuilder(Protocol):
    """Protocol for building executable model spec from lowered artifacts."""

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
        frame: dict[str, Any] | None = None,
        solver_run: dict[str, Any] | None = None,
    ) -> ModelSpec:
        ...


class DefaultModelBuilder:
    """Build ``ModelSpec`` from executable metadata, hardware, and noise config."""

    _XY_RE = re.compile(r"^XY_(\d+)$", re.IGNORECASE)
    _Z_RE = re.compile(r"^Z_(\d+)$", re.IGNORECASE)
    _RO_RE = re.compile(r"^RO_(\d+)$", re.IGNORECASE)
    _TWO_PI = 2.0 * math.pi

    @staticmethod
    def _to_float_list(arr: Any) -> list[float]:
        return [float(x) for x in arr.tolist()] if hasattr(arr, "tolist") else [float(x) for x in arr]

    @staticmethod
    def _expand_noise_value(raw: Any, num_qubits: int, default: float = 0.0) -> list[float]:
        if raw is None:
            return [float(default) for _ in range(num_qubits)]
        if isinstance(raw, (list, tuple)):
            vals = [float(x) for x in raw]
            if len(vals) < num_qubits:
                vals.extend([float(default)] * (num_qubits - len(vals)))
            return vals[:num_qubits]
        return [float(raw) for _ in range(num_qubits)]

    @staticmethod
    def _expand_value(raw: Any, num: int, default: float = 0.0) -> list[float]:
        if raw is None:
            return [float(default) for _ in range(num)]
        if isinstance(raw, (list, tuple)):
            vals = [float(x) for x in raw]
            if len(vals) < num:
                vals.extend([float(default)] * (num - len(vals)))
            return vals[:num]
        return [float(raw) for _ in range(num)]

    @staticmethod
    def _qubit_field(qubits: list[Any], key: str, default: float = 0.0) -> list[float]:
        return [float((q or {}).get(key, default)) for q in qubits]

    @staticmethod
    def _normalize_frame(frame: dict[str, Any] | None, num_qubits: int) -> tuple[str, str, bool, list[float]]:
        frame = frame or {}
        mode = str(frame.get("mode", "rotating")).strip().lower()
        if mode not in {"rotating", "lab"}:
            mode = "rotating"
        reference = str(frame.get("reference", "pulse_carrier")).strip().lower()
        if reference not in {"pulse_carrier", "explicit", "none"}:
            reference = "pulse_carrier"
        rwa = bool(frame.get("rwa", True))
        explicit_refs = DefaultModelBuilder._expand_value(frame.get("qubit_reference_freqs_Hz"), num_qubits, 0.0)
        return mode, reference, rwa, explicit_refs

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
        frame: dict[str, Any] | None = None,
        solver_run: dict[str, Any] | None = None,
    ) -> ModelSpec:
        """Construct normalized ``ModelSpec`` consumed by simulation engines."""
        hw = hw or {}
        noise = noise or {}
        pulse_samples = pulse_samples or {}
        solver_run = dict(solver_run or {})
        reject_unknown_keys("device", hw, MODEL_HARDWARE_KEYS)
        reject_unknown_keys("noise", noise, NOISE_KEYS)
        reject_unknown_keys("solver.run", solver_run, {"dt_s", "t_end_s", "t_padding_s"})
        reject_unknown_coupling_keys(list(hw.get("couplings", [])))

        num_qubits = int(max(1, executable.metadata.get("num_qubits", 1)))
        frame_mode, frame_reference, frame_rwa, explicit_reference_freqs_Hz = self._normalize_frame(frame, num_qubits)
        raw_qubits = list(hw.get("qubits", []) or [])
        inferred_t_end_s = float(executable.metadata.get("t_end_s", 0.0))
        inferred_dt_s = 1.0 * NS_TO_S

        for ch_payload in pulse_samples.values():
            times = ch_payload.get("t")
            if times is None:
                continue
            t_list = self._to_float_list(times)
            if not t_list:
                continue
            inferred_t_end_s = max(inferred_t_end_s, t_list[-1])
            if len(t_list) > 1:
                inferred_dt_s = min(inferred_dt_s, max(1e-15, t_list[1] - t_list[0]))

        if inferred_t_end_s <= 0.0:
            inferred_t_end_s = 1000.0 * NS_TO_S

        dt_raw = solver_run.get("dt_s")
        dt = inferred_dt_s if dt_raw is None else float(dt_raw)
        t_padding_raw = solver_run.get("t_padding_s")
        t_padding_s = max(0.0, 0.0 if t_padding_raw is None else float(t_padding_raw))
        t_end_raw = solver_run.get("t_end_s")
        t_end = (inferred_t_end_s + t_padding_s) if t_end_raw is None else float(t_end_raw)
        trunc = dict(executable.metadata.get("truncation", {}))
        transmon_levels = int(hw.get("transmon_levels", trunc.get("transmon_levels", 2)))
        cavity_nmax = int(hw.get("cavity_nmax", trunc.get("cavity_nmax", 0)))
        req_level = str(hw.get("simulation_level", executable.level)).strip().lower()
        if req_level not in {"qubit", "nlevel", "cqed"}:
            req_level = "qubit"
        if req_level == "nlevel" and transmon_levels <= 2:
            req_level = "qubit"
        if req_level == "cqed" and cavity_nmax <= 0:
            req_level = "nlevel" if transmon_levels > 2 else "qubit"

        if req_level == "qubit":
            dim = int(hw.get("dimension", 2**num_qubits))
        elif req_level == "nlevel":
            dim = int(hw.get("dimension", transmon_levels**num_qubits))
        else:
            dim = int(hw.get("dimension", (cavity_nmax + 1) * (transmon_levels**num_qubits)))

        controls: list[dict[str, Any]] = []
        pulse_carrier_reference_freqs_Hz = [0.0 for _ in range(num_qubits)]
        for ch_name, ch_payload in pulse_samples.items():
            times = self._to_float_list(ch_payload.get("t", []))
            values = self._to_float_list(ch_payload.get("y", []))
            if not times or not values:
                continue
            carrier_freq_Hz = float(self._to_float_list(ch_payload.get("carrier_freq_Hz", [0.0]))[0])
            carrier_phase_rad = float(self._to_float_list(ch_payload.get("carrier_phase_rad", [0.0]))[0])

            axis = None
            target = None
            mxy = self._XY_RE.match(ch_name)
            mz = self._Z_RE.match(ch_name)
            mro = self._RO_RE.match(ch_name)
            if mxy:
                target = int(mxy.group(1))
                axis = "x"
            elif mz:
                target = int(mz.group(1))
                axis = "z"
            elif mro:
                # Readout channels are not part of Hamiltonian control terms.
                continue

            if axis is None or target is None or target >= num_qubits:
                continue
            if axis == "x" and carrier_freq_Hz != 0.0 and pulse_carrier_reference_freqs_Hz[target] == 0.0:
                pulse_carrier_reference_freqs_Hz[target] = carrier_freq_Hz

            controls.append(
                {
                    "channel": ch_name,
                    "target": target,
                    "axis": axis,
                    "times": times,
                    "values": values,
                    "scale": float(hw.get("control_scale", 1.0)),
                    "carrier_freq_Hz": carrier_freq_Hz,
                    "carrier_omega_rad_s": self._TWO_PI * carrier_freq_Hz,
                    "carrier_phase_rad": carrier_phase_rad,
                }
            )

        default_w = float(hw.get("qubit_freq_Hz", 0.0))
        raw_w = hw.get("qubit_freqs_Hz")
        if raw_w is None and raw_qubits:
            raw_w = self._qubit_field(raw_qubits, "freq_Hz", default_w)
        raw_w = raw_w if raw_w is not None else [default_w for _ in range(num_qubits)]
        lab_frame_qubit_freqs = [float(x) for x in raw_w][:num_qubits]
        if len(lab_frame_qubit_freqs) < num_qubits:
            lab_frame_qubit_freqs.extend([default_w] * (num_qubits - len(lab_frame_qubit_freqs)))
        if frame_mode == "lab" or frame_reference == "none":
            reference_freqs_Hz = [0.0 for _ in range(num_qubits)]
        elif frame_reference == "explicit":
            reference_freqs_Hz = [float(x) for x in explicit_reference_freqs_Hz]
        else:
            reference_freqs_Hz = [float(x) for x in pulse_carrier_reference_freqs_Hz]

        for ctrl in controls:
            target = int(ctrl["target"])
            ref = float(reference_freqs_Hz[target]) if 0 <= target < num_qubits else 0.0
            ctrl["reference_freq_Hz"] = ref
            ctrl["reference_omega_rad_s"] = self._TWO_PI * ref
            ctrl["drive_detuning_Hz"] = float(ctrl.get("carrier_freq_Hz", 0.0)) - ref
            ctrl["drive_delta_rad_s"] = self._TWO_PI * float(ctrl["drive_detuning_Hz"])

        qubit_freqs = [
            float(lab_frame_qubit_freqs[q]) - float(reference_freqs_Hz[q]) for q in range(num_qubits)
        ]
        qubit_omega_rad_s = [self._TWO_PI * float(x) for x in qubit_freqs]
        lab_frame_qubit_omega_rad_s = [self._TWO_PI * float(x) for x in lab_frame_qubit_freqs]
        reference_omega_rad_s = [self._TWO_PI * float(x) for x in reference_freqs_Hz]
        pulse_carrier_reference_omega_rad_s = [self._TWO_PI * float(x) for x in pulse_carrier_reference_freqs_Hz]

        couplings = []
        for c in hw.get("couplings", []):
            if not isinstance(c, dict):
                continue
            i, j = int(c.get("i", 0)), int(c.get("j", 0))
            if i == j or i < 0 or j < 0 or i >= num_qubits or j >= num_qubits:
                continue
            couplings.append(
                {
                    "i": i,
                    "j": j,
                    "g_Hz": float(c.get("g_Hz", 0.0)),
                    "g_rad_s": self._TWO_PI * float(c.get("g_Hz", 0.0)),
                    "kind": str(c.get("kind", "xx+yy")),
                }
            )

        # Supported local noise channels:
        # - energy relaxation (T1 / gamma1)
        # - pure dephasing (Tphi / gamma_phi)
        # - thermal excitation (Tup / gamma_up)
        # 1/f and colored spectra are not implemented in this minimal model.
        qubit_gamma1 = self._qubit_field(raw_qubits, "gamma1_Hz", 0.0) if raw_qubits else None
        qubit_gamma_phi = self._qubit_field(raw_qubits, "gamma_phi_Hz", 0.0) if raw_qubits else None
        qubit_gamma_up = self._qubit_field(raw_qubits, "gamma_up_Hz", 0.0) if raw_qubits else None
        qubit_T1 = self._qubit_field(raw_qubits, "T1_s", 0.0) if raw_qubits else None
        qubit_T2 = self._qubit_field(raw_qubits, "T2_s", 0.0) if raw_qubits else None
        qubit_Tphi = self._qubit_field(raw_qubits, "Tphi_s", 0.0) if raw_qubits else None
        qubit_Tup = self._qubit_field(raw_qubits, "Tup_s", 0.0) if raw_qubits else None

        gamma1_raw = noise.get("gamma1_per_qubit_Hz", noise.get("gamma1_Hz", hw.get("gamma1_Hz", qubit_gamma1 or 0.0)))
        gamma_phi_raw = noise.get("gamma_phi_per_qubit_Hz", noise.get("gamma_phi_Hz", hw.get("gamma_phi_Hz", qubit_gamma_phi or 0.0)))
        gamma_up_raw = noise.get("gamma_up_per_qubit_Hz", noise.get("gamma_up_Hz", hw.get("gamma_up_Hz", qubit_gamma_up or 0.0)))
        T1_raw = noise.get("T1_per_qubit_s", noise.get("T1_s", hw.get("T1_s", qubit_T1)))
        T2_raw = noise.get("T2_per_qubit_s", noise.get("T2_s", hw.get("T2_s", qubit_T2)))
        Tphi_raw = noise.get("Tphi_per_qubit_s", noise.get("Tphi_s", hw.get("Tphi_s", qubit_Tphi)))
        Tup_raw = noise.get("Tup_per_qubit_s", noise.get("Tup_s", hw.get("Tup_s", qubit_Tup)))

        gamma1_cfg = self._expand_noise_value(gamma1_raw, num_qubits, 0.0)
        gamma_phi_cfg = self._expand_noise_value(gamma_phi_raw, num_qubits, 0.0)
        gamma_up_cfg = self._expand_noise_value(gamma_up_raw, num_qubits, 0.0)
        T1_cfg = self._expand_noise_value(T1_raw, num_qubits, 0.0)
        T2_cfg = self._expand_noise_value(T2_raw, num_qubits, 0.0)
        Tphi_cfg = self._expand_noise_value(Tphi_raw, num_qubits, 0.0)
        Tup_cfg = self._expand_noise_value(Tup_raw, num_qubits, 0.0)

        per_qubit_rates: list[dict[str, float]] = []
        collapse_ops = []
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
                    # Approximation: 1/T2 = (gamma1 + gamma_up)/2 + gamma_phi
                    gphi = max(0.0, (1.0 / T2) - 0.5 * (g1 + gup))

            if g1 > 0:
                collapse_ops.append({"target": q, "kind": "relaxation", "rate_Hz": g1, "rate_rad_s": self._TWO_PI * g1})
            if gphi > 0:
                collapse_ops.append({"target": q, "kind": "dephasing", "rate_Hz": gphi, "rate_rad_s": self._TWO_PI * gphi})
            if gup > 0:
                collapse_ops.append({"target": q, "kind": "excitation", "rate_Hz": gup, "rate_rad_s": self._TWO_PI * gup})

            per_qubit_rates.append(
                {
                    "q": q,
                    "gamma1_Hz": g1,
                    "gamma_phi_Hz": gphi,
                    "gamma_up_Hz": gup,
                    "gamma1_rad_s": self._TWO_PI * g1,
                    "gamma_phi_rad_s": self._TWO_PI * gphi,
                    "gamma_up_rad_s": self._TWO_PI * gup,
                }
            )

        noise_warnings: list[str] = []
        noise_kind = str(noise.get("model", noise.get("type", ""))).strip().lower()
        noise_model = noise_kind if noise_kind else "markovian_lindblad"
        if noise.get("one_over_f", False):
            noise_model = "one_over_f"

        # Stochastic dephasing parameters (for engine-side effective noise trajectories).
        of_amp = self._expand_value(noise.get("one_over_f_amp_Hz", 0.0), num_qubits, 0.0)
        of_fmin = self._expand_value(noise.get("one_over_f_fmin_Hz", 1e-3), num_qubits, 1e-3)
        of_fmax = self._expand_value(
            noise.get("one_over_f_fmax_Hz", 0.5 / max(dt, 1e-12)),
            num_qubits,
            0.5 / max(dt, 1e-12),
        )
        of_exp = self._expand_value(noise.get("one_over_f_exponent", 1.0), num_qubits, 1.0)
        ou_sigma = self._expand_value(noise.get("ou_sigma_Hz", 0.0), num_qubits, 0.0)
        ou_tau = self._expand_value(noise.get("ou_tau_s", 1.0), num_qubits, 1.0)
        stochastic_noise: list[dict[str, float]] = []
        for q in range(num_qubits):
            stochastic_noise.append(
                {
                    "q": q,
                    "one_over_f_amp_Hz": float(of_amp[q]),
                    "one_over_f_amp_rad_s": self._TWO_PI * float(of_amp[q]),
                    "one_over_f_fmin": float(of_fmin[q]),
                    "one_over_f_fmax": float(of_fmax[q]),
                    "one_over_f_exponent": float(of_exp[q]),
                    "ou_sigma_Hz": float(ou_sigma[q]),
                    "ou_sigma_rad_s": self._TWO_PI * float(ou_sigma[q]),
                    "ou_tau": max(1e-9, float(ou_tau[q])),
                }
            )
        if noise_model in {"1/f", "one_over_f", "pink"}:
            noise_model = "one_over_f"
        elif noise_model in {"ou", "ornstein_uhlenbeck", "lorentzian"}:
            noise_model = "ou"
        else:
            noise_model = "markovian_lindblad"

        model_type = "qubit_network"
        if req_level == "nlevel":
            model_type = "transmon_nlevel"
        elif req_level == "cqed":
            model_type = "cqed_jc"

        anharmonicity_Hz = self._expand_value(
            hw.get("anharmonicity_Hz", self._qubit_field(raw_qubits, "anharmonicity_Hz", -0.2) if raw_qubits else -0.2),
            num_qubits,
            -0.2,
        )
        g_cavity_Hz = self._expand_value(hw.get("g_cavity_Hz", 0.0), num_qubits, 0.0)

        return ModelSpec(
            engine="qutip",
            solver=executable.solver,
            dimension=dim,
            t_end=t_end,
            dt=dt,
            payload={
                "model_type": model_type,
                "simulation_level": req_level,
                "num_qubits": num_qubits,
                "transmon_levels": transmon_levels,
                "cavity_nmax": cavity_nmax,
                "qubit_freqs_Hz": qubit_freqs,
                "qubit_omega_rad_s": qubit_omega_rad_s,
                "lab_frame_qubit_freqs_Hz": lab_frame_qubit_freqs,
                "lab_frame_qubit_omega_rad_s": lab_frame_qubit_omega_rad_s,
                "reference_freqs_Hz": reference_freqs_Hz,
                "reference_omega_rad_s": reference_omega_rad_s,
                "rotating_frame_refs_Hz": reference_freqs_Hz,
                "pulse_carrier_reference_freqs_Hz": pulse_carrier_reference_freqs_Hz,
                "pulse_carrier_reference_omega_rad_s": pulse_carrier_reference_omega_rad_s,
                "frame": {
                    "mode": frame_mode,
                    "reference": frame_reference,
                    "rwa": frame_rwa,
                    "qubit_reference_freqs_Hz": reference_freqs_Hz,
                    "qubit_reference_omega_rad_s": reference_omega_rad_s,
                },
                "anharmonicity_Hz": anharmonicity_Hz,
                "anharmonicity_rad_s": [self._TWO_PI * float(x) for x in anharmonicity_Hz],
                "cavity_freq_Hz": float(hw.get("cavity_freq_Hz", 0.0)),
                "cavity_omega_rad_s": self._TWO_PI * float(hw.get("cavity_freq_Hz", 0.0)),
                "g_cavity_Hz": g_cavity_Hz,
                "g_cavity_rad_s": [self._TWO_PI * float(x) for x in g_cavity_Hz],
                "couplings": couplings,
                "controls": controls,
                "collapse_operators": collapse_ops,
                "noise_summary": {
                    "selected_model": noise_model,
                    "supported": ["relaxation", "dephasing", "excitation", "one_over_f", "ou"],
                    "unsupported": ["non_markovian_memory_kernel"],
                    "per_qubit_rates": per_qubit_rates,
                    "stochastic": stochastic_noise,
                    "warnings": noise_warnings,
                },
                "h_terms": executable.h_terms,
                "noise_terms": executable.noise_terms,
                "reset_events": list(executable.metadata.get("reset_events", [])),
                "noise_cfg": noise,
                "model_assumptions": {
                    "qubit_representation": "two_level_pauli (qubit) or truncated_oscillator (nlevel/cqed)",
                    "subsystem_model": "qubit_network | transmon_nlevel | cqed_jc",
                    "truncation_cfg_from_backend": executable.metadata.get("truncation", {}),
                },
            },
        )
