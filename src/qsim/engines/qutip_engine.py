"""QuTiP-based dynamics engine implementation."""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from qsim.common.schemas import ModelSpec, Trace
from qsim.engines.base import Engine


class QuTiPEngine(Engine):
    """QuTiP-backed dynamics engine."""

    name = "qutip"

    @staticmethod
    def _tensor_op(qt, dims: list[int], target: int, base_op):
        ops = [qt.qeye(d) for d in dims]
        ops[target] = base_op
        return qt.tensor(ops)

    @staticmethod
    def _projector_one(qt, level_dim: int):
        if level_dim <= 1:
            return qt.qeye(level_dim)
        v = qt.basis(level_dim, 1)
        return v * v.dag()

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

    def _build_qubit_ops(self, qt, n_qubits: int):
        dims = [2 for _ in range(n_qubits)]
        sx = [self._tensor_op(qt, dims, i, qt.sigmax()) for i in range(n_qubits)]
        sy = [self._tensor_op(qt, dims, i, qt.sigmay()) for i in range(n_qubits)]
        sz = [self._tensor_op(qt, dims, i, qt.sigmaz()) for i in range(n_qubits)]
        # qutip.sigmam/sigmap follow a spin convention where sigmam maps basis(2,0) -> basis(2,1).
        # This codebase treats basis(2,0) as |0> ground and basis(2,1) as |1> excited, so the
        # physical lowering operator |0><1| corresponds to qutip.sigmap() under that basis ordering.
        sm = [self._tensor_op(qt, dims, i, qt.sigmap()) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(2, 0) for _ in range(n_qubits)])
        ident = qt.tensor([qt.qeye(2) for _ in range(n_qubits)])
        readout_ops = [0.5 * (ident - sz[i]) for i in range(n_qubits)]
        return sx, sy, sz, sm, psi0, readout_ops

    def _build_nlevel_ops(self, qt, n_qubits: int, levels: int):
        levels = max(2, int(levels))
        dims = [levels for _ in range(n_qubits)]
        a = [self._tensor_op(qt, dims, i, qt.destroy(levels)) for i in range(n_qubits)]
        adag = [op.dag() for op in a]
        n = [adag[i] * a[i] for i in range(n_qubits)]
        x = [a[i] + adag[i] for i in range(n_qubits)]
        y = [-1j * (a[i] - adag[i]) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(levels, 0) for _ in range(n_qubits)])
        p1_local = self._projector_one(qt, levels)
        readout_ops = [self._tensor_op(qt, dims, i, p1_local) for i in range(n_qubits)]
        return a, adag, n, x, y, psi0, readout_ops

    def _build_cqed_ops(self, qt, n_qubits: int, levels: int, cavity_nmax: int):
        levels = max(2, int(levels))
        nc = max(1, int(cavity_nmax) + 1)
        dims = [nc] + [levels for _ in range(n_qubits)]
        a_c = self._tensor_op(qt, dims, 0, qt.destroy(nc))
        adag_c = a_c.dag()
        n_c = adag_c * a_c
        a_q = [self._tensor_op(qt, dims, i + 1, qt.destroy(levels)) for i in range(n_qubits)]
        adag_q = [op.dag() for op in a_q]
        n_q = [adag_q[i] * a_q[i] for i in range(n_qubits)]
        x_q = [a_q[i] + adag_q[i] for i in range(n_qubits)]
        y_q = [-1j * (a_q[i] - adag_q[i]) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(nc, 0)] + [qt.basis(levels, 0) for _ in range(n_qubits)])
        p1_local = self._projector_one(qt, levels)
        readout_ops = [self._tensor_op(qt, dims, i + 1, p1_local) for i in range(n_qubits)]
        return a_c, adag_c, n_c, a_q, adag_q, n_q, x_q, y_q, psi0, readout_ops

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trace:
        """Solve model dynamics based on ``model_spec.solver``.

        Supported solvers:
        - ``se``: Schrodinger equation
        - ``me``: master equation
        - ``mcwf``: Monte-Carlo wave-function
        """
        run_options = run_options or {}

        try:
            import qutip as qt
        except Exception as exc:
            raise RuntimeError(f"QuTiP dependency unavailable: {exc}") from exc

        payload = model_spec.payload or {}
        model_type = str(payload.get("model_type", "qubit_network"))

        n_qubits = int(payload.get("num_qubits", 1))
        if n_qubits < 1:
            raise ValueError(f"Invalid model payload: num_qubits must be >= 1, got {n_qubits}")

        dt = max(float(model_spec.dt), 1e-9)
        t_end = max(float(model_spec.t_end), dt)
        tlist = np.arange(0.0, t_end + 0.5 * dt, dt)

        freqs = [float(x) for x in payload.get("qubit_omega_rad_s", [0.0 for _ in range(n_qubits)])]
        if len(freqs) < n_qubits:
            freqs.extend([0.0] * (n_qubits - len(freqs)))
        anh = [float(x) for x in payload.get("anharmonicity_rad_s", [0.0 for _ in range(n_qubits)])]
        if len(anh) < n_qubits:
            anh.extend([0.0] * (n_qubits - len(anh)))
        frame_cfg = dict(payload.get("frame", {}) or {})
        frame_mode = str(frame_cfg.get("mode", "rotating")).strip().lower()
        rwa = bool(frame_cfg.get("rwa", True))

        if model_type == "qubit_network":
            sx, sy, sz, sm, psi0, e_ops = self._build_qubit_ops(qt, n_qubits)
            x_ops = sx
            y_ops = sy
            z_ops = sz
            lower_ops = sm
            raise_ops = [op.dag() for op in sm]
            H0 = 0 * sz[0]
            for i in range(n_qubits):
                H0 = H0 + 0.5 * freqs[i] * sz[i]
        elif model_type == "transmon_nlevel":
            levels = int(payload.get("transmon_levels", 3))
            a, adag, n, x, y, psi0, e_ops = self._build_nlevel_ops(qt, n_qubits, levels)
            x_ops = x
            y_ops = y
            z_ops = n
            lower_ops = a
            raise_ops = adag
            H0 = 0 * n[0]
            for i in range(n_qubits):
                ni = n[i]
                ident = qt.qeye(ni.dims[0])
                H0 = H0 + freqs[i] * ni + 0.5 * anh[i] * (ni * (ni - ident))
        elif model_type == "cqed_jc":
            levels = int(payload.get("transmon_levels", 3))
            cavity_nmax = int(payload.get("cavity_nmax", 8))
            a_c, adag_c, n_c, a_q, adag_q, n_q, x_q, y_q, psi0, e_ops = self._build_cqed_ops(qt, n_qubits, levels, cavity_nmax)
            x_ops = x_q
            y_ops = y_q
            z_ops = n_q
            lower_ops = a_q
            raise_ops = adag_q
            H0 = float(payload.get("cavity_omega_rad_s", 0.0)) * n_c
            for i in range(n_qubits):
                ni = n_q[i]
                ident = qt.qeye(ni.dims[0])
                H0 = H0 + freqs[i] * ni + 0.5 * anh[i] * (ni * (ni - ident))
            g_cavity = payload.get("g_cavity_rad_s", [0.0 for _ in range(n_qubits)])
            if len(g_cavity) < n_qubits:
                g_cavity = list(g_cavity) + [0.0] * (n_qubits - len(g_cavity))
            for i in range(n_qubits):
                g = float(g_cavity[i])
                if g != 0.0:
                    H0 = H0 + g * (adag_c * a_q[i] + a_c * adag_q[i])
        else:
            raise ValueError(f"Unsupported model_type for QuTiP engine: {model_type}")

        for c in payload.get("couplings", []):
            i = int(c.get("i", 0))
            j = int(c.get("j", 0))
            if i < 0 or j < 0 or i >= n_qubits or j >= n_qubits or i == j:
                continue
            g = float(c.get("g_rad_s", c.get("g", 0.0)))
            kind = str(c.get("kind", "xx+yy")).lower()
            if kind == "zz":
                H0 = H0 + g * (z_ops[i] * z_ops[j])
            elif kind == "xx":
                H0 = H0 + g * (x_ops[i] * x_ops[j])
            else:
                if model_type == "qubit_network":
                    H0 = H0 + g * ((x_ops[i] * x_ops[j]) + (y_ops[i] * y_ops[j]))
                else:
                    H0 = H0 + g * (raise_ops[i] * lower_ops[j] + lower_ops[i] * raise_ops[j])

        H = [H0]
        for ctrl in payload.get("controls", []):
            target = int(ctrl.get("target", -1))
            if target < 0 or target >= n_qubits:
                continue
            axis = str(ctrl.get("axis", "x")).lower()
            if axis == "x":
                op_x = x_ops[target]
                op_y = y_ops[target]
            elif axis == "z":
                op = z_ops[target]
            elif axis == "y":
                op = y_ops[target]
            else:
                continue
            coeff_env = self._coeff_interp(
                [float(x) for x in ctrl.get("times", [])],
                [float(x) for x in ctrl.get("values", [])],
                float(ctrl.get("scale", 1.0)),
            )
            if axis == "x":
                carrier_omega_rad_s = float(ctrl.get("carrier_omega_rad_s", 0.0))
                drive_delta_rad_s = float(ctrl.get("drive_delta_rad_s", 0.0))
                phase_rad = float(ctrl.get("carrier_phase_rad", 0.0))
                if frame_mode == "rotating" and rwa:
                    H.append(
                        [
                            op_x,
                            self._modulated_coeff(
                                coeff_env,
                                omega_rad_s=drive_delta_rad_s,
                                phase_rad=phase_rad,
                                trig="cos",
                            ),
                        ]
                    )
                    H.append(
                        [
                            op_y,
                            self._modulated_coeff(
                                coeff_env,
                                omega_rad_s=drive_delta_rad_s,
                                phase_rad=phase_rad,
                                trig="sin",
                            ),
                        ]
                    )
                else:
                    H.append(
                        [
                            op_x,
                            self._modulated_coeff(
                                coeff_env,
                                omega_rad_s=carrier_omega_rad_s,
                                phase_rad=phase_rad,
                                trig="cos",
                            ),
                        ]
                    )
            else:
                H.append([op, coeff_env])

        c_ops = []
        for item in payload.get("collapse_operators", []):
            target = int(item.get("target", -1))
            if target < 0 or target >= n_qubits:
                continue
            kind = str(item.get("kind", "relaxation")).lower()
            rate = max(0.0, float(item.get("rate_rad_s", item.get("rate", 0.0))))
            if rate <= 0:
                continue
            if kind == "relaxation":
                c_ops.append(math.sqrt(rate) * lower_ops[target])
            elif kind == "dephasing":
                c_ops.append(self._dephasing_collapse_prefactor(rate, model_type) * z_ops[target])
            elif kind == "excitation":
                c_ops.append(math.sqrt(rate) * raise_ops[target])

        noise_summary = payload.get("noise_summary", {}) or {}
        selected_noise = str(noise_summary.get("selected_model", "markovian_lindblad")).lower()
        stochastic = noise_summary.get("stochastic", [])
        seed = int(run_options.get("seed", 12345))
        rng = np.random.default_rng(seed)
        if selected_noise in {"one_over_f", "ou"} and stochastic:
            for item in stochastic:
                target = int(item.get("q", -1))
                if target < 0 or target >= n_qubits:
                    continue
                if selected_noise == "one_over_f":
                    series = self._one_over_f_trace(
                        tlist=tlist,
                        amp=float(item.get("one_over_f_amp_rad_s", item.get("one_over_f_amp", 0.0))),
                        fmin=float(item.get("one_over_f_fmin", 1e-3)),
                        fmax=float(item.get("one_over_f_fmax", 0.5 / max(dt, 1e-12))),
                        exponent=float(item.get("one_over_f_exponent", 1.0)),
                        ncomp=int(run_options.get("one_over_f_components", 64)),
                        rng=rng,
                    )
                else:
                    series = self._ou_trace(
                        tlist=tlist,
                        sigma=float(item.get("ou_sigma_rad_s", item.get("ou_sigma", 0.0))),
                        tau=float(item.get("ou_tau", 1.0)),
                        rng=rng,
                    )
                H.append([z_ops[target], lambda t, _a=None, s=series, x=tlist: float(np.interp(float(t), x, s))])

        solver = str(model_spec.solver).lower()
        options = run_options.get("qutip_options", None)

        if solver not in {"se", "me", "mcwf"}:
            raise ValueError(f"Unsupported solver for QuTiP engine: {model_spec.solver}")

        try:
            if solver == "se":
                result = qt.sesolve(H, psi0, tlist, e_ops=e_ops, options=options)
                expect = [np.array(v, dtype=float) for v in result.expect]
            elif solver == "me":
                result = qt.mesolve(H, psi0, tlist, c_ops=c_ops, e_ops=e_ops, options=options)
                expect = [np.array(v, dtype=float) for v in result.expect]
            else:
                ntraj = int(run_options.get("ntraj", 128))
                result = qt.mcsolve(H, psi0, tlist, c_ops=c_ops, e_ops=e_ops, ntraj=ntraj, options=options)
                expect = [np.array(v, dtype=float) for v in result.expect]
        except Exception as exc:
            raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

        states = []
        for k in range(len(tlist)):
            row = [float(np.clip(expect[i][k], 0.0, 1.0)) for i in range(len(expect))]
            states.append(row)

        return Trace(
            engine="qutip",
            times=tlist.astype(float).tolist(),
            states=states,
            metadata={
                "solver": solver,
                "model_type": model_type,
                "num_qubits": n_qubits,
                "num_controls": len(payload.get("controls", [])),
                "num_collapse_ops": len(c_ops),
                "selected_noise": selected_noise,
                "frame_mode": frame_mode,
                "rwa": rwa,
            },
        )
