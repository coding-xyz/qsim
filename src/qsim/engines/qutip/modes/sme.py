"""Stochastic master-equation solver mode for monitored QuTiP readout."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from qsim.common.schemas import Trajectory
from qsim.engines.qutip.modes.common import base_metadata
from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem, QutipTrajectoryRequest


@dataclass(frozen=True)
class _SmeProtocol:
    name: str
    solver_kind: str
    eta_metadata_key: str
    heterodyne: bool = False


@dataclass(frozen=True)
class _SmeContext:
    nt: int
    seed: int
    ntraj: int
    drive: np.ndarray
    kappa_ext_hz: float
    eta_chain: float
    gain_linear: float
    measured_rate: float
    store_states: bool
    options: Any
    c_ops_eff: list[Any]
    sc_ops: list[Any]
    monitored_collapse_index: int
    e_ops_all: list[Any]
    num_primary: int
    num_lowering: int


@dataclass(frozen=True)
class _SmeSeries:
    avg_primary: np.ndarray
    avg_cavity_a: np.ndarray
    avg_cavity_n: np.ndarray
    avg_lowering: list[np.ndarray]
    cavity_shots: list[Any]


@dataclass(frozen=True)
class _SmeRecords:
    shot_payloads: list[dict[str, Any]]
    measurement_records: list[dict[str, Any]]
    measurements: dict[str, Any]


_SME_PROTOCOLS: dict[str, _SmeProtocol] = {
    "homodyne_sme": _SmeProtocol(
        name="homodyne_sme",
        solver_kind="diffusive",
        eta_metadata_key="homodyne_eta",
        heterodyne=False,
    ),
    "heterodyne_sme": _SmeProtocol(
        name="heterodyne_sme",
        solver_kind="diffusive",
        eta_metadata_key="heterodyne_eta",
        heterodyne=True,
    ),
    "photon_counting_sme": _SmeProtocol(
        name="photon_counting_sme",
        solver_kind="counting",
        eta_metadata_key="photon_counting_eta",
    ),
}


def run_monitored_sme(
    *,
    engine,
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    trajectory_cfg: QutipTrajectoryRequest,
) -> Trajectory:
    """Run the selected monitored CQED SME protocol."""
    try:
        monitored = engine._run_cqed_sme(
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )
    except Exception as exc:
        raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

    metadata = base_metadata(setup, solver_inputs)
    metadata["readout_protocol"] = setup.readout_protocol
    metadata.update(dict(monitored.get("metadata", {}) or {}))
    qstate = dict(monitored.get("quantum_state_trajectory", {}) or {})
    wave_function, density_matrix = engine._quantum_payloads(qstate)
    return Trajectory(
        engine="qutip",
        times=list(monitored.get("times", setup.tlist.astype(float).tolist()) or []),
        wave_function=wave_function,
        density_matrix=density_matrix,
        classical=dict(monitored.get("classical", {}) or {}),
        measurements=dict(monitored.get("measurements", {}) or {}),
        metadata=metadata,
    )


class QutipSmeMixin:
    """Run monitored CQED SME protocols and format their records."""

    @classmethod
    def _run_cqed_sme(
        cls,
        *,
        setup: QutipPlan,
        system: QutipSystem,
        solver_inputs: QutipSolverInputs,
        trajectory_cfg: QutipTrajectoryRequest,
    ) -> dict[str, Any]:
        """Run CQED monitored-readout trajectories for a resolved protocol."""
        protocol = setup.readout_protocol
        spec = _SME_PROTOCOLS.get(protocol)
        if spec is None:
            raise ValueError(f"Unsupported CQED readout protocol: {protocol}")
        return cls._run_monitored_cqed_sme(
            protocol=spec,
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )

    @classmethod
    def _run_monitored_cqed_sme(
        cls,
        *,
        protocol: _SmeProtocol,
        setup: QutipPlan,
        system: QutipSystem,
        solver_inputs: QutipSolverInputs,
        trajectory_cfg: QutipTrajectoryRequest,
    ) -> dict[str, Any]:
        qt = setup.qt
        tlist = setup.tlist
        nt = int(tlist.size)
        if nt <= 0:
            return {"times": [], "metadata": {}, "classical": {}, "measurements": {}}

        ctx = cls._prepare_sme_context(
            protocol=protocol,
            setup=setup,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )

        result, solver_impl = cls._solve_monitored_sme(
            protocol=protocol,
            qt=qt,
            H=system.H,
            psi0=system.psi0,
            rho0=qt.ket2dm(system.psi0),
            tlist=tlist,
            context=ctx,
        )
        series = cls._extract_sme_expectations(result, ctx.num_primary, ctx.num_lowering, nt)

        if protocol.solver_kind == "counting":
            records = cls._build_counting_records(
                result=result,
                tlist=tlist,
                context=ctx,
                series=series,
            )
        else:
            records = cls._build_diffusive_records(
                protocol=protocol,
                result=result,
                tlist=tlist,
                context=ctx,
                series=series,
            )

        classical = cls._build_sme_classical_payload(
                protocol=protocol,
                tlist=tlist,
                readout_chain=setup.readout_chain,
                context=ctx,
                series=series,
                record_bundle=records,
            )
        cls._attach_sme_basis_population(
            protocol=protocol,
            classical=classical,
            avg_primary=series.avg_primary,
            num_primary=ctx.num_primary,
        )

        if ctx.store_states and protocol.solver_kind == "counting":
            qstate = cls._extract_quantum_state_trajectory(result, "mcwf", trajectory_cfg.requested_state_kind)
        elif ctx.store_states:
            qstate = cls._extract_stochastic_density_trajectory(result, trajectory_cfg.requested_state_kind)
        else:
            qstate = None

        metadata = {
            "readout_protocol": protocol.name,
            "measurement_model": protocol.name,
            "solver_impl": solver_impl,
            protocol.eta_metadata_key: ctx.eta_chain,
            "measurement_records": records.measurement_records,
        }
        if protocol.solver_kind == "counting":
            metadata["monitored_collapse_index"] = (
                ctx.monitored_collapse_index if ctx.measured_rate > 0.0 else None
            )

        return {
            "times": tlist.astype(float).tolist(),
            "metadata": metadata,
            "classical": classical,
            "measurements": {"records": records.measurement_records},
            "quantum_state_trajectory": qstate or {},
        }

    @classmethod
    def _prepare_sme_context(
        cls,
        *,
        protocol: _SmeProtocol,
        setup: QutipPlan,
        system: QutipSystem,
        solver_inputs: QutipSolverInputs,
        trajectory_cfg: QutipTrajectoryRequest,
    ) -> _SmeContext:
        qt = setup.qt
        tlist = setup.tlist
        run_config = setup.run_config
        readout_chain = setup.readout_chain
        nt = int(tlist.size)
        seed = int(run_config.seed)
        ntraj = max(1, int(run_config.ntraj))
        drive = cls._sample_readout_drive(tlist, list(setup.readout_controls or []))
        kappa_ext_hz = max(0.0, float(readout_chain.get("kappa_ext_Hz", 0.0) or 0.0))
        kappa_ext_rad_s = 2.0 * math.pi * kappa_ext_hz
        eta_chain = float(readout_chain.get("eta_chain", 1.0) or 1.0)
        eta_chain = min(1.0, max(1.0e-6, eta_chain))
        gain_linear = 10.0 ** (float(readout_chain.get("gain_dB", 0.0) or 0.0) / 20.0)
        measured_rate = eta_chain * kappa_ext_rad_s
        lost_rate = max(0.0, kappa_ext_rad_s - measured_rate)
        store_states = trajectory_cfg.requested_state_kind in {"wave_function", "density_matrix"} and (
            trajectory_cfg.save_times != "none" or trajectory_cfg.save_final_state
        )

        options = cls._solver_options_with_state_storage(
            qt,
            run_config.qutip_options,
            store_states=store_states,
            keep_runs_results=True,
        )
        if protocol.solver_kind == "diffusive":
            cls._enable_sme_measurement_storage(options, tlist)

        c_ops_eff = list(solver_inputs.c_ops)
        if lost_rate > 0.0:
            c_ops_eff.append(math.sqrt(lost_rate) * system.cavity_a)

        sc_ops = []
        monitored_ix = len(c_ops_eff)
        if measured_rate > 0.0:
            monitored_op = math.sqrt(measured_rate) * system.cavity_a
            if protocol.solver_kind == "counting":
                c_ops_eff.append(monitored_op)
            else:
                sc_ops = [monitored_op]

        e_ops = list(system.e_ops)
        lower_ops = list(system.lower_ops)
        return _SmeContext(
            nt=nt,
            seed=seed,
            ntraj=ntraj,
            drive=drive,
            kappa_ext_hz=kappa_ext_hz,
            eta_chain=eta_chain,
            gain_linear=gain_linear,
            measured_rate=measured_rate,
            store_states=store_states,
            options=options,
            c_ops_eff=c_ops_eff,
            sc_ops=sc_ops,
            monitored_collapse_index=monitored_ix,
            e_ops_all=e_ops + [system.cavity_a, system.cavity_n] + lower_ops,
            num_primary=len(e_ops),
            num_lowering=len(lower_ops),
        )

    @staticmethod
    def _enable_sme_measurement_storage(options, tlist: np.ndarray) -> None:
        dt = max(float(tlist[1] - tlist[0]), 1.0e-12) if int(tlist.size) > 1 else 1.0e-12
        if isinstance(options, dict):
            options.setdefault("dt", dt)
            options["store_measurement"] = True
            return
        try:
            setattr(options, "dt", dt)
            setattr(options, "store_measurement", True)
        except Exception:
            pass

    @classmethod
    def _solve_monitored_sme(
        cls,
        *,
        protocol: _SmeProtocol,
        qt,
        H,
        psi0,
        rho0,
        tlist: np.ndarray,
        context: _SmeContext,
    ):
        try:
            if protocol.solver_kind == "counting" and context.measured_rate > 0.0:
                return (
                    qt.mcsolve(
                        H,
                        psi0,
                        tlist,
                        c_ops=context.c_ops_eff,
                        e_ops=context.e_ops_all,
                        ntraj=context.ntraj,
                        options=context.options,
                        seeds=context.seed,
                    ),
                    "mcsolve",
                )
            if protocol.solver_kind == "diffusive" and context.sc_ops:
                return (
                    qt.smesolve(
                        H,
                        rho0,
                        tlist,
                        c_ops=context.c_ops_eff,
                        sc_ops=context.sc_ops,
                        heterodyne=protocol.heterodyne,
                        e_ops=context.e_ops_all,
                        ntraj=context.ntraj,
                        options=context.options,
                        seeds=context.seed,
                    ),
                    "smesolve",
            )
            return (
                qt.mesolve(
                    H,
                    rho0,
                    tlist,
                    c_ops=context.c_ops_eff,
                    e_ops=context.e_ops_all,
                    options=context.options,
                ),
                "mesolve",
            )
        except Exception as exc:
            raise RuntimeError(f"QuTiP execution failed: {exc}") from exc

    @classmethod
    def _extract_sme_expectations(
        cls,
        result,
        num_primary: int,
        num_lowering: int,
        nt: int,
    ) -> _SmeSeries:
        avg_primary = (
            np.vstack([cls._stochastic_expect_series(result, idx)[0] for idx in range(num_primary)])
            if num_primary
            else np.zeros((0, nt))
        )
        avg_cavity_a_raw, cavity_shots = cls._stochastic_expect_series(result, num_primary)
        avg_cavity_n_raw, _ = cls._stochastic_expect_series(result, num_primary + 1)
        return _SmeSeries(
            avg_primary=avg_primary,
            avg_cavity_a=cls._series_to_complex(avg_cavity_a_raw),
            avg_cavity_n=cls._series_to_float(avg_cavity_n_raw),
            avg_lowering=[
                cls._series_to_complex(cls._stochastic_expect_series(result, num_primary + 2 + idx)[0])
                for idx in range(num_lowering)
            ],
            cavity_shots=cavity_shots,
        )

    @classmethod
    def _build_diffusive_records(
        cls,
        *,
        protocol: _SmeProtocol,
        result,
        tlist: np.ndarray,
        context: _SmeContext,
        series: _SmeSeries,
    ) -> _SmeRecords:
        nt = context.nt
        cavity_shots = list(series.cavity_shots or [])
        if not cavity_shots:
            cavity_shots = [series.avg_cavity_a]
        measurement = cls._diffusive_measurement_array(protocol, result, len(cavity_shots), nt)

        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        measured_shots: list[np.ndarray] = []

        for traj_idx, cavity_series in enumerate(cavity_shots):
            shot = cls._shot_fields(context.drive, cavity_series, context.kappa_ext_hz)
            if protocol.heterodyne:
                current = cls._measurement_to_complex_series(
                    measurement[traj_idx, 0] if measurement.ndim >= 4 and traj_idx < measurement.shape[0] else [],
                    nt,
                )
                measured_voltage = context.gain_linear * current
                shot_payload = {
                    **shot,
                    "heterodyne_current": cls._serialize_complex_series(current),
                    "heterodyne_I": [float(x) for x in np.real(current).tolist()],
                    "heterodyne_Q": [float(x) for x in np.imag(current).tolist()],
                    "measured_voltage": cls._serialize_complex_series(measured_voltage),
                }
                record = {
                    "times": tlist.astype(float).tolist(),
                    "heterodyne_current": shot_payload["heterodyne_current"],
                    "heterodyne_I": shot_payload["heterodyne_I"],
                    "heterodyne_Q": shot_payload["heterodyne_Q"],
                    "measured_voltage": shot_payload["measured_voltage"],
                }
            else:
                current = cls._measurement_to_real_series(
                    measurement[traj_idx, 0] if measurement.ndim >= 3 and traj_idx < measurement.shape[0] else [],
                    nt,
                )
                measured_voltage = context.gain_linear * current.astype(complex)
                shot_payload = {
                    **shot,
                    "measured_voltage": cls._serialize_real_series_as_complex(np.real(measured_voltage)),
                    "homodyne_current": [float(x) for x in current.tolist()],
                }
                record = {
                    "times": tlist.astype(float).tolist(),
                    "measured_voltage": shot_payload["measured_voltage"],
                    "homodyne_current": shot_payload["homodyne_current"],
                }
            measured_shots.append(measured_voltage)
            shot_payloads.append(shot_payload)
            measurement_records.append(record)

        avg_measured = (
            np.mean(np.asarray(measured_shots, dtype=complex), axis=0) if measured_shots else np.zeros(nt, dtype=complex)
        )
        measurements: dict[str, Any]
        if protocol.heterodyne:
            measurements = {
                "heterodyne_current": cls._serialize_complex_series(
                    avg_measured / max(context.gain_linear, 1.0e-12)
                ),
                "measured_voltage": cls._serialize_complex_series(avg_measured),
            }
        else:
            measurements = {"measured_voltage": cls._serialize_real_series_as_complex(np.real(avg_measured))}

        return _SmeRecords(
            shot_payloads=shot_payloads,
            measurement_records=measurement_records,
            measurements=measurements,
        )

    @staticmethod
    def _diffusive_measurement_array(protocol: _SmeProtocol, result, shot_count: int, nt: int) -> np.ndarray:
        raw_measurement = getattr(result, "measurement", None)
        if protocol.heterodyne:
            if raw_measurement is None:
                return np.zeros((shot_count, 1, 2, max(0, nt - 1)), dtype=float)
            measurement = np.asarray(raw_measurement)
            if measurement.ndim == 3:
                measurement = measurement.reshape(measurement.shape[0], 1, measurement.shape[1], measurement.shape[2])
            return measurement
        if raw_measurement is None:
            return np.zeros((shot_count, 1, max(0, nt - 1)), dtype=float)
        measurement = np.real(np.asarray(raw_measurement, dtype=complex))
        if measurement.ndim == 2:
            measurement = measurement.reshape(measurement.shape[0], 1, measurement.shape[1])
        return measurement

    @classmethod
    def _build_counting_records(
        cls,
        *,
        result,
        tlist: np.ndarray,
        context: _SmeContext,
        series: _SmeSeries,
    ) -> _SmeRecords:
        nt = context.nt
        dt = max(1.0e-18, float(tlist[1] - tlist[0])) if nt > 1 else 1.0
        col_times = list(getattr(result, "col_times", []) or [])
        col_which = list(getattr(result, "col_which", []) or [])
        cavity_shots = list(series.cavity_shots or [])
        if not cavity_shots:
            count = context.ntraj if context.measured_rate > 0.0 else 1
            cavity_shots = [series.avg_cavity_a for _ in range(count)]

        shot_payloads: list[dict[str, Any]] = []
        measurement_records: list[dict[str, Any]] = []
        count_rates: list[np.ndarray] = []
        count_values: list[np.ndarray] = []
        t_edges = np.asarray(tlist, dtype=float)

        for traj_idx, cavity_series in enumerate(cavity_shots):
            shot = cls._shot_fields(context.drive, cavity_series, context.kappa_ext_hz)
            counts = np.zeros(nt, dtype=float)
            jump_times: list[float] = []
            times_for_traj = list(col_times[traj_idx] if traj_idx < len(col_times) else [])
            which_for_traj = list(col_which[traj_idx] if traj_idx < len(col_which) else [])
            for jump_t, jump_ix in zip(times_for_traj, which_for_traj):
                if int(jump_ix) != context.monitored_collapse_index:
                    continue
                jump_time = float(jump_t)
                jump_times.append(jump_time)
                bin_ix = int(np.clip(np.searchsorted(t_edges, jump_time, side="left"), 1, max(1, nt - 1)))
                counts[bin_ix] += 1.0
            count_rate = counts / dt
            count_values.append(counts)
            count_rates.append(count_rate)

            shot_payload = {
                **shot,
                "photon_counts": [int(x) for x in counts.astype(int).tolist()],
                "count_rate": [float(x) for x in count_rate.tolist()],
                "jump_times": jump_times,
            }
            shot_payloads.append(shot_payload)
            measurement_records.append(
                {
                    "times": tlist.astype(float).tolist(),
                    "photon_counts": shot_payload["photon_counts"],
                    "count_rate": shot_payload["count_rate"],
                    "jump_times": jump_times,
                }
            )

        avg_counts = np.mean(np.asarray(count_values, dtype=float), axis=0) if count_values else np.zeros(nt, dtype=float)
        avg_count_rate = (
            np.mean(np.asarray(count_rates, dtype=float), axis=0) if count_rates else np.zeros(nt, dtype=float)
        )
        return _SmeRecords(
            shot_payloads=shot_payloads,
            measurement_records=measurement_records,
            measurements={
                "photon_counts": [float(x) for x in avg_counts.tolist()],
                "count_rate": [float(x) for x in avg_count_rate.tolist()],
            },
        )

    @classmethod
    def _shot_fields(cls, drive: np.ndarray, cavity_series, kappa_ext_hz: float) -> dict[str, Any]:
        a_in = np.asarray(drive, dtype=complex).reshape(-1)
        cavity_vec = np.asarray(cavity_series, dtype=complex).reshape(-1)
        a_out = cls._a_out_series(a_in, cavity_vec, kappa_ext_hz)
        return {
            "a_cavity": cls._serialize_complex_series(cavity_vec),
            "a_in": cls._serialize_complex_series(a_in),
            "a_out": cls._serialize_complex_series(a_out),
        }

    @classmethod
    def _a_out_series(cls, a_in: np.ndarray, cavity: np.ndarray, kappa_ext_hz: float) -> np.ndarray:
        return np.asarray(
            [
                cls._input_output_a_out(a_in=in_field, cavity_field=cavity_field, kappa_ext_hz=kappa_ext_hz)
                for in_field, cavity_field in zip(a_in, cavity)
            ],
            dtype=complex,
        )

    @classmethod
    def _build_sme_classical_payload(
        cls,
        *,
        protocol: _SmeProtocol,
        tlist: np.ndarray,
        readout_chain: dict[str, Any],
        context: _SmeContext,
        series: _SmeSeries,
        record_bundle: _SmeRecords,
    ) -> dict[str, Any]:
        avg_a_out = cls._a_out_series(
            np.asarray(context.drive, dtype=complex).reshape(-1),
            series.avg_cavity_a,
            context.kappa_ext_hz,
        )
        readout = {
            "schema_version": "1.0",
            "times": tlist.astype(float).tolist(),
            "chain": dict(readout_chain),
            "equations": cls._sme_equations(protocol),
            "feedback": {
                "enabled": False,
                "mode": protocol.name,
                "line_target_source": "none",
                "quantum_input_source": "pulse_drive_only",
            },
            "a_in": cls._serialize_complex_series(context.drive),
            "cavity_a": cls._serialize_complex_series(series.avg_cavity_a),
            "cavity_n": [float(x) for x in series.avg_cavity_n.tolist()],
            "a_out": cls._serialize_complex_series(avg_a_out),
            **record_bundle.measurements,
            "qubit_lowering": [cls._serialize_complex_series(values) for values in series.avg_lowering],
            "shots": record_bundle.shot_payloads,
        }
        return {"readout": readout}

    @staticmethod
    def _sme_equations(protocol: _SmeProtocol) -> dict[str, str]:
        equations = {
            "a_out": "a_out(t) = a_in(t) - sqrt(kappa_ext_rad_s) * <a_cavity(t)>_c",
            "quantum_drive": "H_ro(t) uses the pulse-derived a_in(t) directly as the cavity drive coefficient",
        }
        if protocol.name == "homodyne_sme":
            equations["measured_voltage"] = (
                "I_hom(t) = gain * [sqrt(eta*kappa_ext_rad_s) * <a + a^dagger>_c + xi(t)]"
            )
        elif protocol.name == "heterodyne_sme":
            equations["measured_voltage"] = "V_IQ(t) = gain * [I_het(t) + i Q_het(t)]"
            equations["heterodyne_current"] = "I_het(t) + i Q_het(t) from the monitored cavity leakage channel"
        else:
            equations["photon_counts"] = "dN(t) is the monitored output-channel photon count increment"
            equations["count_rate"] = "count_rate(t) = dN(t) / dt for each output time bin"
        return equations

    @staticmethod
    def _attach_sme_basis_population(
        *,
        protocol: _SmeProtocol,
        classical: dict[str, Any],
        avg_primary: np.ndarray,
        num_primary: int,
    ) -> None:
        if num_primary != 1:
            return
        p1 = np.clip(np.real(avg_primary[0]).astype(float), 0.0, 1.0)
        classical["basis_population"] = {
            "quantity": "basis_population",
            "description": f"Ensemble-averaged single-qubit basis populations from the {protocol.name} trajectories.",
            "series_labels": ["0", "1"],
            "values": [[float(1.0 - val), float(val)] for val in p1.tolist()],
        }
