"""Quantum-classical coupled CQED dynamics for the QuTiP engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from qsim.engines.qutip.measurement import _control_attr
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


@dataclass(frozen=True)
class _HybridContext:
    qt: Any
    psi0: Any
    tlist: np.ndarray
    c_ops: list[Any]
    solver_options: Any
    step_hamiltonian: Any
    drive_source: np.ndarray
    readout_chain: dict[str, Any]
    requested_state_kind: str
    save_times: str
    save_final_state: bool
    hybrid_update_mode: str
    hybrid_arg_store: dict[str, float] | None
    nt: int
    seed: int
    ntraj: int
    dt: float
    kappa_ext_hz: float
    gamma_line: float
    line_detuning_rad: float
    gain_linear: float
    thermal_sigma: float
    measurement_sigma: float
    coupling_scale: float
    e_ops_all: list[Any]
    num_primary: int
    num_lowering: int


class QutipHybridDynamicsMixin:
    """Run quantum-classical coupled CQED readout dynamics."""

    @classmethod
    def _run_hybrid_cqed_mcwf(
        cls,
        *,
        setup: QutipPlan,
        system: QutipSystem,
        solver_inputs: QutipSolverInputs,
        trajectory_cfg: QutipTrajectoryRequest,
    ) -> dict[str, Any]:
        ctx = cls._prepare_hybrid_context(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )
        if ctx.nt <= 0:
            return {"times": [], "states": [], "metadata": {}}

        avg_primary = np.zeros((ctx.num_primary, ctx.nt), dtype=float)
        avg_cavity_a = np.zeros(ctx.nt, dtype=complex)
        avg_cavity_n = np.zeros(ctx.nt, dtype=float)
        avg_a_in = np.zeros(ctx.nt, dtype=complex)
        avg_a_out = np.zeros(ctx.nt, dtype=complex)
        avg_line = np.zeros(ctx.nt, dtype=complex)
        avg_measured = np.zeros(ctx.nt, dtype=complex)
        avg_lowering = [np.zeros(ctx.nt, dtype=complex) for _ in range(ctx.num_lowering)]
        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        first_snapshots: list[dict[str, Any]] = []

        for traj in range(ctx.ntraj):
            traj_seed = ctx.seed + 7919 * traj
            traj_rng = np.random.default_rng(traj_seed)
            if ctx.c_ops:
                solver_obj = ctx.qt.MCSolver(ctx.step_hamiltonian, ctx.c_ops, options=ctx.solver_options)
            else:
                solver_obj = ctx.qt.SESolver(ctx.step_hamiltonian, options=ctx.solver_options)

            state = ctx.psi0.copy()
            traj_primary = np.zeros((ctx.num_primary, ctx.nt), dtype=float)
            traj_cavity_a = np.zeros(ctx.nt, dtype=complex)
            traj_cavity_n = np.zeros(ctx.nt, dtype=float)
            traj_a_in = np.zeros(ctx.nt, dtype=complex)
            traj_a_out = np.zeros(ctx.nt, dtype=complex)
            traj_line = np.zeros(ctx.nt, dtype=complex)
            traj_measured = np.zeros(ctx.nt, dtype=complex)
            traj_lowering = [np.zeros(ctx.nt, dtype=complex) for _ in range(ctx.num_lowering)]

            line_state = complex(ctx.drive_source[0]) if ctx.nt > 0 else 0.0j

            def _measurement_noise() -> complex:
                return ctx.measurement_sigma * math.sqrt(ctx.dt) * (
                    float(traj_rng.normal()) + 1j * float(traj_rng.normal())
                ) / math.sqrt(2.0)

            def _thermal_kick() -> complex:
                return ctx.thermal_sigma * math.sqrt(ctx.dt) * (
                    float(traj_rng.normal()) + 1j * float(traj_rng.normal())
                ) / math.sqrt(2.0)

            obs0 = np.asarray(ctx.qt.expect(ctx.e_ops_all, state), dtype=complex).reshape(-1)
            traj_primary[:, 0] = np.real(obs0[: ctx.num_primary]).astype(float)
            traj_cavity_a[0] = complex(obs0[ctx.num_primary])
            traj_cavity_n[0] = float(np.real(obs0[ctx.num_primary + 1]))
            for idx in range(ctx.num_lowering):
                traj_lowering[idx][0] = complex(obs0[ctx.num_primary + 2 + idx])
            traj_line[0] = line_state
            traj_a_in[0] = line_state
            traj_a_out[0] = cls._input_output_a_out(
                a_in=line_state,
                cavity_field=traj_cavity_a[0],
                kappa_ext_hz=ctx.kappa_ext_hz,
            )
            traj_measured[0] = ctx.gain_linear * traj_a_out[0] + _measurement_noise()

            if traj == 0 and ctx.requested_state_kind == "wave_function" and ctx.save_times != "none":
                first_snapshots.append(cls._serialize_qobj_state(state))

            for k in range(ctx.nt - 1):
                if ctx.c_ops:
                    solver_obj.start(state, float(ctx.tlist[k]), seed=traj_seed + k)
                else:
                    solver_obj.start(state, float(ctx.tlist[k]))
                thermal_noise = _thermal_kick()
                if ctx.hybrid_update_mode == "predictor_corrector":
                    line_target_pred = cls._input_output_a_out(
                        a_in=complex(ctx.drive_source[k + 1]),
                        cavity_field=traj_cavity_a[k],
                        kappa_ext_hz=ctx.kappa_ext_hz,
                    )
                    line_pred = cls._advance_line_state(
                        line_state,
                        line_target=line_target_pred,
                        dt=ctx.dt,
                        gamma_line=ctx.gamma_line,
                        line_detuning_rad=ctx.line_detuning_rad,
                        thermal_noise=0.0j,
                    )
                    line_for_quantum = 0.5 * (line_state + line_pred)
                else:
                    line_for_quantum = line_state

                if ctx.hybrid_arg_store is not None:
                    ctx.hybrid_arg_store["hybrid_ro_re"] = float(ctx.coupling_scale * np.real(line_for_quantum))
                    ctx.hybrid_arg_store["hybrid_ro_im"] = float(ctx.coupling_scale * np.imag(line_for_quantum))
                args = {
                    "hybrid_ro_re": float(ctx.coupling_scale * np.real(line_for_quantum)),
                    "hybrid_ro_im": float(ctx.coupling_scale * np.imag(line_for_quantum)),
                }
                state = solver_obj.step(float(ctx.tlist[k + 1]), args=args)
                obs_pre = np.asarray(ctx.qt.expect(ctx.e_ops_all, state), dtype=complex).reshape(-1)
                cavity_field_pre = complex(obs_pre[ctx.num_primary])

                traj_a_in[k + 1] = line_for_quantum
                traj_a_out[k + 1] = cls._input_output_a_out(
                    a_in=line_for_quantum,
                    cavity_field=cavity_field_pre,
                    kappa_ext_hz=ctx.kappa_ext_hz,
                )

                line_target = cls._input_output_a_out(
                    a_in=complex(ctx.drive_source[k + 1]),
                    cavity_field=cavity_field_pre,
                    kappa_ext_hz=ctx.kappa_ext_hz,
                )
                line_state = cls._advance_line_state(
                    line_state,
                    line_target=line_target,
                    dt=ctx.dt,
                    gamma_line=ctx.gamma_line,
                    line_detuning_rad=ctx.line_detuning_rad,
                    thermal_noise=thermal_noise,
                )
                traj_line[k + 1] = line_state
                traj_measured[k + 1] = ctx.gain_linear * line_state + _measurement_noise()

                obs = np.asarray(ctx.qt.expect(ctx.e_ops_all, state), dtype=complex).reshape(-1)
                traj_primary[:, k + 1] = np.real(obs[: ctx.num_primary]).astype(float)
                traj_cavity_a[k + 1] = complex(obs[ctx.num_primary])
                traj_cavity_n[k + 1] = float(np.real(obs[ctx.num_primary + 1]))
                for idx in range(ctx.num_lowering):
                    traj_lowering[idx][k + 1] = complex(obs[ctx.num_primary + 2 + idx])

                if traj == 0 and ctx.requested_state_kind == "wave_function" and ctx.save_times != "none":
                    first_snapshots.append(cls._serialize_qobj_state(state))

            if (
                traj == 0
                and ctx.requested_state_kind == "wave_function"
                and ctx.save_times == "none"
                and ctx.save_final_state
            ):
                first_snapshots.append(cls._serialize_qobj_state(state))

            avg_primary += traj_primary
            avg_cavity_a += traj_cavity_a
            avg_cavity_n += traj_cavity_n
            avg_a_in += traj_a_in
            avg_a_out += traj_a_out
            avg_line += traj_line
            avg_measured += traj_measured
            for idx in range(ctx.num_lowering):
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
                    "times": ctx.tlist.astype(float).tolist(),
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            )

        return cls._build_hybrid_readout_result(
            context=ctx,
            avg_primary=avg_primary,
            avg_cavity_a=avg_cavity_a,
            avg_cavity_n=avg_cavity_n,
            avg_a_in=avg_a_in,
            avg_a_out=avg_a_out,
            avg_line=avg_line,
            avg_measured=avg_measured,
            avg_lowering=avg_lowering,
            shot_payloads=shot_payloads,
            measurement_records=measurement_records,
            first_snapshots=first_snapshots,
        )

    @classmethod
    def _prepare_hybrid_context(
        cls,
        *,
        setup: QutipPlan,
        system: QutipSystem,
        solver_inputs: QutipSolverInputs,
        trajectory_cfg: QutipTrajectoryRequest,
    ) -> _HybridContext:
        qt = setup.qt
        H = system.H
        psi0 = system.psi0
        tlist = setup.tlist
        c_ops = solver_inputs.c_ops
        e_ops = system.e_ops
        lower_ops = system.lower_ops
        cavity_a = system.cavity_a
        cavity_n = system.cavity_n
        run_config = setup.run_config
        readout_controls = list(setup.readout_controls or [])
        readout_chain = setup.readout_chain
        requested_state_kind = trajectory_cfg.requested_state_kind
        save_times = trajectory_cfg.save_times
        save_final_state = trajectory_cfg.save_final_state
        hybrid_update_mode = setup.hybrid_update_mode
        hybrid_arg_store = system.hybrid_arg_store
        nt = int(tlist.size)

        seed = int(run_config.seed)
        ntraj = max(1, int(run_config.ntraj))
        dt = max(1.0e-18, float(tlist[1] - tlist[0])) if nt > 1 else 1.0
        solver_options = cls._solver_options_with_state_storage(
            qt,
            run_config.qutip_options,
            store_states=False,
            keep_runs_results=False,
        )
        step_hamiltonian = qt.QobjEvo(H)
        drive_source = cls._sample_readout_drive(tlist, readout_controls)
        readout_carrier_hz = 0.0
        for ctrl in readout_controls:
            readout_carrier_hz = float(_control_attr(ctrl, "carrier_freq_Hz", 0.0) or 0.0)
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
        return _HybridContext(
            qt=qt,
            psi0=psi0,
            tlist=tlist,
            c_ops=c_ops,
            solver_options=solver_options,
            step_hamiltonian=step_hamiltonian,
            drive_source=drive_source,
            readout_chain=readout_chain,
            requested_state_kind=requested_state_kind,
            save_times=save_times,
            save_final_state=save_final_state,
            hybrid_update_mode=hybrid_update_mode,
            hybrid_arg_store=hybrid_arg_store,
            nt=nt,
            seed=seed,
            ntraj=ntraj,
            dt=dt,
            kappa_ext_hz=kappa_ext_hz,
            gamma_line=gamma_line,
            line_detuning_rad=line_detuning_rad,
            gain_linear=gain_linear,
            thermal_sigma=thermal_sigma,
            measurement_sigma=measurement_sigma,
            coupling_scale=coupling_scale,
            e_ops_all=e_ops_all,
            num_primary=num_primary,
            num_lowering=num_lowering,
        )

    @classmethod
    def _build_hybrid_readout_result(
        cls,
        *,
        context: _HybridContext,
        avg_primary: np.ndarray,
        avg_cavity_a: np.ndarray,
        avg_cavity_n: np.ndarray,
        avg_a_in: np.ndarray,
        avg_a_out: np.ndarray,
        avg_line: np.ndarray,
        avg_measured: np.ndarray,
        avg_lowering: list[np.ndarray],
        shot_payloads: list[dict[str, Any]],
        measurement_records: list[dict[str, Any]],
        first_snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        norm = 1.0 / float(context.ntraj)
        avg_primary *= norm
        avg_cavity_a *= norm
        avg_cavity_n *= norm
        avg_a_in *= norm
        avg_a_out *= norm
        avg_line *= norm
        avg_measured *= norm
        avg_lowering = [series * norm for series in avg_lowering]

        states = [
            [float(np.clip(avg_primary[q, k], 0.0, 1.0)) for q in range(context.num_primary)]
            for k in range(int(context.tlist.size))
        ]
        metadata = {
            "hybrid_update_mode": context.hybrid_update_mode,
            "measurement_records": measurement_records,
            "readout_observables": {
                "schema_version": "1.0",
                "times": context.tlist.astype(float).tolist(),
                "chain": dict(context.readout_chain),
                "equations": {
                    "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>",
                    "line_state": "d alpha_line / dt = -(gamma_line/2 + i Delta_line) alpha_line + gamma_line * a_out + xi_thermal",
                    "measured_voltage": "V_IQ(t) = gain * alpha_line(t) + xi_meas(t)",
                    "quantum_drive": "H_ro(t) uses sqrt(kappa_ext_rad_s) * a_in(t) as the cavity drive coefficient",
                },
                "feedback": {
                    "enabled": True,
                    "mode": context.hybrid_update_mode,
                    "line_target_source": "a_out",
                    "quantum_input_source": (
                        "line_state"
                        if context.hybrid_update_mode != "predictor_corrector"
                        else "0.5 * (line_state + predicted_line_state)"
                    ),
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
            requested_kind=context.requested_state_kind,
            actual_kind="wave_function",
        )
        if quantum_state_trajectory is not None:
            metadata["quantum_state_trajectory"] = quantum_state_trajectory
        return {
            "times": context.tlist.astype(float).tolist(),
            "states": states,
            "metadata": metadata,
        }


