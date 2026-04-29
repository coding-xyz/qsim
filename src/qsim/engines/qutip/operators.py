"""Operator builders for QuTiP-backed models."""

from __future__ import annotations


class QutipOperatorMixin:
    """Build QuTiP operators for supported model families."""

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

    def _build_qubit_ops(self, qt, n_qubits: int):
        dims = [2 for _ in range(n_qubits)]
        sx = [self._tensor_op(qt, dims, i, qt.sigmax()) for i in range(n_qubits)]
        sy = [self._tensor_op(qt, dims, i, qt.sigmay()) for i in range(n_qubits)]
        sz = [self._tensor_op(qt, dims, i, qt.sigmaz()) for i in range(n_qubits)]
        # qutip.sigmam/sigmap follow a spin convention where sigmam maps basis(2,0) -> basis(2,1).
        # The workflow uses basis(2,0) as |0> and basis(2,1) as |1>, so the
        # physical lowering operator |0><1| corresponds to qutip.sigmap().
        sm = [self._tensor_op(qt, dims, i, qt.sigmap()) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(2, 0) for _ in range(n_qubits)])
        ident = qt.tensor([qt.qeye(2) for _ in range(n_qubits)])
        readout_ops = [0.5 * (ident - sz[i]) for i in range(n_qubits)]
        return sx, sy, sz, sm, psi0, readout_ops

    def _build_nlevel_ops(self, qt, n_qubits: int, levels: int):
        dims = [levels for _ in range(n_qubits)]
        a_local = qt.destroy(levels)
        adag_local = a_local.dag()
        n_local = adag_local * a_local
        x_local = a_local + adag_local
        y_local = -1j * (a_local - adag_local)
        a = [self._tensor_op(qt, dims, i, a_local) for i in range(n_qubits)]
        adag = [self._tensor_op(qt, dims, i, adag_local) for i in range(n_qubits)]
        n = [self._tensor_op(qt, dims, i, n_local) for i in range(n_qubits)]
        x = [self._tensor_op(qt, dims, i, x_local) for i in range(n_qubits)]
        y = [self._tensor_op(qt, dims, i, y_local) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(levels, 0) for _ in range(n_qubits)])
        p1_local = self._projector_one(qt, levels)
        readout_ops = [self._tensor_op(qt, dims, i, p1_local) for i in range(n_qubits)]
        return a, adag, n, x, y, psi0, readout_ops

    def _build_cqed_ops(self, qt, n_qubits: int, levels: int, cavity_nmax: int):
        nc = max(1, int(cavity_nmax) + 1)
        dims = [nc] + [levels for _ in range(n_qubits)]
        a_c_local = qt.destroy(nc)
        a_c = self._tensor_op(qt, dims, 0, a_c_local)
        adag_c = a_c.dag()
        n_c = adag_c * a_c
        a_q_local = qt.destroy(levels)
        adag_q_local = a_q_local.dag()
        n_q_local = adag_q_local * a_q_local
        x_q_local = a_q_local + adag_q_local
        y_q_local = -1j * (a_q_local - adag_q_local)
        a_q = [self._tensor_op(qt, dims, i + 1, a_q_local) for i in range(n_qubits)]
        adag_q = [self._tensor_op(qt, dims, i + 1, adag_q_local) for i in range(n_qubits)]
        n_q = [self._tensor_op(qt, dims, i + 1, n_q_local) for i in range(n_qubits)]
        x_q = [self._tensor_op(qt, dims, i + 1, x_q_local) for i in range(n_qubits)]
        y_q = [self._tensor_op(qt, dims, i + 1, y_q_local) for i in range(n_qubits)]
        psi0 = qt.tensor([qt.basis(nc, 0)] + [qt.basis(levels, 0) for _ in range(n_qubits)])
        p1_local = self._projector_one(qt, levels)
        readout_ops = [self._tensor_op(qt, dims, i + 1, p1_local) for i in range(n_qubits)]
        return a_c, adag_c, n_c, a_q, adag_q, n_q, x_q, y_q, psi0, readout_ops
