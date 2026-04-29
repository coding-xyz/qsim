"""QuTiP-based dynamics engine implementation."""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from qsim.engines.base import Engine
from qsim.engines.qutip.dynamics.classical import QutipClassicalDynamicsMixin
from qsim.engines.qutip.dynamics.hybrid import QutipHybridDynamicsMixin
from qsim.engines.qutip.measurement import QutipMeasurementMixin
from qsim.engines.qutip.operators import QutipOperatorMixin
from qsim.engines.qutip.runner import QutipRunnerMixin
from qsim.engines.qutip.serialization import QutipSerializationMixin
from qsim.engines.qutip.modes.sme import QutipSmeMixin


class QuTiPEngine(
    QutipOperatorMixin,
    QutipMeasurementMixin,
    QutipClassicalDynamicsMixin,
    QutipHybridDynamicsMixin,
    QutipRunnerMixin,
    QutipSmeMixin,
    QutipSerializationMixin,
    Engine,
):
    """QuTiP-backed dynamics engine."""

    name = "qutip"

    @staticmethod
    def _is_cqed_model(model_type: str) -> bool:
        return str(model_type).strip().lower() in {"cqed_jc", "cqed_dispersive"}

    @staticmethod
    def _coeff_interp(times: list[float], values: list[float], scale: float) -> Callable[[float, dict], float]:
        if not times or not values:
            return lambda _t, _args: 0.0
        x = np.asarray(times, dtype=float)
        y = scale * np.asarray(values, dtype=float)
        if x.size == 1:
            c = float(y[0])
            return lambda _t, _args: c

        x0 = float(x[0])
        x1 = float(x[-1])

        def f(t, _args=None):
            tv = float(t)
            if tv <= x0:
                return float(y[0])
            if tv >= x1:
                return float(y[-1])
            return float(np.interp(tv, x, y))

        return f

    @staticmethod
    def _modulated_coeff(
        envelope: Callable[[float, dict], float],
        *,
        omega_rad_s: float,
        phase_rad: float,
        trig: str,
    ) -> Callable[[float, dict], float]:
        def f(t, args=None):
            env = float(envelope(t, args))
            angle = float(omega_rad_s) * float(t) + float(phase_rad)
            if trig == "sin":
                return env * math.sin(angle)
            return env * math.cos(angle)

        return f

    def _control_envelope(self, ctrl):
        if hasattr(ctrl, "coefficient"):
            coeff = ctrl.coefficient
            return self._coeff_interp(
                [float(x) for x in list(coeff.times_s or [])],
                [float(x) for x in list(coeff.values or [])],
                float(coeff.scale),
            )
        if hasattr(ctrl, "times"):
            return self._coeff_interp(
                [float(x) for x in list(ctrl.times or [])],
                [float(x) for x in list(ctrl.values or [])],
                float(ctrl.scale),
            )
        return self._coeff_interp(
            [float(x) for x in ctrl.get("times", [])],
            [float(x) for x in ctrl.get("values", [])],
            float(ctrl.get("scale", 1.0)),
        )

    @staticmethod
    def _dephasing_collapse_prefactor(rate: float, model_type: str) -> float:
        rate = max(0.0, float(rate))
        if rate <= 0.0:
            return 0.0
        if str(model_type).lower() == "qubit_network":
            # With c = sqrt(gamma_phi/2) * sigma_z, off-diagonal qubit coherence
            # decays at gamma_phi. Using sqrt(gamma_phi) would overcount by 2x.
            return math.sqrt(0.5 * rate)
        # For n = a^\dagger a, D[n] damps |0><1| coherence at rate prefactor^2 / 2.
        # Use sqrt(2 * gamma_phi) so Tphi continues to mean the pure-dephasing time
        # of the qubit subspace across nlevel/cqed models as well.
        return math.sqrt(2.0 * rate)

    @staticmethod
    def _one_over_f_trace(
        tlist: np.ndarray,
        amp: float,
        fmin: float,
        fmax: float,
        exponent: float,
        ncomp: int,
        rng: np.random.Generator,
    ) -> np.ndarray:
        if amp <= 0.0 or tlist.size <= 1:
            return np.zeros_like(tlist, dtype=float)
        fmin = max(1e-9, float(fmin))
        nyquist = 0.5 / max(float(tlist[1] - tlist[0]), 1e-12)
        fmax = min(max(fmin * 1.01, float(fmax)), nyquist)
        if fmax <= fmin:
            return np.zeros_like(tlist, dtype=float)

        freqs = np.logspace(np.log10(fmin), np.log10(fmax), int(max(8, ncomp)))
        phases = rng.uniform(0.0, 2.0 * np.pi, size=freqs.shape[0])
        weights = 1.0 / np.maximum(freqs, 1e-12) ** (0.5 * exponent)
        weights = weights / max(1e-12, np.sqrt(np.mean(weights**2)))

        t = tlist.reshape(-1, 1)
        sig = np.sum(weights.reshape(1, -1) * np.sin(2.0 * np.pi * t * freqs.reshape(1, -1) + phases.reshape(1, -1)), axis=1)
        sig = sig - np.mean(sig)
        rms = np.sqrt(np.mean(sig**2))
        if rms > 0:
            sig = sig * (amp / rms)
        return sig.astype(float)

    @staticmethod
    def _ou_trace(tlist: np.ndarray, sigma: float, tau: float, rng: np.random.Generator) -> np.ndarray:
        if sigma <= 0.0 or tlist.size <= 1:
            return np.zeros_like(tlist, dtype=float)
        dt = max(1e-12, float(tlist[1] - tlist[0]))
        tau = max(1e-9, float(tau))
        out = np.zeros_like(tlist, dtype=float)
        a = math.exp(-dt / tau)
        b = sigma * math.sqrt(max(0.0, 1.0 - a * a))
        for k in range(1, tlist.size):
            out[k] = a * out[k - 1] + b * float(rng.normal())
        return out

    @staticmethod
    def _solver_options_with_state_storage(qt, options, *, store_states: bool, keep_runs_results: bool = False):
        if options is None:
            out = {"store_states": bool(store_states)}
            if keep_runs_results:
                out["keep_runs_results"] = True
            return out
        if isinstance(options, dict):
            out = dict(options)
            out["store_states"] = bool(store_states)
            if keep_runs_results:
                out["keep_runs_results"] = True
            return out
        try:
            setattr(options, "store_states", bool(store_states))
            if keep_runs_results:
                setattr(options, "keep_runs_results", True)
        except Exception:
            pass
        return options

    @staticmethod
    def _series_to_float(values) -> np.ndarray:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return np.real(arr).astype(float)

    @staticmethod
    def _series_to_complex(values) -> np.ndarray:
        return np.asarray(values, dtype=complex).reshape(-1)

    @staticmethod
    def _average_expect_series(values) -> np.ndarray:
        arr = np.asarray(values, dtype=complex)
        if arr.ndim <= 1:
            return arr.reshape(-1)
        return np.mean(arr, axis=0).reshape(-1)

    @staticmethod
    def _shot_expectation_series(values) -> list[np.ndarray]:
        arr = np.asarray(values, dtype=complex)
        if arr.ndim <= 1:
            return [arr.reshape(-1)]
        return [np.asarray(item, dtype=complex).reshape(-1) for item in arr]

    @classmethod
    def _stochastic_expect_series(cls, result, idx: int) -> tuple[np.ndarray, list[np.ndarray]]:
        runs_expect = getattr(result, "runs_expect", None)
        if isinstance(runs_expect, list) and 0 <= idx < len(runs_expect):
            arr = np.asarray(runs_expect[idx], dtype=complex)
            if arr.ndim == 1:
                shot = arr.reshape(-1)
                return shot, [shot]
            if arr.ndim >= 2:
                shots = [np.asarray(arr[k], dtype=complex).reshape(-1) for k in range(arr.shape[0])]
                avg = np.mean(arr, axis=0).reshape(-1)
                return avg, shots
        expect = getattr(result, "expect", None)
        if isinstance(expect, list) and 0 <= idx < len(expect):
            arr = np.asarray(expect[idx], dtype=complex)
            if arr.ndim <= 1:
                shot = arr.reshape(-1)
                return shot, [shot]
            shots = [np.asarray(item, dtype=complex).reshape(-1) for item in arr]
            avg = np.mean(arr, axis=0).reshape(-1)
            return avg, shots
        return np.asarray([], dtype=complex), []
