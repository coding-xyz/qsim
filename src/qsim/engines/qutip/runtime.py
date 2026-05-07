"""Typed QuTiP runtime IR built from engine-neutral ``ModelSpec``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from qsim.common.schemas import ModelSpec


@dataclass
class QutipRunConfig:
    """Execution controls owned by ``ModelSpec.solver`` for a QuTiP run."""

    seed: int = 12345
    ntraj: int = 128
    qutip_options: Any = None
    one_over_f_components: int = 64
    backend_options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_model_spec(cls, model_spec: ModelSpec) -> "QutipRunConfig":
        """Extract QuTiP runtime controls from ``ModelSpec.solver``."""
        solver = model_spec.solver
        options = dict(getattr(solver, "options", {}) or {})
        backend_options = dict(options.get("backend_options", {}) or {})
        native_options = options.get("qutip_options", options.get("native_options", None))
        return cls(
            seed=int(solver.seed if solver.seed is not None else options.get("seed", 12345)),
            ntraj=int(max(1, solver.ntraj if solver.ntraj is not None else options.get("ntraj", 128))),
            qutip_options=native_options,
            one_over_f_components=int(options.get("one_over_f_components") or 64),
            backend_options=backend_options,
        )


@dataclass
class QutipPlan:
    """QuTiP-local plan after classifying quantum/classical/hybrid dynamics."""

    qt: Any
    model_spec: ModelSpec
    run_config: QutipRunConfig
    dynamics_kind: str
    model_type: str
    solver: str
    n_qubits: int
    dt: float
    tlist: np.ndarray
    freqs: list[float]
    anh: list[float]
    frame_mode: str
    rwa: bool
    readout_chain: dict[str, Any]
    readout_controls: list[Any]
    hybrid_update_mode: str
    readout_protocol: str
    readout_mode: str

    def inspect(self) -> dict[str, Any]:
        """Return a compact, serializable boundary summary for debugging."""
        return {
            "dynamics_kind": self.dynamics_kind,
            "model_type": self.model_type,
            "solver": self.solver,
            "n_qubits": self.n_qubits,
            "dt": self.dt,
            "num_time_points": int(self.tlist.size),
            "frame_mode": self.frame_mode,
            "rwa": self.rwa,
            "readout_mode": self.readout_mode,
            "readout_protocol": self.readout_protocol,
            "seed": self.run_config.seed,
            "ntraj": self.run_config.ntraj,
        }


@dataclass
class QutipSystem:
    """QuTiP operators and Hamiltonian terms for the selected plan."""

    H: list[Any]
    psi0: Any
    e_ops: list[Any]
    x_ops: list[Any]
    y_ops: list[Any]
    z_ops: list[Any]
    lower_ops: list[Any]
    raise_ops: list[Any]
    cavity_a: Any = None
    cavity_n: Any = None
    hybrid_arg_store: dict[str, float] | None = None

    def inspect(self) -> dict[str, Any]:
        """Return counts that summarize the constructed QuTiP system."""
        return {
            "num_hamiltonian_terms": len(self.H),
            "num_expectation_ops": len(self.e_ops),
            "num_lowering_ops": len(self.lower_ops),
            "has_cavity": self.cavity_a is not None and self.cavity_n is not None,
            "has_hybrid_arg_store": self.hybrid_arg_store is not None,
        }


@dataclass
class QutipSolverInputs:
    """Collapse operators and sampled stochastic noise entering a solver mode."""

    c_ops: list[Any]
    selected_noise: str
    seed: int

    def inspect(self) -> dict[str, Any]:
        """Return a serializable summary of collapse/noise inputs."""
        return {
            "num_collapse_ops": len(self.c_ops),
            "selected_noise": self.selected_noise,
            "seed": self.seed,
        }


@dataclass
class QutipTrajectoryRequest:
    """Requested trajectory/state-storage behavior for QuTiP output."""

    requested_state_kind: str
    save_times: str
    save_final_state: bool
    options: Any

    def inspect(self) -> dict[str, Any]:
        """Return a serializable summary of requested trajectory storage."""
        return {
            "requested_state_kind": self.requested_state_kind,
            "save_times": self.save_times,
            "save_final_state": self.save_final_state,
        }
