"""QuTiP-based dynamics engine implementation."""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from qsim.common.schemas import ModelSpec, Trajectory
from qsim.engines.base import Engine


class QuTiPEngine(Engine):
    """QuTiP-backed dynamics engine."""

    name = "qutip"

    @staticmethod
    def _is_cqed_model(model_type: str) -> bool:
        return str(model_type).strip().lower() in {"cqed_jc", "cqed_dispersive"}

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

    @staticmethod
    def _sample_readout_drive(tlist: np.ndarray, controls: list[dict[str, Any]]) -> np.ndarray:
        drive = np.zeros_like(tlist, dtype=complex)
        for ctrl in controls:
            times = [float(x) for x in ctrl.get("times", [])]
            values = [float(x) for x in ctrl.get("values", [])]
            if not times or not values:
                continue
            env = np.interp(
                tlist,
                np.asarray(times, dtype=float),
                np.asarray(values, dtype=float),
                left=0.0,
                right=0.0,
            )
            phase = float(ctrl.get("carrier_phase_rad", 0.0))
            drive = drive + float(ctrl.get("scale", 1.0)) * env.astype(complex) * complex(math.cos(phase), math.sin(phase))
        return drive

    @staticmethod
    def _infer_cqed_readout_params(payload: dict[str, Any], n_qubits: int) -> dict[str, Any]:
        components = [dict(comp) for comp in list(payload.get("components", []) or []) if isinstance(comp, dict)]
        connections = [dict(conn) for conn in list(payload.get("connections", []) or []) if isinstance(conn, dict)]
        qubit_index: dict[str, int] = {}
        cavity_params: dict[str, Any] = {}
        line_params: dict[str, Any] = {}
        chi_hz = [0.0 for _ in range(max(1, n_qubits))]
        for comp in components:
            comp_type = str(comp.get("type", "")).strip().lower()
            params = dict(comp.get("parameters", {}) or {})
            if comp_type == "transmon":
                qubit_index[str(comp.get("id", f"q{len(qubit_index)}"))] = len(qubit_index)
            elif comp_type == "resonator" and not cavity_params:
                cavity_params = params
            elif comp_type == "readout_line" and not line_params:
                line_params = params
        io_params: dict[str, Any] = {}
        for conn in connections:
            conn_type = str(conn.get("type", "")).strip().lower()
            params = dict(conn.get("parameters", {}) or {})
            if conn_type == "dispersive":
                qid = str(conn.get("a", "")) if str(conn.get("a", "")) in qubit_index else str(conn.get("b", ""))
                q = qubit_index.get(qid)
                if q is not None and q < len(chi_hz):
                    chi_hz[q] = float(params.get("chi_Hz", cavity_params.get("chi_Hz", 0.0)) or 0.0)
            elif conn_type == "readout_feedline" and not io_params:
                io_params = params
        if not any(abs(val) > 0.0 for val in chi_hz):
            fallback = float(cavity_params.get("chi_Hz", 0.0) or 0.0)
            chi_hz = [fallback for _ in range(max(1, n_qubits))]
        return {
            "kappa_int_Hz": float(cavity_params.get("kappa_int_Hz", 0.0) or 0.0),
            "kappa_ext_Hz": float(io_params.get("kappa_ext_Hz", cavity_params.get("kappa_ext_Hz", 0.0)) or 0.0),
            "chi_Hz": chi_hz[:n_qubits],
            "eta_chain": float(io_params.get("eta_chain", line_params.get("eta_chain", 1.0)) or 1.0),
            "gain_dB": float(line_params.get("gain_dB", 0.0) or 0.0),
            "added_noise_photons": float(line_params.get("added_noise_photons", 0.0) or 0.0),
            "center_freq_Hz": float(line_params.get("center_freq_Hz", cavity_params.get("freq_Hz", 0.0)) or 0.0),
            "bandwidth_Hz": float(io_params.get("bandwidth_Hz", line_params.get("bandwidth_Hz", 0.0)) or 0.0),
        }

    @staticmethod
    def _infer_classical_readout_params(payload: dict[str, Any]) -> dict[str, Any]:
        components = [dict(comp) for comp in list(payload.get("components", []) or []) if isinstance(comp, dict)]
        connections = [dict(conn) for conn in list(payload.get("connections", []) or []) if isinstance(conn, dict)]
        cavity_params: dict[str, Any] = {}
        line_params: dict[str, Any] = {}
        io_params: dict[str, Any] = {}
        chi_hz = 0.0
        for comp in components:
            comp_type = str(comp.get("type", "")).strip().lower()
            params = dict(comp.get("parameters", {}) or {})
            if comp_type == "resonator" and not cavity_params:
                cavity_params = params
            elif comp_type == "readout_line" and not line_params:
                line_params = params
        for conn in connections:
            conn_type = str(conn.get("type", "")).strip().lower()
            params = dict(conn.get("parameters", {}) or {})
            if conn_type == "dispersive" and chi_hz == 0.0:
                chi_hz = float(params.get("chi_Hz", cavity_params.get("chi_Hz", 0.0)) or 0.0)
            elif conn_type == "readout_feedline" and not io_params:
                io_params = params
        if chi_hz == 0.0:
            chi_hz = float(cavity_params.get("chi_Hz", 0.0) or 0.0)
        return {
            "kappa_int_Hz": float(cavity_params.get("kappa_int_Hz", 0.0) or 0.0),
            "kappa_ext_Hz": float(io_params.get("kappa_ext_Hz", cavity_params.get("kappa_ext_Hz", 0.0)) or 0.0),
            "chi_Hz": float(chi_hz),
            "eta_chain": float(io_params.get("eta_chain", line_params.get("eta_chain", 1.0)) or 1.0),
            "gain_dB": float(line_params.get("gain_dB", 0.0) or 0.0),
            "added_noise_photons": float(line_params.get("added_noise_photons", 0.0) or 0.0),
            "center_freq_Hz": float(line_params.get("center_freq_Hz", cavity_params.get("freq_Hz", 0.0)) or 0.0),
            "bandwidth_Hz": float(io_params.get("bandwidth_Hz", line_params.get("bandwidth_Hz", 0.0)) or 0.0),
            "cavity_freq_Hz": float(cavity_params.get("freq_Hz", 0.0) or 0.0),
            "input_amplitude_noise_rel_sigma": float(
                line_params.get(
                    "input_amplitude_noise_rel_sigma",
                    io_params.get("input_amplitude_noise_rel_sigma", 0.0),
                )
                or 0.0
            ),
            "input_phase_noise_std_rad": float(
                line_params.get(
                    "input_phase_noise_std_rad",
                    io_params.get("input_phase_noise_std_rad", 0.0),
                )
                or 0.0
            ),
            "input_additive_noise_sigma": float(
                line_params.get(
                    "input_additive_noise_sigma",
                    io_params.get("input_additive_noise_sigma", 0.0),
                )
                or 0.0
            ),
            "feedback_success_prob": float(
                line_params.get(
                    "feedback_success_prob",
                    io_params.get("feedback_success_prob", 1.0),
                )
                or 1.0
            ),
        }

    @staticmethod
    def _classical_readout_state(primary_step: dict[str, Any]) -> tuple[int, str]:
        prep_state = dict(primary_step.get("prep_state", {}) or {})
        options = dict(primary_step.get("options", {}) or {})
        raw_label = str(
            options.get("classical_readout_state", options.get("readout_state_label", prep_state.get("label", "0")))
            or "0"
        ).strip()
        label = raw_label or "0"
        digits = [ch for ch in label if ch.isdigit()]
        state = 1 if digits and digits[0] == "1" else 0
        return state, label

    @classmethod
    def _has_classical_readout_line(cls, payload: dict[str, Any]) -> bool:
        components = [dict(comp) for comp in list(payload.get("components", []) or []) if isinstance(comp, dict)]
        for comp in components:
            if str(comp.get("type", "")).strip().lower() != "readout_line":
                continue
            if str(comp.get("representation", "quantum")).strip().lower() == "classical":
                return True
        return False

    @staticmethod
    def _resolve_hybrid_update_mode(payload: dict[str, Any]) -> str:
        primary_step = dict(payload.get("primary_step", {}) or {})
        options = dict(primary_step.get("options", {}) or {})
        raw = str(
            options.get(
                "hybrid_readout_update",
                options.get("classical_readout_update", options.get("hybrid_update_mode", "predictor_corrector")),
            )
            or "predictor_corrector"
        ).strip().lower()
        if raw in {"staggered", "interleaved", "explicit", "legacy"}:
            return "staggered"
        if raw in {"predictor_corrector", "predictor-corrector", "pc", "midpoint"}:
            return "predictor_corrector"
        return "predictor_corrector"

    @staticmethod
    def _resolve_readout_protocol(payload: dict[str, Any]) -> str:
        primary_step = dict(payload.get("primary_step", {}) or {})
        options = dict(primary_step.get("options", {}) or {})
        raw = str(
            options.get("readout_protocol", options.get("measurement_protocol", "dispersive_reflectometry"))
            or "dispersive_reflectometry"
        ).strip().lower()
        if raw in {"heterodyne", "heterodyne_sme", "heterodyne-sme", "sme_heterodyne"}:
            return "heterodyne_sme"
        if raw in {"homodyne", "homodyne_sme", "homodyne-sme", "sme_homodyne"}:
            return "homodyne_sme"
        return "dispersive_reflectometry"

    @staticmethod
    def _arg_coeff(name: str, store: dict[str, float] | None = None) -> Callable[[float, dict[str, Any] | None], float]:
        def f(_t, args=None):
            if isinstance(args, dict) and name in args:
                return float(args.get(name, 0.0))
            if store is not None:
                return float(store.get(name, 0.0))
            return 0.0

        return f

    @staticmethod
    def _advance_line_state(
        prev: complex,
        *,
        line_target: complex,
        dt: float,
        gamma_line: float,
        line_detuning_rad: float,
        thermal_noise: complex,
    ) -> complex:
        if gamma_line > 0.0:
            next_state = prev + dt * (-(0.5 * gamma_line + 1j * line_detuning_rad) * prev + gamma_line * line_target)
        else:
            next_state = complex(line_target)
        return complex(next_state + thermal_noise)

    @staticmethod
    def _readout_coupling_prefactor(kappa_ext_hz: float) -> float:
        return math.sqrt(max(0.0, 2.0 * math.pi * float(kappa_ext_hz)))

    @classmethod
    def _input_output_a_out(cls, *, a_in: complex, cavity_field: complex, kappa_ext_hz: float) -> complex:
        return complex(a_in) - cls._readout_coupling_prefactor(kappa_ext_hz) * complex(cavity_field)

    @classmethod
    def _build_quantum_state_trajectory(
        cls,
        *,
        snapshots: list[Any],
        requested_kind: str,
        actual_kind: str,
    ) -> dict[str, object] | None:
        if not snapshots:
            return None
        note = ""
        if requested_kind == "density_matrix" and actual_kind != "density_matrix":
            note = "requested density_matrix but hybrid mcwf stores wave_function trajectories"
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in snapshots if isinstance(item, dict)],
            "note": note,
        }

    @classmethod
    def _run_hybrid_cqed_mcwf(
        cls,
        *,
        qt,
        H,
        psi0,
        tlist: np.ndarray,
        c_ops,
        e_ops,
        lower_ops,
        cavity_a,
        cavity_n,
        run_options: dict[str, Any],
        readout_controls: list[dict[str, Any]],
        readout_chain: dict[str, Any],
        requested_state_kind: str,
        save_times: str,
        save_final_state: bool,
        hybrid_update_mode: str,
        hybrid_arg_store: dict[str, float] | None,
    ) -> dict[str, Any]:
        nt = int(tlist.size)
        if nt <= 0:
            return {
                "times": [],
                "states": [],
                "metadata": {},
            }

        seed = int(run_options.get("seed", 12345))
        ntraj = max(1, int(run_options.get("ntraj", 128)))
        dt = max(1.0e-18, float(tlist[1] - tlist[0])) if nt > 1 else 1.0
        solver_options = cls._solver_options_with_state_storage(
            qt,
            run_options.get("qutip_options", None),
            store_states=False,
            keep_runs_results=False,
        )
        step_hamiltonian = qt.QobjEvo(H)
        drive_source = cls._sample_readout_drive(tlist, readout_controls)
        readout_carrier_hz = 0.0
        for ctrl in readout_controls:
            readout_carrier_hz = float(ctrl.get("carrier_freq_Hz", 0.0) or 0.0)
            if readout_carrier_hz != 0.0:
                break

        kappa_ext_hz = max(0.0, float(readout_chain.get("kappa_ext_Hz", 0.0) or 0.0))
        gamma_line = max(0.0, 2.0 * math.pi * float(readout_chain.get("bandwidth_Hz", 0.0) or 0.0))
        line_detuning_rad = 2.0 * math.pi * (
            float(readout_chain.get("center_freq_Hz", 0.0) or 0.0) - float(readout_carrier_hz)
        )
        eta_chain = max(1.0e-6, float(readout_chain.get("eta_chain", 1.0) or 1.0))
        gain_linear = 10.0 ** (float(readout_chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        added_noise = max(0.0, float(readout_chain.get("added_noise_photons", 0.0) or 0.0))
        thermal_sigma = max(1.0e-6, math.sqrt(added_noise + 1.0e-12) * 1.0e-2)
        measurement_sigma = max(1.0e-6, math.sqrt(added_noise / eta_chain + 1.0e-12) * 5.0e-3)
        coupling_scale = cls._readout_coupling_prefactor(kappa_ext_hz)
        e_ops_all = list(e_ops) + [cavity_a, cavity_n] + list(lower_ops)
        num_primary = len(e_ops)
        num_lowering = len(lower_ops)

        avg_primary = np.zeros((num_primary, nt), dtype=float)
        avg_cavity_a = np.zeros(nt, dtype=complex)
        avg_cavity_n = np.zeros(nt, dtype=float)
        avg_a_in = np.zeros(nt, dtype=complex)
        avg_a_out = np.zeros(nt, dtype=complex)
        avg_line = np.zeros(nt, dtype=complex)
        avg_measured = np.zeros(nt, dtype=complex)
        avg_lowering = [np.zeros(nt, dtype=complex) for _ in range(num_lowering)]
        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        first_snapshots: list[dict[str, Any]] = []

        for traj in range(ntraj):
            traj_seed = seed + 7919 * traj
            traj_rng = np.random.default_rng(traj_seed)
            if c_ops:
                solver_obj = qt.MCSolver(step_hamiltonian, c_ops, options=solver_options)
            else:
                solver_obj = qt.SESolver(step_hamiltonian, options=solver_options)

            state = psi0.copy()
            traj_primary = np.zeros((num_primary, nt), dtype=float)
            traj_cavity_a = np.zeros(nt, dtype=complex)
            traj_cavity_n = np.zeros(nt, dtype=float)
            traj_a_in = np.zeros(nt, dtype=complex)
            traj_a_out = np.zeros(nt, dtype=complex)
            traj_line = np.zeros(nt, dtype=complex)
            traj_measured = np.zeros(nt, dtype=complex)
            traj_lowering = [np.zeros(nt, dtype=complex) for _ in range(num_lowering)]

            line_state = complex(drive_source[0]) if nt > 0 else 0.0j

            def _measurement_noise() -> complex:
                return measurement_sigma * math.sqrt(dt) * (
                    float(traj_rng.normal()) + 1j * float(traj_rng.normal())
                ) / math.sqrt(2.0)

            def _thermal_kick() -> complex:
                return thermal_sigma * math.sqrt(dt) * (
                    float(traj_rng.normal()) + 1j * float(traj_rng.normal())
                ) / math.sqrt(2.0)

            obs0 = np.asarray(qt.expect(e_ops_all, state), dtype=complex).reshape(-1)
            traj_primary[:, 0] = np.real(obs0[:num_primary]).astype(float)
            traj_cavity_a[0] = complex(obs0[num_primary])
            traj_cavity_n[0] = float(np.real(obs0[num_primary + 1]))
            for idx in range(num_lowering):
                traj_lowering[idx][0] = complex(obs0[num_primary + 2 + idx])
            traj_line[0] = line_state
            traj_a_in[0] = line_state
            traj_a_out[0] = cls._input_output_a_out(a_in=line_state, cavity_field=traj_cavity_a[0], kappa_ext_hz=kappa_ext_hz)
            traj_measured[0] = gain_linear * traj_a_out[0] + _measurement_noise()

            if traj == 0 and requested_state_kind == "wave_function" and save_times != "none":
                first_snapshots.append(cls._serialize_qobj_state(state))

            for k in range(nt - 1):
                if c_ops:
                    solver_obj.start(state, float(tlist[k]), seed=traj_seed + k)
                else:
                    solver_obj.start(state, float(tlist[k]))
                thermal_noise = _thermal_kick()
                if hybrid_update_mode == "predictor_corrector":
                    line_target_pred = cls._input_output_a_out(
                        a_in=complex(drive_source[k + 1]),
                        cavity_field=traj_cavity_a[k],
                        kappa_ext_hz=kappa_ext_hz,
                    )
                    line_pred = cls._advance_line_state(
                        line_state,
                        line_target=line_target_pred,
                        dt=dt,
                        gamma_line=gamma_line,
                        line_detuning_rad=line_detuning_rad,
                        thermal_noise=0.0j,
                    )
                    line_for_quantum = 0.5 * (line_state + line_pred)
                else:
                    line_for_quantum = line_state

                if hybrid_arg_store is not None:
                    hybrid_arg_store["hybrid_ro_re"] = float(coupling_scale * np.real(line_for_quantum))
                    hybrid_arg_store["hybrid_ro_im"] = float(coupling_scale * np.imag(line_for_quantum))
                args = {
                    "hybrid_ro_re": float(coupling_scale * np.real(line_for_quantum)),
                    "hybrid_ro_im": float(coupling_scale * np.imag(line_for_quantum)),
                }
                state = solver_obj.step(float(tlist[k + 1]), args=args)
                obs_pre = np.asarray(qt.expect(e_ops_all, state), dtype=complex).reshape(-1)
                cavity_field_pre = complex(obs_pre[num_primary])

                traj_a_in[k + 1] = line_for_quantum
                traj_a_out[k + 1] = cls._input_output_a_out(
                    a_in=line_for_quantum,
                    cavity_field=cavity_field_pre,
                    kappa_ext_hz=kappa_ext_hz,
                )

                line_target = cls._input_output_a_out(
                    a_in=complex(drive_source[k + 1]),
                    cavity_field=cavity_field_pre,
                    kappa_ext_hz=kappa_ext_hz,
                )
                line_state = cls._advance_line_state(
                    line_state,
                    line_target=line_target,
                    dt=dt,
                    gamma_line=gamma_line,
                    line_detuning_rad=line_detuning_rad,
                    thermal_noise=thermal_noise,
                )
                traj_line[k + 1] = line_state
                traj_measured[k + 1] = gain_linear * line_state + _measurement_noise()

                obs = np.asarray(qt.expect(e_ops_all, state), dtype=complex).reshape(-1)
                traj_primary[:, k + 1] = np.real(obs[:num_primary]).astype(float)
                traj_cavity_a[k + 1] = complex(obs[num_primary])
                traj_cavity_n[k + 1] = float(np.real(obs[num_primary + 1]))
                for idx in range(num_lowering):
                    traj_lowering[idx][k + 1] = complex(obs[num_primary + 2 + idx])

                if traj == 0 and requested_state_kind == "wave_function" and save_times != "none":
                    first_snapshots.append(cls._serialize_qobj_state(state))

            if traj == 0 and requested_state_kind == "wave_function" and save_times == "none" and save_final_state:
                first_snapshots.append(cls._serialize_qobj_state(state))

            avg_primary += traj_primary
            avg_cavity_a += traj_cavity_a
            avg_cavity_n += traj_cavity_n
            avg_a_in += traj_a_in
            avg_a_out += traj_a_out
            avg_line += traj_line
            avg_measured += traj_measured
            for idx in range(num_lowering):
                avg_lowering[idx] += traj_lowering[idx]

            shot_payload = {
                "a_cavity": cls._serialize_complex_series(traj_cavity_a),
                "a_in": cls._serialize_complex_series(traj_a_in),
                "a_out": cls._serialize_complex_series(traj_a_out),
                "line_state": cls._serialize_complex_series(traj_line),
                "measured_voltage": cls._serialize_complex_series(traj_measured),
            }
            shot_payloads.append(shot_payload)
            measurement_records.append(
                {
                    "times": tlist.astype(float).tolist(),
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            )

        norm = 1.0 / float(ntraj)
        avg_primary *= norm
        avg_cavity_a *= norm
        avg_cavity_n *= norm
        avg_a_in *= norm
        avg_a_out *= norm
        avg_line *= norm
        avg_measured *= norm
        avg_lowering = [series * norm for series in avg_lowering]

        states = [
            [float(np.clip(avg_primary[q, k], 0.0, 1.0)) for q in range(num_primary)]
            for k in range(nt)
        ]
        metadata = {
            "hybrid_update_mode": hybrid_update_mode,
            "measurement_records": measurement_records,
            "readout_observables": {
                "schema_version": "1.0",
                "times": tlist.astype(float).tolist(),
                "chain": dict(readout_chain),
                "equations": {
                    "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>",
                    "line_state": "d alpha_line / dt = -(gamma_line/2 + i Delta_line) alpha_line + gamma_line * a_out + xi_thermal",
                    "measured_voltage": "V_IQ(t) = gain * alpha_line(t) + xi_meas(t)",
                    "quantum_drive": "H_ro(t) uses sqrt(kappa_ext_rad_s) * a_in(t) as the cavity drive coefficient",
                },
                "feedback": {
                    "enabled": True,
                    "mode": hybrid_update_mode,
                    "line_target_source": "a_out",
                    "quantum_input_source": "line_state" if hybrid_update_mode != "predictor_corrector" else "0.5 * (line_state + predicted_line_state)",
                },
                "a_in": cls._serialize_complex_series(avg_a_in),
                "cavity_a": cls._serialize_complex_series(avg_cavity_a),
                "cavity_n": [float(x) for x in avg_cavity_n.tolist()],
                "a_out": cls._serialize_complex_series(avg_a_out),
                "line_state": cls._serialize_complex_series(avg_line),
                "measured_voltage": cls._serialize_complex_series(avg_measured),
                "qubit_lowering": [cls._serialize_complex_series(series) for series in avg_lowering],
                "shots": shot_payloads,
            },
        }
        quantum_state_trajectory = cls._build_quantum_state_trajectory(
            snapshots=first_snapshots,
            requested_kind=requested_state_kind,
            actual_kind="wave_function",
        )
        if quantum_state_trajectory is not None:
            metadata["quantum_state_trajectory"] = quantum_state_trajectory
        return {
            "times": tlist.astype(float).tolist(),
            "states": states,
            "metadata": metadata,
        }

    @classmethod
    def _simulate_classical_readout(
        cls,
        *,
        tlist: np.ndarray,
        drive: np.ndarray,
        cavity_avg: np.ndarray,
        cavity_shots: list[np.ndarray],
        chain: dict[str, Any],
        seed: int,
    ) -> dict[str, Any]:
        if tlist.size <= 0:
            return {}
        kappa_ext = max(0.0, float(chain.get("kappa_ext_Hz", 0.0)))
        eta_chain = max(1.0e-6, float(chain.get("eta_chain", 1.0)))
        added_noise = max(0.0, float(chain.get("added_noise_photons", 0.0)))
        gain_linear = 10.0 ** (float(chain.get("gain_dB", 0.0)) / 20.0)
        bandwidth_hz = max(0.0, float(chain.get("bandwidth_Hz", 0.0)))
        gamma_line = 2.0 * math.pi * bandwidth_hz if bandwidth_hz > 0.0 else 0.0
        dt = max(1.0e-18, float(tlist[1] - tlist[0])) if tlist.size > 1 else 1.0
        noise_sigma = max(1.0e-5, math.sqrt(added_noise / eta_chain) * 1.0e-2)
        rng = np.random.default_rng(int(seed))

        def _simulate_single(cavity_series: np.ndarray) -> dict[str, np.ndarray]:
            a_in = np.asarray(drive, dtype=complex).reshape(-1)
            a_out = np.asarray(
                [
                    cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext)
                    for in_field, cavity_field in zip(a_in, np.asarray(cavity_series, dtype=complex).reshape(-1))
                ],
                dtype=complex,
            )
            line_state = np.zeros_like(a_out, dtype=complex)
            measured_voltage = np.zeros_like(a_out, dtype=complex)
            for k in range(a_out.size):
                noise = noise_sigma * (float(rng.normal()) + 1j * float(rng.normal())) / math.sqrt(2.0)
                if k > 0:
                    prev = line_state[k - 1]
                    if gamma_line > 0.0:
                        line_state[k] = prev + dt * (-0.5 * gamma_line * prev + gamma_line * a_out[k - 1])
                    else:
                        line_state[k] = a_out[k - 1]
                else:
                    line_state[k] = a_out[k]
                measured_voltage[k] = gain_linear * line_state[k] + noise
            return {
                "a_in": a_in,
                "a_out": a_out,
                "line_state": line_state,
                "measured_voltage": measured_voltage,
            }

        shots = [_simulate_single(series) for series in (cavity_shots or [cavity_avg])]
        avg = {
            key: np.mean(np.asarray([shot[key] for shot in shots], dtype=complex), axis=0)
            for key in ("a_in", "a_out", "line_state", "measured_voltage")
        }
        avg["a_cavity"] = np.asarray(cavity_avg, dtype=complex).reshape(-1)
        return {
            "average": avg,
            "shots": [
                {
                    "a_cavity": cls._serialize_complex_series(series),
                    "a_in": cls._serialize_complex_series(shot["a_in"]),
                    "a_out": cls._serialize_complex_series(shot["a_out"]),
                    "line_state": cls._serialize_complex_series(shot["line_state"]),
                    "measured_voltage": cls._serialize_complex_series(shot["measured_voltage"]),
                }
                for shot, series in zip(shots, cavity_shots or [cavity_avg])
            ],
        }

    @staticmethod
    def _measurement_to_real_series(measurement, nt: int) -> np.ndarray:
        arr = np.asarray(measurement)
        if np.iscomplexobj(arr):
            arr = np.real(arr)
        arr = np.asarray(arr, dtype=float)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        out = np.zeros(max(0, int(nt)), dtype=float)
        if out.size <= 0 or arr.size <= 0:
            return out
        if arr.size == out.size - 1:
            out[1:] = arr
            return out
        if arr.size >= out.size:
            out[:] = arr[: out.size]
            return out
        out[-arr.size :] = arr
        return out

    @classmethod
    def _measurement_to_complex_series(cls, measurement, nt: int) -> np.ndarray:
        arr = np.asarray(measurement)
        if np.iscomplexobj(arr):
            if arr.ndim <= 1:
                flat = arr.reshape(-1).astype(complex)
                out = np.zeros(max(0, int(nt)), dtype=complex)
                if out.size <= 0 or flat.size <= 0:
                    return out
                if flat.size == out.size - 1:
                    out[1:] = flat
                    return out
                if flat.size >= out.size:
                    out[:] = flat[: out.size]
                    return out
                out[-flat.size :] = flat
                return out
            if arr.ndim == 2 and arr.shape[0] == 1:
                return cls._measurement_to_complex_series(arr[0], nt)
            if arr.ndim == 2 and arr.shape[1] == 1:
                return cls._measurement_to_complex_series(arr[:, 0], nt)
            arr = np.real(arr)
        arr = np.asarray(arr, dtype=float)
        if arr.ndim <= 1:
            return cls._measurement_to_real_series(arr, nt).astype(complex)
        if arr.ndim == 2 and arr.shape[0] >= 2:
            i_vals = cls._measurement_to_real_series(arr[0], nt)
            q_vals = cls._measurement_to_real_series(arr[1], nt)
            return i_vals.astype(complex) + 1j * q_vals.astype(complex)
        if arr.ndim == 2 and arr.shape[-1] >= 2:
            i_vals = cls._measurement_to_real_series(arr[:, 0], nt)
            q_vals = cls._measurement_to_real_series(arr[:, 1], nt)
            return i_vals.astype(complex) + 1j * q_vals.astype(complex)
        return cls._measurement_to_real_series(arr.reshape(-1), nt).astype(complex)

    @staticmethod
    def _complex_vector(values) -> list[complex]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [complex(float(v.real), float(v.imag)) for v in arr]

    @classmethod
    def _serialize_complex_series(cls, values) -> list[list[float]]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [[float(v.real), float(v.imag)] for v in arr]

    @classmethod
    def _serialize_real_series_as_complex(cls, values) -> list[list[float]]:
        arr = np.asarray(values, dtype=float).reshape(-1)
        return [[float(v), 0.0] for v in arr]

    @classmethod
    def _serialize_qobj_state(cls, qobj) -> dict[str, object]:
        data = np.asarray(qobj.full(), dtype=complex)
        if data.ndim == 2 and 1 in data.shape:
            return {"kind": "wave_function", "data": cls._complex_vector(data.reshape(-1))}
        return {
            "kind": "density_matrix",
            "data": [[cls._complex_vector(row) for row in data]][0],
        }

    @classmethod
    def _extract_quantum_state_trajectory(cls, result, solver: str, requested_kind: str) -> dict[str, object] | None:
        if requested_kind not in {"wave_function", "density_matrix"}:
            return None
        raw_states = list(getattr(result, "states", []) or [])
        if not raw_states and solver == "mcwf":
            runs_states = list(getattr(result, "runs_states", []) or [])
            raw_states = list(runs_states[:1] or [])
            if raw_states and isinstance(raw_states[0], list):
                raw_states = list(raw_states[0])
        if not raw_states:
            return None
        serialized = [cls._serialize_qobj_state(state) for state in raw_states]
        actual_kind = str(serialized[0].get("kind", "unknown"))
        if requested_kind == "wave_function" and actual_kind != "wave_function":
            note = "requested wave_function but solver returned density_matrix"
        else:
            note = ""
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in serialized],
            "note": note,
        }

    @staticmethod
    def _average_qobj_sequences(sequences: list[list[Any]]) -> list[Any]:
        averaged: list[Any] = []
        if not sequences:
            return averaged
        nsteps = max(len(seq) for seq in sequences)
        for idx in range(nsteps):
            samples = [seq[idx] for seq in sequences if idx < len(seq)]
            if not samples:
                continue
            accum = samples[0] * 0.0
            for state in samples:
                accum = accum + state
            averaged.append(accum * (1.0 / float(len(samples))))
        return averaged

    @classmethod
    def _extract_stochastic_density_trajectory(cls, result, requested_kind: str) -> dict[str, object] | None:
        if requested_kind not in {"wave_function", "density_matrix"}:
            return None
        raw_runs_states = list(getattr(result, "runs_states", []) or [])
        state_runs: list[list[Any]] = []
        if raw_runs_states:
            state_runs = [list(run) for run in raw_runs_states if isinstance(run, list) and run]
        if not state_runs:
            raw_states = list(getattr(result, "states", []) or [])
            if raw_states and isinstance(raw_states[0], list):
                state_runs = [list(run) for run in raw_states if isinstance(run, list) and run]
            elif raw_states:
                state_runs = [list(raw_states)]
        if not state_runs:
            return None
        averaged_states = cls._average_qobj_sequences(state_runs)
        if not averaged_states:
            return None
        serialized = [cls._serialize_qobj_state(state) for state in averaged_states]
        serialized_runs = [
            [cls._serialize_qobj_state(state) for state in run]
            for run in state_runs
        ]
        actual_kind = str(serialized[0].get("kind", "density_matrix"))
        note = ""
        if requested_kind == "wave_function":
            note = "requested wave_function but stochastic SME returns density_matrix"
        return {
            "requested_kind": requested_kind or actual_kind,
            "actual_kind": actual_kind,
            "encoding": "complex",
            "snapshots": [item.get("data", []) for item in serialized],
            "runs": [[item.get("data", []) for item in run] for run in serialized_runs],
            "num_runs": len(serialized_runs),
            "note": note,
        }

    @staticmethod
    def _quantum_payloads(qstate: dict[str, object] | None) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        payload = dict(qstate or {})
        actual_kind = str(payload.get("actual_kind", "")).strip().lower()
        if actual_kind == "wave_function":
            return payload, None
        if actual_kind == "density_matrix":
            return None, payload
        return None, None

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

    @classmethod
    def _run_cavity_classical_readout(
        cls,
        *,
        model_spec: ModelSpec,
        run_options: dict[str, Any],
    ) -> Trajectory:
        payload = dict(model_spec.payload or {})
        dt = max(float(model_spec.dt), 1.0e-12)
        t_end = max(float(model_spec.t_end), dt)
        tlist = np.arange(0.0, t_end + 0.5 * dt, dt)
        nt = int(tlist.size)
        primary_step = dict(payload.get("primary_step", {}) or {})
        hidden_state, state_label = cls._classical_readout_state(primary_step)
        chain = cls._infer_classical_readout_params(payload)
        readout_controls = list(payload.get("readout_controls", []) or [])
        base_drive = cls._sample_readout_drive(tlist, readout_controls)
        drive_freq_hz = float(readout_controls[0].get("carrier_freq_Hz", chain.get("center_freq_Hz", 0.0))) if readout_controls else float(chain.get("center_freq_Hz", 0.0))
        cavity_freq_hz = float(chain.get("cavity_freq_Hz", drive_freq_hz) or drive_freq_hz)
        chi_hz = float(chain.get("chi_Hz", 0.0) or 0.0)
        state_shift_hz = chi_hz if hidden_state else 0.0
        delta_eff_rad_s = 2.0 * math.pi * (cavity_freq_hz + state_shift_hz - drive_freq_hz)
        kappa_int_rad_s = max(0.0, 2.0 * math.pi * float(chain.get("kappa_int_Hz", 0.0)))
        kappa_ext_rad_s = max(0.0, 2.0 * math.pi * float(chain.get("kappa_ext_Hz", 0.0)))
        kappa_total_rad_s = kappa_int_rad_s + kappa_ext_rad_s
        gamma_line = 2.0 * math.pi * max(0.0, float(chain.get("bandwidth_Hz", 0.0)))
        eta_chain = max(1.0e-6, float(chain.get("eta_chain", 1.0) or 1.0))
        gain_linear = 10.0 ** (float(chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        added_noise_photons = max(0.0, float(chain.get("added_noise_photons", 0.0) or 0.0))
        input_amp_sigma = max(0.0, float(chain.get("input_amplitude_noise_rel_sigma", 0.0) or 0.0))
        input_phase_sigma = max(0.0, float(chain.get("input_phase_noise_std_rad", 0.0) or 0.0))
        input_add_sigma = max(0.0, float(chain.get("input_additive_noise_sigma", 0.0) or 0.0))
        feedback_success_prob = min(1.0, max(0.0, float(chain.get("feedback_success_prob", 1.0) or 1.0)))
        coupling = cls._readout_coupling_prefactor(float(chain.get("kappa_ext_Hz", 0.0) or 0.0))
        seed = int(run_options.get("seed", 12345))
        ntraj = max(1, int(run_options.get("ntraj", 128)))
        rng = np.random.default_rng(seed)
        drive_scale = max(1.0, float(np.max(np.abs(base_drive))) if base_drive.size > 0 else 1.0)
        measurement_noise_sigma = max(
            1.0e-5,
            drive_scale
            * (
                math.sqrt(added_noise_photons / eta_chain) * 1.0e-2
                + float((payload.get("noise_cfg", {}) or {}).get("readout_error", 0.0) or 0.0)
            ),
        )
        reset_events = [
            {
                **dict(event),
                "t0_s": 1.0e-9 * float(dict(event).get("t0", 0.0) or 0.0),
                "t_meas_end_s": 1.0e-9 * float(dict(event).get("t_meas_end", 0.0) or 0.0),
                "t_feedback_start_s": 1.0e-9 * float(dict(event).get("t_feedback_end", 0.0) or 0.0),
                "t_apply_s": 1.0e-9 * float(dict(event).get("t1", 0.0) or 0.0),
            }
            for event in list(payload.get("reset_events", []) or [])
            if isinstance(event, dict)
        ]
        reset_events.sort(key=lambda item: float(item.get("t0_s", 0.0)))

        def _nearest_time_index(target_s: float) -> int:
            return int(np.clip(np.searchsorted(tlist, float(target_s), side="left"), 0, max(0, nt - 1)))

        def _integrate_complex_window(trace: np.ndarray, start_s: float, stop_s: float) -> complex:
            if nt <= 0:
                return 0.0j
            mask = (tlist >= float(start_s)) & (tlist <= float(stop_s))
            if not np.any(mask):
                idx = _nearest_time_index(0.5 * (float(start_s) + float(stop_s)))
                return complex(trace[idx])
            t_sel = tlist[mask]
            trace_sel = np.asarray(trace[mask], dtype=complex)
            if t_sel.size == 1:
                return complex(trace_sel[0])
            span = max(float(t_sel[-1] - t_sel[0]), 1.0e-18)
            if hasattr(np, "trapezoid"):
                i_val = float(np.trapezoid(np.real(trace_sel), t_sel) / span)
                q_val = float(np.trapezoid(np.imag(trace_sel), t_sel) / span)
            else:
                i_val = float(np.trapz(np.real(trace_sel), t_sel) / span)
                q_val = float(np.trapz(np.imag(trace_sel), t_sel) / span)
            return complex(i_val, q_val)

        def _reference_reset_point(
            *,
            alpha0: complex,
            line0: complex,
            a_in_series: np.ndarray,
            start_idx: int,
            stop_idx: int,
            state: int,
        ) -> complex:
            alpha = complex(alpha0)
            line = complex(line0)
            measured = np.zeros(max(1, stop_idx - start_idx + 1), dtype=complex)
            local_times = tlist[start_idx : stop_idx + 1]
            delta_rad = 2.0 * math.pi * (cavity_freq_hz + (chi_hz if state else 0.0) - drive_freq_hz)
            for out_idx, idx in enumerate(range(start_idx, stop_idx + 1)):
                if idx > start_idx:
                    alpha = alpha + dt * (-(0.5 * kappa_total_rad_s + 1j * delta_rad) * alpha + coupling * a_in_series[idx - 1])
                a_out_ref = cls._input_output_a_out(
                    a_in=complex(a_in_series[idx]),
                    cavity_field=alpha,
                    kappa_ext_hz=float(chain.get("kappa_ext_Hz", 0.0) or 0.0),
                )
                if gamma_line > 0.0:
                    line = line + dt * (-0.5 * gamma_line * line + gamma_line * a_out_ref)
                else:
                    line = a_out_ref
                measured[out_idx] = gain_linear * math.sqrt(eta_chain) * line
            if measured.size <= 1 or local_times.size <= 1:
                return complex(measured[-1])
            span = max(float(local_times[-1] - local_times[0]), 1.0e-18)
            if hasattr(np, "trapezoid"):
                i_val = float(np.trapezoid(np.real(measured), local_times) / span)
                q_val = float(np.trapezoid(np.imag(measured), local_times) / span)
            else:
                i_val = float(np.trapz(np.real(measured), local_times) / span)
                q_val = float(np.trapz(np.imag(measured), local_times) / span)
            return complex(i_val, q_val)

        shot_payloads: list[dict[str, Any]] = []
        shot_records: list[dict[str, Any]] = []
        mean_accum: dict[str, np.ndarray] = {
            "a_in": np.zeros(nt, dtype=complex),
            "cavity_a": np.zeros(nt, dtype=complex),
            "cavity_n": np.zeros(nt, dtype=float),
            "a_out": np.zeros(nt, dtype=complex),
            "line_state": np.zeros(nt, dtype=complex),
            "heterodyne_current": np.zeros(nt, dtype=complex),
            "measured_voltage": np.zeros(nt, dtype=complex),
        }

        for traj_idx in range(ntraj):
            amp_noise = rng.normal(0.0, input_amp_sigma, size=nt) if input_amp_sigma > 0.0 else np.zeros(nt, dtype=float)
            phase_noise = rng.normal(0.0, input_phase_sigma, size=nt) if input_phase_sigma > 0.0 else np.zeros(nt, dtype=float)
            additive_noise = (
                input_add_sigma
                * (rng.normal(0.0, 1.0, size=nt) + 1j * rng.normal(0.0, 1.0, size=nt))
                / math.sqrt(2.0)
                if input_add_sigma > 0.0
                else np.zeros(nt, dtype=complex)
            )
            a_in = base_drive * (1.0 + amp_noise) * np.exp(1j * phase_noise) + additive_noise

            cavity_a = np.zeros(nt, dtype=complex)
            state_series = np.zeros(nt, dtype=int)
            current_state = int(hidden_state)
            state_series[:] = current_state
            cavity_n = np.abs(cavity_a) ** 2
            a_out = np.zeros(nt, dtype=complex)
            line_state = np.zeros(nt, dtype=complex)
            heterodyne_current = np.zeros(nt, dtype=complex)
            measured_voltage = np.zeros(nt, dtype=complex)
            reset_log: list[dict[str, Any]] = []
            reset_contexts: list[dict[str, Any]] = []
            for event in reset_events:
                reset_contexts.append(
                    {
                        **event,
                        "measured": False,
                        "applied": False,
                        "predicted_state": None,
                        "alpha_start": None,
                        "line_start": None,
                    }
                )
            for idx in range(nt):
                if idx > 0:
                    current_state = int(state_series[idx - 1])
                    delta_now_rad_s = 2.0 * math.pi * (cavity_freq_hz + (chi_hz if current_state else 0.0) - drive_freq_hz)
                    cavity_a[idx] = cavity_a[idx - 1] + dt * (
                        -(0.5 * kappa_total_rad_s + 1j * delta_now_rad_s) * cavity_a[idx - 1]
                        + coupling * a_in[idx - 1]
                    )
                    cavity_n[idx] = float(abs(cavity_a[idx]) ** 2)
                a_out[idx] = cls._input_output_a_out(
                    a_in=complex(a_in[idx]),
                    cavity_field=complex(cavity_a[idx]),
                    kappa_ext_hz=float(chain.get("kappa_ext_Hz", 0.0) or 0.0),
                )
                if idx == 0:
                    line_state[idx] = a_out[idx]
                elif gamma_line > 0.0:
                    line_state[idx] = line_state[idx - 1] + dt * (-0.5 * gamma_line * line_state[idx - 1] + gamma_line * a_out[idx - 1])
                else:
                    line_state[idx] = a_out[idx]
                noise = measurement_noise_sigma * (
                    rng.normal(0.0, 1.0) + 1j * rng.normal(0.0, 1.0)
                ) / math.sqrt(2.0)
                heterodyne_current[idx] = math.sqrt(eta_chain) * line_state[idx] + noise
                measured_voltage[idx] = gain_linear * heterodyne_current[idx]
                state_series[idx] = current_state

                for event in reset_contexts:
                    if event["alpha_start"] is None and float(tlist[idx]) >= float(event.get("t0_s", 0.0)):
                        event["alpha_start"] = complex(cavity_a[idx])
                        event["line_start"] = complex(line_state[idx])
                    if not event["measured"] and float(tlist[idx]) >= float(event.get("t_meas_end_s", 0.0)):
                        start_idx = _nearest_time_index(float(event.get("t0_s", 0.0)))
                        stop_idx = _nearest_time_index(float(event.get("t_meas_end_s", 0.0)))
                        actual_point = _integrate_complex_window(measured_voltage, float(event.get("t0_s", 0.0)), float(event.get("t_meas_end_s", 0.0)))
                        alpha_start = complex(event.get("alpha_start", 0.0j) or 0.0j)
                        line_start = complex(event.get("line_start", 0.0j) or 0.0j)
                        point_0 = _reference_reset_point(alpha0=alpha_start, line0=line_start, a_in_series=a_in, start_idx=start_idx, stop_idx=stop_idx, state=0)
                        point_1 = _reference_reset_point(alpha0=alpha_start, line0=line_start, a_in_series=a_in, start_idx=start_idx, stop_idx=stop_idx, state=1)
                        predicted_state = 0 if abs(actual_point - point_0) <= abs(actual_point - point_1) else 1
                        event["predicted_state"] = int(predicted_state)
                        event["measured"] = True
                        reset_log.append(
                            {
                                "trajectory_index": traj_idx,
                                "window_s": {"t0": float(event.get("t0_s", 0.0)), "t1": float(event.get("t_meas_end_s", 0.0))},
                                "actual_state_before_feedback": int(current_state),
                                "predicted_state": int(predicted_state),
                                "integrated_iq": [float(actual_point.real), float(actual_point.imag)],
                            }
                        )
                    if (
                        not event["applied"]
                        and event["predicted_state"] is not None
                        and float(tlist[idx]) >= float(event.get("t_apply_s", 0.0))
                    ):
                        if bool(event.get("apply_feedback", False)) and int(event.get("predicted_state", -1)) == int(event.get("conditional_on", 1)):
                            if float(rng.random()) <= feedback_success_prob:
                                current_state = 1 - int(current_state)
                        event["applied"] = True
                    state_series[idx] = current_state

            cavity_n = np.abs(cavity_a) ** 2

            mean_accum["a_in"] += a_in
            mean_accum["cavity_a"] += cavity_a
            mean_accum["cavity_n"] += cavity_n
            mean_accum["a_out"] += a_out
            mean_accum["line_state"] += line_state
            mean_accum["heterodyne_current"] += heterodyne_current
            mean_accum["measured_voltage"] += measured_voltage

            shot_payload = {
                "trajectory_index": traj_idx,
                "hidden_state": int(hidden_state),
                "hidden_state_label": state_label,
                "hidden_state_series": [int(val) for val in state_series.tolist()],
                "a_cavity": cls._serialize_complex_series(cavity_a),
                "a_in": cls._serialize_complex_series(a_in),
                "a_out": cls._serialize_complex_series(a_out),
                "line_state": cls._serialize_complex_series(line_state),
                "heterodyne_current": cls._serialize_complex_series(heterodyne_current),
                "measured_voltage": cls._serialize_complex_series(measured_voltage),
                "cavity_n": [float(val) for val in cavity_n.tolist()],
                "reset_log": reset_log,
            }
            shot_payloads.append(shot_payload)
            shot_records.append(
                {
                    "trajectory_index": traj_idx,
                    "times": tlist.astype(float).tolist(),
                    "heterodyne_current": shot_payload["heterodyne_current"],
                    "heterodyne_I": [float(val.real) for val in heterodyne_current.tolist()],
                    "heterodyne_Q": [float(val.imag) for val in heterodyne_current.tolist()],
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            )

        norm = 1.0 / float(ntraj)
        avg_a_in = mean_accum["a_in"] * norm
        avg_cavity_a = mean_accum["cavity_a"] * norm
        avg_cavity_n = (mean_accum["cavity_n"] * norm).tolist()
        avg_a_out = mean_accum["a_out"] * norm
        avg_line_state = mean_accum["line_state"] * norm
        avg_heterodyne = mean_accum["heterodyne_current"] * norm
        avg_voltage = mean_accum["measured_voltage"] * norm

        avg_state_series = np.rint(
            np.mean(
                np.asarray([shot.get("hidden_state_series", [hidden_state for _ in range(nt)]) for shot in shot_payloads], dtype=float),
                axis=0,
            )
        ).astype(int)
        basis_values = [[float(1 - val), float(val)] for val in avg_state_series.tolist()]
        classical = {
            "readout": {
                "times": tlist.astype(float).tolist(),
                "a_in": cls._serialize_complex_series(avg_a_in),
                "cavity_a": cls._serialize_complex_series(avg_cavity_a),
                "cavity_n": [float(val) for val in avg_cavity_n],
                "a_out": cls._serialize_complex_series(avg_a_out),
                "line_state": cls._serialize_complex_series(avg_line_state),
                "heterodyne_current": cls._serialize_complex_series(avg_heterodyne),
                "measured_voltage": cls._serialize_complex_series(avg_voltage),
                "shots": shot_payloads,
                "chain": {
                    **chain,
                    "drive_freq_Hz": float(drive_freq_hz),
                    "state_shift_Hz": float(state_shift_hz),
                    "hidden_state": int(hidden_state),
                    "hidden_state_label": state_label,
                },
                "equations": {
                    "cavity_equation": "d alpha / dt = -(i Delta_eff + kappa/2) alpha + sqrt(kappa_ext) * a_in(t)",
                    "output_equation": "a_out(t) = a_in(t) - sqrt(kappa_ext) * alpha(t)",
                    "measured_voltage": "V_meas(t) = gain * (sqrt(eta_chain) * alpha_line(t) + xi_meas)",
                    "input_noise": "a_in(t) = (1 + dA) a_in,ideal(t) exp(i dphi) + xi_in",
                },
                "feedback": {
                    "enabled": False,
                    "mode": "classical_readout_only",
                },
            },
            "basis_population": {
                "series_labels": ["0", "1"],
                "values": basis_values,
                "state_label": state_label,
                "hidden_state": int(hidden_state),
            },
        }
        measurements = {"records": shot_records}
        metadata = {
            "solver": str(model_spec.solver),
            "solver_impl": "cavity_classical_readout",
            "model_type": "cavity_classical_readout",
            "num_qubits": 0,
            "num_trajectories": int(ntraj),
            "hidden_state": int(hidden_state),
            "hidden_state_label": state_label,
        }
        return Trajectory(
            engine="qutip",
            times=tlist.astype(float).tolist(),
            classical=classical,
            measurements=measurements,
            metadata=metadata,
        )

    @classmethod
    def _run_homodyne_cqed_sme(
        cls,
        *,
        qt,
        H,
        rho0,
        tlist: np.ndarray,
        c_ops,
        e_ops,
        lower_ops,
        cavity_a,
        cavity_n,
        run_options: dict[str, Any],
        readout_controls: list[dict[str, Any]],
        readout_chain: dict[str, Any],
        requested_state_kind: str,
        save_times: str,
        save_final_state: bool,
    ) -> dict[str, Any]:
        nt = int(tlist.size)
        if nt <= 0:
            return {"times": [], "metadata": {}, "classical": {}, "measurements": {}}

        seed = int(run_options.get("seed", 12345))
        ntraj = max(1, int(run_options.get("ntraj", 128)))
        drive = cls._sample_readout_drive(tlist, readout_controls)
        kappa_ext_hz = max(0.0, float(readout_chain.get("kappa_ext_Hz", 0.0) or 0.0))
        kappa_ext_rad_s = 2.0 * math.pi * kappa_ext_hz
        eta_chain = float(readout_chain.get("eta_chain", 1.0) or 1.0)
        eta_chain = min(1.0, max(1.0e-6, eta_chain))
        gain_linear = 10.0 ** (float(readout_chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        measured_rate = eta_chain * kappa_ext_rad_s
        lost_rate = max(0.0, kappa_ext_rad_s - measured_rate)

        store_states = requested_state_kind in {"wave_function", "density_matrix"} and (save_times != "none" or save_final_state)
        options = cls._solver_options_with_state_storage(
            qt,
            run_options.get("qutip_options", None),
            store_states=store_states,
            keep_runs_results=True,
        )
        if isinstance(options, dict):
            options.setdefault("dt", max(float(tlist[1] - tlist[0]), 1.0e-12) if nt > 1 else 1.0e-12)
            options["store_measurement"] = True
        else:
            try:
                setattr(options, "dt", max(float(tlist[1] - tlist[0]), 1.0e-12) if nt > 1 else 1.0e-12)
                setattr(options, "store_measurement", True)
            except Exception:
                pass

        c_ops_eff = list(c_ops)
        if lost_rate > 0.0:
            c_ops_eff.append(math.sqrt(lost_rate) * cavity_a)
        sc_ops = [math.sqrt(measured_rate) * cavity_a] if measured_rate > 0.0 else []
        e_ops_all = list(e_ops) + [cavity_a, cavity_n] + list(lower_ops)
        num_primary = len(e_ops)
        num_lowering = len(lower_ops)

        try:
            if sc_ops:
                result = qt.smesolve(
                    H,
                    rho0,
                    tlist,
                    c_ops=c_ops_eff,
                    sc_ops=sc_ops,
                    heterodyne=False,
                    e_ops=e_ops_all,
                    ntraj=ntraj,
                    options=options,
                    seeds=seed,
                )
            else:
                result = qt.mesolve(H, rho0, tlist, c_ops=c_ops_eff, e_ops=e_ops_all, options=options)
        except Exception as exc:
            raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

        avg_primary = (
            np.vstack([cls._stochastic_expect_series(result, idx)[0] for idx in range(num_primary)])
            if num_primary
            else np.zeros((0, nt))
        )
        avg_cavity_a_raw, cavity_shots = cls._stochastic_expect_series(result, num_primary)
        avg_cavity_n_raw, _ = cls._stochastic_expect_series(result, num_primary + 1)
        avg_cavity_a = cls._series_to_complex(avg_cavity_a_raw)
        avg_cavity_n = cls._series_to_float(avg_cavity_n_raw)
        avg_lowering = [
            cls._series_to_complex(cls._stochastic_expect_series(result, num_primary + 2 + idx)[0])
            for idx in range(num_lowering)
        ]

        raw_measurement = getattr(result, "measurement", None)
        if raw_measurement is None:
            measurement = np.zeros((len(cavity_shots), 1, max(0, nt - 1)), dtype=float)
        else:
            measurement = np.real(np.asarray(raw_measurement, dtype=complex))
            if measurement.ndim == 2:
                measurement = measurement.reshape(measurement.shape[0], 1, measurement.shape[1])

        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        measured_shots: list[np.ndarray] = []
        coupling_scale = cls._readout_coupling_prefactor(kappa_ext_hz)

        for traj_idx, cavity_series in enumerate(cavity_shots):
            a_in = np.asarray(drive, dtype=complex).reshape(-1)
            a_out = np.asarray(
                [
                    cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext_hz)
                    for in_field, cavity_field in zip(a_in, np.asarray(cavity_series, dtype=complex).reshape(-1))
                ],
                dtype=complex,
            )
            current = cls._measurement_to_real_series(
                measurement[traj_idx, 0] if measurement.ndim >= 3 and traj_idx < measurement.shape[0] else [],
                nt,
            )
            measured_voltage = gain_linear * current.astype(complex)
            measured_shots.append(measured_voltage)
            shot_payload = {
                "a_cavity": cls._serialize_complex_series(cavity_series),
                "a_in": cls._serialize_complex_series(a_in),
                "a_out": cls._serialize_complex_series(a_out),
                "measured_voltage": cls._serialize_real_series_as_complex(np.real(measured_voltage)),
                "homodyne_current": [float(x) for x in current.tolist()],
            }
            shot_payloads.append(shot_payload)
            measurement_records.append(
                {
                    "times": tlist.astype(float).tolist(),
                    "measured_voltage": shot_payload["measured_voltage"],
                    "homodyne_current": shot_payload["homodyne_current"],
                }
            )

        avg_measured = (
            np.mean(np.asarray(measured_shots, dtype=complex), axis=0) if measured_shots else np.zeros(nt, dtype=complex)
        )
        avg_a_out = np.asarray(
            [
                cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext_hz)
                for in_field, cavity_field in zip(np.asarray(drive, dtype=complex).reshape(-1), avg_cavity_a)
            ],
            dtype=complex,
        )

        classical: dict[str, Any] = {
            "readout": {
                "schema_version": "1.0",
                "times": tlist.astype(float).tolist(),
                "chain": dict(readout_chain),
                "equations": {
                    "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>_c",
                    "measured_voltage": "I_hom(t) = gain * [sqrt(eta*kappa_ext_rad_s) * <a + a^dagger>_c + xi(t)]",
                    "quantum_drive": "H_ro(t) uses the pulse-derived a_in(t) directly as the cavity drive coefficient",
                },
                "feedback": {
                    "enabled": False,
                    "mode": "homodyne_sme",
                    "line_target_source": "none",
                    "quantum_input_source": "pulse_drive_only",
                },
                "a_in": cls._serialize_complex_series(drive),
                "cavity_a": cls._serialize_complex_series(avg_cavity_a),
                "cavity_n": [float(x) for x in avg_cavity_n.tolist()],
                "a_out": cls._serialize_complex_series(avg_a_out),
                "measured_voltage": cls._serialize_real_series_as_complex(np.real(avg_measured)),
                "qubit_lowering": [cls._serialize_complex_series(series) for series in avg_lowering],
                "shots": shot_payloads,
            }
        }
        if num_primary == 1:
            p1 = np.clip(np.real(avg_primary[0]).astype(float), 0.0, 1.0)
            classical["basis_population"] = {
                "quantity": "basis_population",
                "description": "Ensemble-averaged single-qubit basis populations from the homodyne SME trajectories.",
                "series_labels": ["0", "1"],
                "values": [[float(1.0 - val), float(val)] for val in p1.tolist()],
            }

        qstate = cls._extract_stochastic_density_trajectory(result, requested_state_kind) if store_states else None
        metadata = {
            "readout_protocol": "homodyne_sme",
            "measurement_model": "homodyne_sme",
            "solver_impl": "smesolve" if sc_ops else "mesolve",
            "homodyne_eta": eta_chain,
            "measurement_records": measurement_records,
        }
        return {
            "times": tlist.astype(float).tolist(),
            "metadata": metadata,
            "classical": classical,
            "measurements": {"records": measurement_records},
            "quantum_state_trajectory": qstate or {},
        }

    @classmethod
    def _run_heterodyne_cqed_sme(
        cls,
        *,
        qt,
        H,
        rho0,
        tlist: np.ndarray,
        c_ops,
        e_ops,
        lower_ops,
        cavity_a,
        cavity_n,
        run_options: dict[str, Any],
        readout_controls: list[dict[str, Any]],
        readout_chain: dict[str, Any],
        requested_state_kind: str,
        save_times: str,
        save_final_state: bool,
    ) -> dict[str, Any]:
        nt = int(tlist.size)
        if nt <= 0:
            return {"times": [], "metadata": {}, "classical": {}, "measurements": {}}

        seed = int(run_options.get("seed", 12345))
        ntraj = max(1, int(run_options.get("ntraj", 128)))
        drive = cls._sample_readout_drive(tlist, readout_controls)
        kappa_ext_hz = max(0.0, float(readout_chain.get("kappa_ext_Hz", 0.0) or 0.0))
        kappa_ext_rad_s = 2.0 * math.pi * kappa_ext_hz
        eta_chain = float(readout_chain.get("eta_chain", 1.0) or 1.0)
        eta_chain = min(1.0, max(1.0e-6, eta_chain))
        gain_linear = 10.0 ** (float(readout_chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        measured_rate = eta_chain * kappa_ext_rad_s
        lost_rate = max(0.0, kappa_ext_rad_s - measured_rate)

        store_states = requested_state_kind in {"wave_function", "density_matrix"} and (save_times != "none" or save_final_state)
        options = cls._solver_options_with_state_storage(
            qt,
            run_options.get("qutip_options", None),
            store_states=store_states,
            keep_runs_results=True,
        )
        if isinstance(options, dict):
            options.setdefault("dt", max(float(tlist[1] - tlist[0]), 1.0e-12) if nt > 1 else 1.0e-12)
            options["store_measurement"] = True
        else:
            try:
                setattr(options, "dt", max(float(tlist[1] - tlist[0]), 1.0e-12) if nt > 1 else 1.0e-12)
                setattr(options, "store_measurement", True)
            except Exception:
                pass

        c_ops_eff = list(c_ops)
        if lost_rate > 0.0:
            c_ops_eff.append(math.sqrt(lost_rate) * cavity_a)
        sc_ops = [math.sqrt(measured_rate) * cavity_a] if measured_rate > 0.0 else []
        e_ops_all = list(e_ops) + [cavity_a, cavity_n] + list(lower_ops)
        num_primary = len(e_ops)
        num_lowering = len(lower_ops)

        try:
            if sc_ops:
                result = qt.smesolve(
                    H,
                    rho0,
                    tlist,
                    c_ops=c_ops_eff,
                    sc_ops=sc_ops,
                    heterodyne=True,
                    e_ops=e_ops_all,
                    ntraj=ntraj,
                    options=options,
                    seeds=seed,
                )
            else:
                result = qt.mesolve(H, rho0, tlist, c_ops=c_ops_eff, e_ops=e_ops_all, options=options)
        except Exception as exc:
            raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

        avg_primary = (
            np.vstack([cls._stochastic_expect_series(result, idx)[0] for idx in range(num_primary)])
            if num_primary
            else np.zeros((0, nt))
        )
        avg_cavity_a_raw, cavity_shots = cls._stochastic_expect_series(result, num_primary)
        avg_cavity_n_raw, _ = cls._stochastic_expect_series(result, num_primary + 1)
        avg_cavity_a = cls._series_to_complex(avg_cavity_a_raw)
        avg_cavity_n = cls._series_to_float(avg_cavity_n_raw)
        avg_lowering = [
            cls._series_to_complex(cls._stochastic_expect_series(result, num_primary + 2 + idx)[0])
            for idx in range(num_lowering)
        ]

        raw_measurement = getattr(result, "measurement", None)
        if raw_measurement is None:
            measurement = np.zeros((len(cavity_shots), 1, 2, max(0, nt - 1)), dtype=float)
        else:
            measurement = np.asarray(raw_measurement)
            if measurement.ndim == 3:
                measurement = measurement.reshape(measurement.shape[0], 1, measurement.shape[1], measurement.shape[2])

        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        measured_shots: list[np.ndarray] = []

        for traj_idx, cavity_series in enumerate(cavity_shots):
            a_in = np.asarray(drive, dtype=complex).reshape(-1)
            a_out = np.asarray(
                [
                    cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext_hz)
                    for in_field, cavity_field in zip(a_in, np.asarray(cavity_series, dtype=complex).reshape(-1))
                ],
                dtype=complex,
            )
            current = cls._measurement_to_complex_series(
                measurement[traj_idx, 0] if measurement.ndim >= 4 and traj_idx < measurement.shape[0] else [],
                nt,
            )
            measured_voltage = gain_linear * current
            measured_shots.append(measured_voltage)
            shot_payload = {
                "a_cavity": cls._serialize_complex_series(cavity_series),
                "a_in": cls._serialize_complex_series(a_in),
                "a_out": cls._serialize_complex_series(a_out),
                "heterodyne_current": cls._serialize_complex_series(current),
                "heterodyne_I": [float(x) for x in np.real(current).tolist()],
                "heterodyne_Q": [float(x) for x in np.imag(current).tolist()],
                "measured_voltage": cls._serialize_complex_series(measured_voltage),
            }
            shot_payloads.append(shot_payload)
            measurement_records.append(
                {
                    "times": tlist.astype(float).tolist(),
                    "heterodyne_current": shot_payload["heterodyne_current"],
                    "heterodyne_I": shot_payload["heterodyne_I"],
                    "heterodyne_Q": shot_payload["heterodyne_Q"],
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            )

        avg_measured = (
            np.mean(np.asarray(measured_shots, dtype=complex), axis=0) if measured_shots else np.zeros(nt, dtype=complex)
        )
        avg_a_out = np.asarray(
            [
                cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext_hz)
                for in_field, cavity_field in zip(np.asarray(drive, dtype=complex).reshape(-1), avg_cavity_a)
            ],
            dtype=complex,
        )

        classical: dict[str, Any] = {
            "readout": {
                "schema_version": "1.0",
                "times": tlist.astype(float).tolist(),
                "chain": dict(readout_chain),
                "equations": {
                    "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>_c",
                    "measured_voltage": "V_IQ(t) = gain * [I_het(t) + i Q_het(t)]",
                    "heterodyne_current": "I_het(t) + i Q_het(t) from the monitored cavity leakage channel",
                    "quantum_drive": "H_ro(t) uses the pulse-derived a_in(t) directly as the cavity drive coefficient",
                },
                "feedback": {
                    "enabled": False,
                    "mode": "heterodyne_sme",
                    "line_target_source": "none",
                    "quantum_input_source": "pulse_drive_only",
                },
                "a_in": cls._serialize_complex_series(drive),
                "cavity_a": cls._serialize_complex_series(avg_cavity_a),
                "cavity_n": [float(x) for x in avg_cavity_n.tolist()],
                "a_out": cls._serialize_complex_series(avg_a_out),
                "heterodyne_current": cls._serialize_complex_series(avg_measured / max(gain_linear, 1.0e-12)),
                "measured_voltage": cls._serialize_complex_series(avg_measured),
                "qubit_lowering": [cls._serialize_complex_series(series) for series in avg_lowering],
                "shots": shot_payloads,
            }
        }
        if num_primary == 1:
            p1 = np.clip(np.real(avg_primary[0]).astype(float), 0.0, 1.0)
            classical["basis_population"] = {
                "quantity": "basis_population",
                "description": "Ensemble-averaged single-qubit basis populations from the heterodyne SME trajectories.",
                "series_labels": ["0", "1"],
                "values": [[float(1.0 - val), float(val)] for val in p1.tolist()],
            }

        qstate = cls._extract_stochastic_density_trajectory(result, requested_state_kind) if store_states else None
        metadata = {
            "readout_protocol": "heterodyne_sme",
            "measurement_model": "heterodyne_sme",
            "solver_impl": "smesolve" if sc_ops else "mesolve",
            "heterodyne_eta": eta_chain,
            "measurement_records": measurement_records,
        }
        return {
            "times": tlist.astype(float).tolist(),
            "metadata": metadata,
            "classical": classical,
            "measurements": {"records": measurement_records},
            "quantum_state_trajectory": qstate or {},
        }

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trajectory:
        """Solve model dynamics based on ``model_spec.solver``.

        Supported solvers:
        - ``se``: Schrodinger equation
        - ``me``: master equation
        - ``mcwf``: Monte-Carlo wave-function
        """
        run_options = run_options or {}
        payload = model_spec.payload or {}
        model_type = str(payload.get("model_type", "qubit_network"))

        if str(model_type).strip().lower() == "cavity_classical_readout":
            return self._run_cavity_classical_readout(model_spec=model_spec, run_options=run_options)

        try:
            import qutip as qt
        except Exception as exc:
            raise RuntimeError(f"QuTiP dependency unavailable: {exc}") from exc

        n_qubits = int(payload.get("num_qubits", 1))
        if n_qubits < 1:
            raise ValueError(f"Invalid model payload: num_qubits must be >= 1, got {n_qubits}")

        dt = max(float(model_spec.dt), 1e-12)
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
        readout_chain = self._infer_cqed_readout_params(payload, n_qubits)
        hybrid_update_mode = self._resolve_hybrid_update_mode(payload)
        readout_protocol = self._resolve_readout_protocol(payload)
        use_heterodyne_sme = (
            solver := str(model_spec.solver).lower()
        ) in {"me", "mcwf"} and self._is_cqed_model(model_type) and self._has_classical_readout_line(payload) and readout_protocol == "heterodyne_sme"
        use_homodyne_sme = (
            solver
        ) in {"me", "mcwf"} and self._is_cqed_model(model_type) and self._has_classical_readout_line(payload) and readout_protocol == "homodyne_sme"
        use_hybrid_classical_readout = (
            solver == "mcwf"
        ) and self._is_cqed_model(model_type) and self._has_classical_readout_line(payload) and not use_homodyne_sme and not use_heterodyne_sme

        cavity_a = None
        cavity_adag = None
        cavity_n = None
        hybrid_arg_store: dict[str, float] | None = None
        cavity_kappa_int = 0.0
        cavity_kappa_ext = 0.0

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
        elif self._is_cqed_model(model_type):
            levels = int(payload.get("transmon_levels", 3))
            cavity_nmax = int(payload.get("cavity_nmax", 8))
            nc = max(1, cavity_nmax + 1)
            a_c, adag_c, n_c, a_q, adag_q, n_q, x_q, y_q, psi0, e_ops = self._build_cqed_ops(qt, n_qubits, levels, cavity_nmax)
            cavity_a = a_c
            cavity_adag = adag_c
            cavity_n = n_c
            x_ops = x_q
            y_ops = y_q
            z_ops = n_q
            lower_ops = a_q
            raise_ops = adag_q
            cavity_omega_rad_s = float(payload.get("cavity_omega_rad_s", 0.0))
            if frame_mode == "rotating":
                readout_controls = list(payload.get("readout_controls", []) or [])
                for ctrl in readout_controls:
                    ref = float(ctrl.get("carrier_omega_rad_s", 0.0) or 0.0)
                    if ref != 0.0:
                        cavity_omega_rad_s = cavity_omega_rad_s - ref
                        break
            H0 = cavity_omega_rad_s * n_c
            for i in range(n_qubits):
                ni = n_q[i]
                ident = qt.qeye(ni.dims[0])
                H0 = H0 + freqs[i] * ni + 0.5 * anh[i] * (ni * (ni - ident))
            if str(model_type).strip().lower() == "cqed_jc":
                g_cavity = payload.get("g_cavity_rad_s", [0.0 for _ in range(n_qubits)])
                if len(g_cavity) < n_qubits:
                    g_cavity = list(g_cavity) + [0.0] * (n_qubits - len(g_cavity))
                for i in range(n_qubits):
                    g = float(g_cavity[i])
                    if g != 0.0:
                        H0 = H0 + g * (adag_c * a_q[i] + a_c * adag_q[i])
            chi_rad = [2.0 * math.pi * float(x) for x in readout_chain.get("chi_Hz", [0.0 for _ in range(n_qubits)])]
            if len(chi_rad) < n_qubits:
                chi_rad.extend([0.0] * (n_qubits - len(chi_rad)))
            for i in range(n_qubits):
                if chi_rad[i] != 0.0:
                    H0 = H0 + chi_rad[i] * n_c * n_q[i]
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
            axis = str(ctrl.get("axis", "x")).lower()
            if axis == "zz":
                pair = list(ctrl.get("target_pair", []) or [])
                if len(pair) < 2:
                    continue
                i, j = int(pair[0]), int(pair[1])
                if i < 0 or j < 0 or i >= n_qubits or j >= n_qubits or i == j:
                    continue
                op = z_ops[i] * z_ops[j]
                coeff_env = self._coeff_interp(
                    [float(x) for x in ctrl.get("times", [])],
                    [float(x) for x in ctrl.get("values", [])],
                    float(ctrl.get("scale", 1.0)),
                )
                H.append([op, coeff_env])
                continue

            target = int(ctrl.get("target", -1))
            if target < 0 or target >= n_qubits:
                continue
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

        if self._is_cqed_model(model_type) and cavity_a is not None and cavity_adag is not None and not use_hybrid_classical_readout:
            cavity_x = cavity_a + cavity_adag
            cavity_y = -1j * (cavity_a - cavity_adag)
            readout_drive_scale = self._readout_coupling_prefactor(readout_chain.get("kappa_ext_Hz", 0.0))
            for ctrl in payload.get("readout_controls", []):
                coeff_env = self._coeff_interp(
                    ctrl.get("times", []),
                    ctrl.get("values", []),
                    float(ctrl.get("scale", 1.0)),
                )
                phase_rad = float(ctrl.get("carrier_phase_rad", 0.0) or 0.0)
                carrier_omega_rad_s = float(ctrl.get("carrier_omega_rad_s", 0.0) or 0.0)
                if frame_mode == "rotating" and rwa:
                    H.append(
                        [
                            cavity_x,
                            lambda t, args=None, env=coeff_env, phase=phase_rad, scale=readout_drive_scale: (
                                scale * float(env(t, args)) * math.cos(phase)
                            ),
                        ]
                    )
                    H.append(
                        [
                            cavity_y,
                            lambda t, args=None, env=coeff_env, phase=phase_rad, scale=readout_drive_scale: (
                                scale * float(env(t, args)) * math.sin(phase)
                            ),
                        ]
                    )
                else:
                    scaled_env = lambda t, args=None, env=coeff_env, scale=readout_drive_scale: scale * float(env(t, args))
                    H.append(
                        [
                            cavity_x,
                            self._modulated_coeff(
                                scaled_env,
                                omega_rad_s=carrier_omega_rad_s,
                                phase_rad=phase_rad,
                                trig="cos",
                            ),
                        ]
                    )
                    H.append(
                        [
                            cavity_y,
                            self._modulated_coeff(
                                scaled_env,
                                omega_rad_s=carrier_omega_rad_s,
                                phase_rad=phase_rad,
                                trig="sin",
                            ),
                        ]
                    )
        elif self._is_cqed_model(model_type) and cavity_a is not None and cavity_adag is not None and use_hybrid_classical_readout:
            cavity_x = cavity_a + cavity_adag
            cavity_y = -1j * (cavity_a - cavity_adag)
            hybrid_arg_store = {"hybrid_ro_re": 0.0, "hybrid_ro_im": 0.0}
            H.append([cavity_x, self._arg_coeff("hybrid_ro_re", hybrid_arg_store)])
            H.append([cavity_y, self._arg_coeff("hybrid_ro_im", hybrid_arg_store)])

        c_ops = []
        if self._is_cqed_model(model_type) and cavity_a is not None:
            cavity_kappa_int = max(0.0, 2.0 * math.pi * float(readout_chain.get("kappa_int_Hz", 0.0)))
            cavity_kappa_ext = max(0.0, 2.0 * math.pi * float(readout_chain.get("kappa_ext_Hz", 0.0)))
            if cavity_kappa_int > 0.0:
                c_ops.append(math.sqrt(cavity_kappa_int) * cavity_a)
            if cavity_kappa_ext > 0.0 and not use_homodyne_sme and not use_heterodyne_sme:
                c_ops.append(math.sqrt(cavity_kappa_ext) * cavity_a)
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

        analyser_cfg = dict(payload.get("analyser", {}) or {})
        trajectory_cfg = dict(analyser_cfg.get("trajectory", {}) or {})
        requested_state_kind = str(trajectory_cfg.get("quantum", "")).strip().lower()
        if requested_state_kind not in {"wave_function", "density_matrix"}:
            requested_state_kind = "wave_function" if solver == "mcwf" else "density_matrix"
        save_times = str(trajectory_cfg.get("save_times", "all")).strip().lower()
        save_final_state = bool(trajectory_cfg.get("save_final_state", True))
        keep_runs_results = solver == "mcwf"
        store_states = requested_state_kind in {"wave_function", "density_matrix"} and (save_times != "none" or save_final_state)
        options = self._solver_options_with_state_storage(
            qt,
            run_options.get("qutip_options", None),
            store_states=store_states,
            keep_runs_results=keep_runs_results,
        )

        if solver not in {"se", "me", "mcwf"}:
            raise ValueError(f"Unsupported solver for QuTiP engine: {model_spec.solver}")

        base_e_ops = list(e_ops)
        readout_expect_ix: dict[str, Any] = {}
        if self._is_cqed_model(model_type) and cavity_a is not None and cavity_n is not None:
            readout_expect_ix["cavity_a"] = len(base_e_ops)
            base_e_ops.append(cavity_a)
            readout_expect_ix["cavity_n"] = len(base_e_ops)
            base_e_ops.append(cavity_n)
            lowering_ix: list[int] = []
            for op in lower_ops:
                lowering_ix.append(len(base_e_ops))
                base_e_ops.append(op)
            readout_expect_ix["qubit_lowering"] = lowering_ix

        if use_heterodyne_sme and cavity_a is not None and cavity_n is not None:
            try:
                heterodyne = self._run_heterodyne_cqed_sme(
                    qt=qt,
                    H=H,
                    rho0=qt.ket2dm(psi0),
                    tlist=tlist,
                    c_ops=c_ops,
                    e_ops=e_ops,
                    lower_ops=lower_ops,
                    cavity_a=cavity_a,
                    cavity_n=cavity_n,
                    run_options=run_options,
                    readout_controls=list(payload.get("readout_controls", []) or []),
                    readout_chain=readout_chain,
                    requested_state_kind=requested_state_kind,
                    save_times=save_times,
                    save_final_state=save_final_state,
                )
            except Exception as exc:
                raise RuntimeError(f"QuTiP execution failed: {exc}") from exc
            metadata = {
                "solver": solver,
                "solver_impl": "smesolve",
                "model_type": model_type,
                "num_qubits": n_qubits,
                "num_controls": len(payload.get("controls", [])),
                "num_readout_controls": len(payload.get("readout_controls", [])),
                "num_collapse_ops": len(c_ops),
                "selected_noise": selected_noise,
                "frame_mode": frame_mode,
                "rwa": rwa,
                "readout_protocol": readout_protocol,
            }
            metadata.update(dict(heterodyne.get("metadata", {}) or {}))
            qstate = dict(heterodyne.get("quantum_state_trajectory", {}) or {})
            wave_function, density_matrix = self._quantum_payloads(qstate)
            return Trajectory(
                engine="qutip",
                times=list(heterodyne.get("times", tlist.astype(float).tolist()) or []),
                wave_function=wave_function,
                density_matrix=density_matrix,
                classical=dict(heterodyne.get("classical", {}) or {}),
                measurements=dict(heterodyne.get("measurements", {}) or {}),
                metadata=metadata,
            )

        if use_homodyne_sme and cavity_a is not None and cavity_n is not None:
            try:
                homodyne = self._run_homodyne_cqed_sme(
                    qt=qt,
                    H=H,
                    rho0=qt.ket2dm(psi0),
                    tlist=tlist,
                    c_ops=c_ops,
                    e_ops=e_ops,
                    lower_ops=lower_ops,
                    cavity_a=cavity_a,
                    cavity_n=cavity_n,
                    run_options=run_options,
                    readout_controls=list(payload.get("readout_controls", []) or []),
                    readout_chain=readout_chain,
                    requested_state_kind=requested_state_kind,
                    save_times=save_times,
                    save_final_state=save_final_state,
                )
            except Exception as exc:
                raise RuntimeError(f"QuTiP execution failed: {exc}") from exc
            metadata = {
                "solver": solver,
                "solver_impl": "smesolve",
                "model_type": model_type,
                "num_qubits": n_qubits,
                "num_controls": len(payload.get("controls", [])),
                "num_readout_controls": len(payload.get("readout_controls", [])),
                "num_collapse_ops": len(c_ops),
                "selected_noise": selected_noise,
                "frame_mode": frame_mode,
                "rwa": rwa,
                "readout_protocol": readout_protocol,
            }
            metadata.update(dict(homodyne.get("metadata", {}) or {}))
            qstate = dict(homodyne.get("quantum_state_trajectory", {}) or {})
            wave_function, density_matrix = self._quantum_payloads(qstate)
            return Trajectory(
                engine="qutip",
                times=list(homodyne.get("times", tlist.astype(float).tolist()) or []),
                wave_function=wave_function,
                density_matrix=density_matrix,
                classical=dict(homodyne.get("classical", {}) or {}),
                measurements=dict(homodyne.get("measurements", {}) or {}),
                metadata=metadata,
            )

        if use_hybrid_classical_readout and cavity_a is not None and cavity_n is not None:
            try:
                hybrid = self._run_hybrid_cqed_mcwf(
                    qt=qt,
                    H=H,
                    psi0=psi0,
                    tlist=tlist,
                    c_ops=c_ops,
                    e_ops=e_ops,
                    lower_ops=lower_ops,
                    cavity_a=cavity_a,
                    cavity_n=cavity_n,
                    run_options=run_options,
                    readout_controls=list(payload.get("readout_controls", []) or []),
                    readout_chain=readout_chain,
                    requested_state_kind=requested_state_kind,
                    save_times=save_times,
                    save_final_state=save_final_state,
                    hybrid_update_mode=hybrid_update_mode,
                    hybrid_arg_store=hybrid_arg_store,
                )
            except Exception as exc:
                raise RuntimeError(f"QuTiP execution failed: {exc}") from exc
            metadata = {
                "solver": solver,
                "model_type": model_type,
                "num_qubits": n_qubits,
                "num_controls": len(payload.get("controls", [])),
                "num_readout_controls": len(payload.get("readout_controls", [])),
                "num_collapse_ops": len(c_ops),
                "selected_noise": selected_noise,
                "frame_mode": frame_mode,
                "rwa": rwa,
                "hybrid_update_mode": hybrid_update_mode,
            }
            metadata.update(dict(hybrid.get("metadata", {}) or {}))
            wave_function = None
            density_matrix = None
            qstate = dict(hybrid.get("quantum_state_trajectory", {}) or {})
            if not qstate:
                qstate = dict(metadata.pop("quantum_state_trajectory", {}) or {})
            wave_function, density_matrix = self._quantum_payloads(qstate)
            return Trajectory(
                engine="qutip",
                times=list(hybrid.get("times", tlist.astype(float).tolist()) or []),
                wave_function=wave_function,
                density_matrix=density_matrix,
                metadata=metadata,
            )

        try:
            if solver == "se":
                result = qt.sesolve(H, psi0, tlist, e_ops=base_e_ops, options=options)
            elif solver == "me":
                result = qt.mesolve(H, psi0, tlist, c_ops=c_ops, e_ops=base_e_ops, options=options)
            else:
                ntraj = int(run_options.get("ntraj", 128))
                result = qt.mcsolve(H, psi0, tlist, c_ops=c_ops, e_ops=base_e_ops, ntraj=ntraj, options=options)
        except Exception as exc:
            raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

        quantum_state_trajectory = self._extract_quantum_state_trajectory(result, solver, requested_state_kind)
        wave_function, density_matrix = self._quantum_payloads(quantum_state_trajectory)
        metadata = {
            "solver": solver,
            "model_type": model_type,
            "num_qubits": n_qubits,
            "num_controls": len(payload.get("controls", [])),
            "num_readout_controls": len(payload.get("readout_controls", [])),
            "num_collapse_ops": len(c_ops),
            "selected_noise": selected_noise,
            "frame_mode": frame_mode,
            "rwa": rwa,
        }
        if self._is_cqed_model(model_type) and "cavity_a" in readout_expect_ix:
            cavity_a_series = self._series_to_complex(self._average_expect_series(result.expect[readout_expect_ix["cavity_a"]]))
            cavity_n_series = self._series_to_float(self._average_expect_series(result.expect[readout_expect_ix["cavity_n"]])).tolist()
            qubit_lowering_series = [
                self._serialize_complex_series(self._series_to_complex(self._average_expect_series(result.expect[ix])))
                for ix in readout_expect_ix.get("qubit_lowering", [])
            ]
            shot_cavity = []
            if solver == "mcwf":
                shot_cavity = [
                    self._series_to_complex(values)
                    for values in self._shot_expectation_series(result.expect[readout_expect_ix["cavity_a"]])
                ]
            drive = self._sample_readout_drive(tlist, list(payload.get("readout_controls", []) or []))
            classical_line = self._simulate_classical_readout(
                tlist=tlist,
                drive=drive,
                cavity_avg=cavity_a_series,
                cavity_shots=shot_cavity,
                chain=readout_chain,
                seed=seed,
            )
            average_line = dict(classical_line.get("average", {}) or {})
            metadata["readout_observables"] = {
                "schema_version": "1.0",
                "times": tlist.astype(float).tolist(),
                "chain": readout_chain,
                "equations": {
                    "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>",
                    "line_state": "d alpha_line / dt = -(gamma_line/2 + i Delta_line) alpha_line + gamma_line * a_out + xi_thermal",
                    "measured_voltage": "V_IQ(t) = gain * alpha_line(t) + xi_meas(t)",
                    "quantum_drive": "readout drive is sampled directly from the pulse envelope for non-hybrid replay",
                },
                "feedback": {
                    "enabled": False,
                    "mode": "postprocessed_classical_line",
                    "line_target_source": "a_out",
                    "quantum_input_source": "pulse_drive_only",
                },
                "a_in": self._serialize_complex_series(np.asarray(average_line.get("a_in", drive), dtype=complex)),
                "cavity_a": self._serialize_complex_series(cavity_a_series),
                "cavity_n": cavity_n_series,
                "a_out": self._serialize_complex_series(np.asarray(average_line.get("a_out", drive - cavity_a_series), dtype=complex)),
                "line_state": self._serialize_complex_series(np.asarray(average_line.get("line_state", np.zeros_like(cavity_a_series)), dtype=complex)),
                "measured_voltage": self._serialize_complex_series(
                    np.asarray(average_line.get("measured_voltage", np.zeros_like(cavity_a_series)), dtype=complex)
                ),
                "qubit_lowering": qubit_lowering_series,
                "shots": list(classical_line.get("shots", []) or []),
            }

        return Trajectory(
            engine="qutip",
            times=tlist.astype(float).tolist(),
            wave_function=wave_function,
            density_matrix=density_matrix,
            metadata=metadata,
        )

