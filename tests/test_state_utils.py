import numpy as np

from qsim.analysis import state_fidelity
from qsim.analysis.state_utils import final_density_matrix
from qsim.common.schemas import Trajectory


def test_state_fidelity_uses_target_subspace_and_normalizes_state():
    rho = np.diag([0.5, 0.5, 0.0])
    psi = np.array([2.0, 0.0], dtype=complex)

    assert state_fidelity(rho, psi) == 0.5


def test_final_density_matrix_reads_last_snapshot():
    first = [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]]
    last = [[0.0j, 0.0j], [0.0j, 1.0 + 0.0j]]
    trajectory = Trajectory(
        times=[0.0, 1.0],
        density_matrix={"actual_kind": "density_matrix", "snapshots": [first, last]},
    )

    np.testing.assert_allclose(final_density_matrix(trajectory), np.asarray(last, dtype=complex))
