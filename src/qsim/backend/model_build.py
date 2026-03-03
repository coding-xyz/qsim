"""Executable-model to solver-model conversion utilities."""

from __future__ import annotations

import re
from typing import Any
from typing import Protocol

from qsim.common.schemas import ExecutableModel, ModelSpec


class IModelBuilder(Protocol):
    """Protocol for building executable model spec from lowered artifacts."""

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
    ) -> ModelSpec:
        ...


class DefaultModelBuilder:
    """Build ``ModelSpec`` from executable metadata, hardware, and noise config."""

    _XY_RE = re.compile(r"^XY(\d+)$", re.IGNORECASE)
    _Z_RE = re.compile(r"^Z(\d+)$", re.IGNORECASE)
    _RO_RE = re.compile(r"^RO(\d+)$", re.IGNORECASE)

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

    def build(
        self,
        executable: ExecutableModel,
        hw: dict | None,
        noise: dict | None,
        pulse_samples: dict[str, dict[str, Any]] | None = None,
    ) -> ModelSpec:
        """Construct normalized ``ModelSpec`` consumed by simulation engines."""
        hw = hw or {}
        noise = noise or {}
        pulse_samples = pulse_samples or {}

        num_qubits = int(max(1, executable.metadata.get("num_qubits", 1)))
        inferred_t_end = float(executable.metadata.get("t_end", 1000.0))
        inferred_dt = 1.0

        for ch_payload in pulse_samples.values():
            times = ch_payload.get("t")
            if times is None:
                continue
            t_list = self._to_float_list(times)
            if not t_list:
                continue
            inferred_t_end = max(inferred_t_end, t_list[-1])
            if len(t_list) > 1:
                inferred_dt = min(inferred_dt, max(1e-9, t_list[1] - t_list[0]))

        t_end = float(hw.get("t_end", inferred_t_end))
        dt = float(hw.get("dt", inferred_dt))
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
        for ch_name, ch_payload in pulse_samples.items():
            times = self._to_float_list(ch_payload.get("t", []))
            values = self._to_float_list(ch_payload.get("y", []))
            if not times or not values:
                continue

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

            controls.append(
                {
                    "channel": ch_name,
                    "target": target,
                    "axis": axis,
                    "times": times,
                    "values": values,
                    "scale": float(hw.get("control_scale", 1.0)),
                }
            )

        default_w = float(hw.get("qubit_freq_hz", 0.0))
        raw_w = hw.get("qubit_freqs_hz", [default_w for _ in range(num_qubits)])
        qubit_freqs = [float(x) for x in raw_w][:num_qubits]
        if len(qubit_freqs) < num_qubits:
            qubit_freqs.extend([default_w] * (num_qubits - len(qubit_freqs)))

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
                    "g": float(c.get("g", 0.0)),
                    "kind": str(c.get("kind", "xx+yy")),
                }
            )

        # Supported local noise channels:
        # - energy relaxation (T1 / gamma1)
        # - pure dephasing (Tphi / gamma_phi)
        # - thermal excitation (Tup / gamma_up)
        # 1/f and colored spectra are not implemented in this minimal model.
        gamma1_raw = noise.get("gamma1_per_qubit", noise.get("gamma1", hw.get("gamma1", 0.0)))
        gamma_phi_raw = noise.get("gamma_phi_per_qubit", noise.get("gamma_phi", hw.get("gamma_phi", 0.0)))
        gamma_up_raw = noise.get("gamma_up_per_qubit", noise.get("gamma_up", hw.get("gamma_up", 0.0)))
        t1_raw = noise.get("t1_per_qubit", noise.get("t1", hw.get("t1", None)))
        t2_raw = noise.get("t2_per_qubit", noise.get("t2", hw.get("t2", None)))
        tphi_raw = noise.get("tphi_per_qubit", noise.get("tphi", hw.get("tphi", None)))
        tup_raw = noise.get("tup_per_qubit", noise.get("tup", hw.get("tup", None)))

        gamma1_cfg = self._expand_noise_value(gamma1_raw, num_qubits, 0.0)
        gamma_phi_cfg = self._expand_noise_value(gamma_phi_raw, num_qubits, 0.0)
        gamma_up_cfg = self._expand_noise_value(gamma_up_raw, num_qubits, 0.0)
        t1_cfg = self._expand_noise_value(t1_raw, num_qubits, 0.0)
        t2_cfg = self._expand_noise_value(t2_raw, num_qubits, 0.0)
        tphi_cfg = self._expand_noise_value(tphi_raw, num_qubits, 0.0)
        tup_cfg = self._expand_noise_value(tup_raw, num_qubits, 0.0)

        per_qubit_rates: list[dict[str, float]] = []
        collapse_ops = []
        for q in range(num_qubits):
            g1 = max(0.0, float(gamma1_cfg[q]))
            gphi = max(0.0, float(gamma_phi_cfg[q]))
            gup = max(0.0, float(gamma_up_cfg[q]))
            t1 = float(t1_cfg[q])
            t2 = float(t2_cfg[q])
            tphi = float(tphi_cfg[q])
            tup = float(tup_cfg[q])

            if g1 <= 0.0 and t1 > 0.0:
                g1 = 1.0 / t1
            if gup <= 0.0 and tup > 0.0:
                gup = 1.0 / tup
            if gphi <= 0.0:
                if tphi > 0.0:
                    gphi = 1.0 / tphi
                elif t2 > 0.0:
                    # Approximation: 1/T2 = (gamma1 + gamma_up)/2 + gamma_phi
                    gphi = max(0.0, (1.0 / t2) - 0.5 * (g1 + gup))

            if g1 > 0:
                collapse_ops.append({"target": q, "kind": "relaxation", "rate": g1})
            if gphi > 0:
                collapse_ops.append({"target": q, "kind": "dephasing", "rate": gphi})
            if gup > 0:
                collapse_ops.append({"target": q, "kind": "excitation", "rate": gup})

            per_qubit_rates.append({"q": q, "gamma1": g1, "gamma_phi": gphi, "gamma_up": gup})

        noise_warnings: list[str] = []
        noise_kind = str(noise.get("model", noise.get("type", ""))).strip().lower()
        noise_model = noise_kind if noise_kind else "markovian_lindblad"
        if noise.get("one_over_f", False):
            noise_model = "one_over_f"

        # Stochastic dephasing parameters (for engine-side effective noise trajectories).
        of_amp = self._expand_value(noise.get("one_over_f_amp", 0.0), num_qubits, 0.0)
        of_fmin = self._expand_value(noise.get("one_over_f_fmin", 1e-3), num_qubits, 1e-3)
        of_fmax = self._expand_value(noise.get("one_over_f_fmax", 0.5 / max(dt, 1e-12)), num_qubits, 0.5 / max(dt, 1e-12))
        of_exp = self._expand_value(noise.get("one_over_f_exponent", 1.0), num_qubits, 1.0)
        ou_sigma = self._expand_value(noise.get("ou_sigma", 0.0), num_qubits, 0.0)
        ou_tau = self._expand_value(noise.get("ou_tau", 1.0), num_qubits, 1.0)
        stochastic_noise: list[dict[str, float]] = []
        for q in range(num_qubits):
            stochastic_noise.append(
                {
                    "q": q,
                    "one_over_f_amp": float(of_amp[q]),
                    "one_over_f_fmin": float(of_fmin[q]),
                    "one_over_f_fmax": float(of_fmax[q]),
                    "one_over_f_exponent": float(of_exp[q]),
                    "ou_sigma": float(ou_sigma[q]),
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
                "qubit_freqs_hz": qubit_freqs,
                "anharmonicity_hz": self._expand_value(hw.get("anharmonicity_hz", -0.2), num_qubits, -0.2),
                "cavity_freq_hz": float(hw.get("cavity_freq_hz", 0.0)),
                "g_cavity_hz": self._expand_value(hw.get("g_cavity_hz", 0.0), num_qubits, 0.0),
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
