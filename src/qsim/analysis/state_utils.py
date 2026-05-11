"""Small quantum-state helpers for notebook and workflow analysis."""

from __future__ import annotations

from typing import Any

import numpy as np

from qsim.common.schemas import Trajectory


def final_density_matrix(source: Any) -> np.ndarray:
    """Return the final density matrix from a trajectory-like object.

    ``source`` may be a ``Trajectory``, a solver-run bundle with a ``trajectory``
    attribute, or a ``Model`` containing ``runs``.
    """
    trajectory = source
    if hasattr(source, "trajectory"):
        trajectory = source.trajectory
    elif hasattr(source, "runs") and source.runs:
        # Use the first available run trajectory as representative
        first_run = next(iter(source.runs.values()))
        trajectory = first_run.result.trajectory if first_run.result else None

    if not isinstance(trajectory, Trajectory) and not hasattr(trajectory, "density_matrix"):
        raise TypeError("source must be a Trajectory, solver-run bundle, or Model with density-matrix results")

    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    snapshots = list(density_matrix.get("snapshots", []) or [])
    if not snapshots:
        raise ValueError("trajectory does not contain density_matrix snapshots")
    return np.asarray(snapshots[-1], dtype=complex)


def state_fidelity(rho: Any, psi: Any) -> float:
    """Compute pure-state fidelity ``<psi|rho|psi>``.

    The state vector is normalized defensively. If ``rho`` is larger than the
    target vector, the top-left computational subspace with matching dimension
    is used.
    """
    rho_arr = np.asarray(rho, dtype=complex)
    psi_arr = np.asarray(psi, dtype=complex).reshape(-1)
    norm = np.linalg.norm(psi_arr)
    if norm == 0.0:
        raise ValueError("psi must be nonzero")
    psi_arr = psi_arr / norm
    dim = psi_arr.shape[0]
    if rho_arr.shape[0] < dim or rho_arr.shape[1] < dim:
        raise ValueError("rho dimension is smaller than psi dimension")
    rho_sub = rho_arr[:dim, :dim]
    return float(np.real(np.vdot(psi_arr, rho_sub @ psi_arr)))
