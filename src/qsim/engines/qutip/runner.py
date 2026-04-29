"""Top-level QuTiP engine runner orchestration."""

from __future__ import annotations

import numpy as np

from qsim.common.schemas import ModelSpec, Trajectory
from qsim.engines.qutip.modes import run_solver_mode
from qsim.engines.qutip.model import build_collapse_and_noise, build_hamiltonian_system
from qsim.engines.qutip.runtime import QutipPlan, QutipRunConfig, QutipTrajectoryRequest


class QutipRunnerMixin:
    """Coordinate QuTiP setup, solver dispatch, and trajectory formatting."""

    def run(self, model_spec: ModelSpec) -> Trajectory:
        """Solve model dynamics based on ``model_spec.solver_mode``."""
        model_type = str(model_spec.system.model_type)

        if str(model_type).strip().lower() == "cavity_classical_readout":
            return self._run_cavity_classical_readout(model_spec=model_spec, run_config=QutipRunConfig.from_model_spec(model_spec))

        qt = self._import_qutip()
        plan = self._prepare_run_setup(
            qt=qt,
            model_spec=model_spec,
            model_type=model_type,
        )
        system = build_hamiltonian_system(self, plan)
        solver_inputs = build_collapse_and_noise(self, plan, system)
        trajectory_cfg = self._resolve_trajectory_config(plan)
        return run_solver_mode(
            engine=self,
            setup=plan,
            system=system,
            solver_inputs=solver_inputs,
            trajectory_cfg=trajectory_cfg,
        )

    @staticmethod
    def _import_qutip():
        try:
            import qutip as qt
        except Exception as exc:
            raise RuntimeError(f"QuTiP dependency unavailable: {exc}") from exc
        return qt

    def _prepare_run_setup(
        self,
        *,
        qt,
        model_spec: ModelSpec,
        model_type: str,
    ) -> QutipPlan:
        n_qubits = int(model_spec.system.num_qubits)
        if n_qubits < 1:
            raise ValueError(f"Invalid runtime model: num_qubits must be >= 1, got {n_qubits}")

        run_config = QutipRunConfig.from_model_spec(model_spec)
        dt = max(float(model_spec.dt), 1e-12)
        t_end = max(float(model_spec.t_end), dt)
        tlist = np.arange(0.0, t_end + 0.5 * dt, dt)

        freqs = [float(x) for x in list(model_spec.system.qubit_omega_rad_s or [])]
        if len(freqs) < n_qubits:
            freqs.extend([0.0] * (n_qubits - len(freqs)))
        anh = [float(x) for x in list(model_spec.system.anharmonicity_rad_s or [])]
        if len(anh) < n_qubits:
            anh.extend([0.0] * (n_qubits - len(anh)))

        frame_mode = str(model_spec.frame.mode).strip().lower()
        rwa = bool(model_spec.frame.rwa)
        solver = model_spec.solver_mode
        readout_chain = self._infer_cqed_readout_params(model_spec, n_qubits)
        hybrid_update_mode = self._resolve_hybrid_update_mode(model_spec)
        readout_protocol = self._resolve_readout_protocol(model_spec)
        has_classical_line = self._is_cqed_model(model_type) and self._has_classical_readout_line(model_spec)
        readout_mode = self._resolve_runtime_readout_mode(
            solver=solver,
            has_classical_line=has_classical_line,
            readout_protocol=readout_protocol,
        )
        dynamics_kind = self._classify_dynamics(
            model_type=model_type,
            readout_mode=readout_mode,
        )

        if solver not in {"se", "me", "mcwf", "heom"}:
            raise ValueError(f"Unsupported solver for QuTiP engine: {model_spec.solver_mode}")

        return QutipPlan(
            qt=qt,
            model_spec=model_spec,
            run_config=run_config,
            dynamics_kind=dynamics_kind,
            model_type=model_type,
            solver=solver,
            n_qubits=n_qubits,
            dt=dt,
            tlist=tlist,
            freqs=freqs,
            anh=anh,
            frame_mode=frame_mode,
            rwa=rwa,
            readout_chain=readout_chain,
            readout_controls=list(model_spec.readout.controls if model_spec.readout else []),
            hybrid_update_mode=hybrid_update_mode,
            readout_protocol=readout_protocol,
            readout_mode=readout_mode,
        )

    @staticmethod
    def _classify_dynamics(*, model_type: str, readout_mode: str) -> str:
        if str(model_type).strip().lower() == "cavity_classical_readout":
            return "classical"
        if readout_mode == "hybrid_classical":
            return "hybrid"
        return "quantum"

    @staticmethod
    def _resolve_runtime_readout_mode(*, solver: str, has_classical_line: bool, readout_protocol: str) -> str:
        if not has_classical_line:
            return "none"
        if solver in {"me", "mcwf"} and readout_protocol in {
            "homodyne_sme",
            "heterodyne_sme",
            "photon_counting_sme",
        }:
            return "monitored_sme"
        if solver == "mcwf":
            return "hybrid_classical"
        return "postprocessed_classical"

    def _resolve_trajectory_config(self, setup: QutipPlan) -> QutipTrajectoryRequest:
        model_spec = setup.model_spec
        solver = setup.solver
        analyser_cfg = dict(model_spec.analysis_request.config if model_spec.analysis_request else {})
        trajectory_cfg = dict(analyser_cfg.get("trajectory", {}) or {})
        requested_state_kind = str(trajectory_cfg.get("quantum", "")).strip().lower()
        if requested_state_kind not in {"wave_function", "density_matrix"}:
            requested_state_kind = "wave_function" if solver == "mcwf" else "density_matrix"
        save_times = str(trajectory_cfg.get("save_times", "all")).strip().lower()
        save_final_state = bool(trajectory_cfg.get("save_final_state", True))
        store_states = requested_state_kind in {"wave_function", "density_matrix"} and (
            save_times != "none" or save_final_state
        )
        return QutipTrajectoryRequest(
            requested_state_kind=requested_state_kind,
            save_times=save_times,
            save_final_state=save_final_state,
            options=self._solver_options_with_state_storage(
                setup.qt,
                setup.run_config.qutip_options,
                store_states=store_states,
                keep_runs_results=solver == "mcwf",
            ),
        )

