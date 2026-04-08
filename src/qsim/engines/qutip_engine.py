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

    @staticmethod
    def _sample_readout_drive(tlist: np.ndarray, controls: list[dict[str, Any]]) -> np.ndarray:
        drive = np.zeros_like(tlist, dtype=complex)
        for ctrl in controls:
            times = [float(x) for x in ctrl.get("times", [])]
            values = [float(x) for x in ctrl.get("values", [])]
            if not times or not values:
                continue
            env = np.interp(tlist, np.asarray(times, dtype=float), np.asarray(values, dtype=float), left=values[0], right=values[-1])
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
    def _complex_vector(values) -> list[complex]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [complex(float(v.real), float(v.imag)) for v in arr]

    @classmethod
    def _serialize_complex_series(cls, values) -> list[list[float]]:
        arr = np.asarray(values, dtype=complex).reshape(-1)
        return [[float(v.real), float(v.imag)] for v in arr]

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

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trajectory:
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
        readout_chain = self._infer_cqed_readout_params(payload, n_qubits)
        hybrid_update_mode = self._resolve_hybrid_update_mode(payload)
        use_hybrid_classical_readout = (
            solver := str(model_spec.solver).lower()
        ) == "mcwf" and self._is_cqed_model(model_type) and self._has_classical_readout_line(payload)

        cavity_a = None
        cavity_adag = None
        cavity_n = None
        hybrid_arg_store: dict[str, float] | None = None

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

        if self._is_cqed_model(model_type) and cavity_a is not None and cavity_adag is not None and not use_hybrid_classical_readout:
            cavity_drive_op = cavity_a + cavity_adag
            for ctrl in payload.get("readout_controls", []):
                coeff_env = self._coeff_interp(
                    ctrl.get("times", []),
                    ctrl.get("values", []),
                    float(ctrl.get("scale", 1.0)),
                )
                H.append([cavity_drive_op, coeff_env])
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
            if cavity_kappa_ext > 0.0:
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

