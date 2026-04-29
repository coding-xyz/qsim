"""Hamiltonian lowering from QuTiP runtime model data."""

from __future__ import annotations

import math
from typing import Any

from qsim.engines.qutip.runtime import QutipPlan, QutipSystem


def build_hamiltonian_system(engine, setup: QutipPlan) -> QutipSystem:
    """Build QuTiP operators and Hamiltonian terms for a prepared setup."""
    qt = setup.qt
    model_spec = setup.model_spec
    system_spec = model_spec.system
    hamiltonian = model_spec.hamiltonian
    model_type = setup.model_type
    model_key = str(model_type).strip().lower()
    n_qubits = setup.n_qubits
    freqs = setup.freqs
    anh = setup.anh
    frame_mode = setup.frame_mode
    rwa = setup.rwa
    readout_chain = setup.readout_chain

    cavity_a = None
    cavity_adag = None
    cavity_n = None
    hybrid_arg_store: dict[str, float] | None = None

    if model_key == "qubit_network":
        sx, sy, sz, sm, psi0, e_ops = engine._build_qubit_ops(qt, n_qubits)
        x_ops = sx
        y_ops = sy
        z_ops = sz
        lower_ops = sm
        raise_ops = [op.dag() for op in sm]
        H0 = 0 * sz[0]
        for i in range(n_qubits):
            H0 = H0 + 0.5 * freqs[i] * sz[i]
    elif model_key == "transmon_nlevel":
        levels = int(system_spec.transmon_levels or 3)
        a, adag, n, x, y, psi0, e_ops = engine._build_nlevel_ops(qt, n_qubits, levels)
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
    elif engine._is_cqed_model(model_type):
        levels = int(system_spec.transmon_levels or 3)
        cavity_nmax = int(system_spec.cavity_nmax or 8)
        a_c, adag_c, n_c, a_q, adag_q, n_q, x_q, y_q, psi0, e_ops = engine._build_cqed_ops(
            qt,
            n_qubits,
            levels,
            cavity_nmax,
        )
        cavity_a = a_c
        cavity_adag = adag_c
        cavity_n = n_c
        x_ops = x_q
        y_ops = y_q
        z_ops = n_q
        lower_ops = a_q
        raise_ops = adag_q
        cavity_omega_rad_s = float(system_spec.cavity_omega_rad_s)
        if frame_mode == "rotating":
            for ctrl in list(model_spec.readout.controls if model_spec.readout else []):
                ref = float(ctrl.carrier_omega_rad_s or 0.0)
                if ref != 0.0:
                    cavity_omega_rad_s = cavity_omega_rad_s - ref
                    break
        H0 = cavity_omega_rad_s * n_c
        for i in range(n_qubits):
            ni = n_q[i]
            ident = qt.qeye(ni.dims[0])
            H0 = H0 + freqs[i] * ni + 0.5 * anh[i] * (ni * (ni - ident))
        if model_key == "cqed_jc":
            g_cavity = list(system_spec.g_cavity_rad_s or [0.0 for _ in range(n_qubits)])
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

    H0 = _append_static_couplings(
        H0=H0,
        couplings=hamiltonian.coupling_terms,
        model_type=model_type,
        n_qubits=n_qubits,
        x_ops=x_ops,
        y_ops=y_ops,
        z_ops=z_ops,
        lower_ops=lower_ops,
        raise_ops=raise_ops,
    )
    H = [H0]
    _append_control_terms(
        engine=engine,
        H=H,
        controls=hamiltonian.control_terms,
        n_qubits=n_qubits,
        frame_mode=frame_mode,
        rwa=rwa,
        x_ops=x_ops,
        y_ops=y_ops,
        z_ops=z_ops,
    )
    hybrid_arg_store = _append_readout_drive_terms(
        engine=engine,
        H=H,
        readout_controls=list(model_spec.readout.controls if model_spec.readout else []),
        setup=setup,
        cavity_a=cavity_a,
        cavity_adag=cavity_adag,
    )

    return QutipSystem(
        H=H,
        psi0=psi0,
        e_ops=e_ops,
        x_ops=x_ops,
        y_ops=y_ops,
        z_ops=z_ops,
        lower_ops=lower_ops,
        raise_ops=raise_ops,
        cavity_a=cavity_a,
        cavity_n=cavity_n,
        hybrid_arg_store=hybrid_arg_store,
    )


def _append_static_couplings(
    *,
    H0,
    couplings: list[dict[str, Any]],
    model_type: str,
    n_qubits: int,
    x_ops,
    y_ops,
    z_ops,
    lower_ops,
    raise_ops,
):
    for c in couplings:
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
        elif str(model_type).strip().lower() == "qubit_network":
            H0 = H0 + g * ((x_ops[i] * x_ops[j]) + (y_ops[i] * y_ops[j]))
        else:
            H0 = H0 + g * (raise_ops[i] * lower_ops[j] + lower_ops[i] * raise_ops[j])
    return H0


def _append_control_terms(
    *,
    engine,
    H: list[Any],
    controls: list[Any],
    n_qubits: int,
    frame_mode: str,
    rwa: bool,
    x_ops,
    y_ops,
    z_ops,
) -> None:
    for ctrl in controls:
        axis = str(ctrl.operator.name).lower()
        if axis == "zz":
            pair = list(ctrl.operator.target_pair or [])
            if len(pair) < 2:
                continue
            i, j = int(pair[0]), int(pair[1])
            if i < 0 or j < 0 or i >= n_qubits or j >= n_qubits or i == j:
                continue
            coeff_env = engine._control_envelope(ctrl)
            H.append([z_ops[i] * z_ops[j], coeff_env])
            continue

        target = -1 if ctrl.operator.target is None else int(ctrl.operator.target)
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

        coeff_env = engine._control_envelope(ctrl)
        if axis == "x":
            carrier = ctrl.coefficient.carrier
            carrier_omega_rad_s = float(carrier.omega_rad_s if carrier else 0.0)
            drive_delta_rad_s = float(ctrl.metadata.get("drive_delta_rad_s", 0.0))
            phase_rad = float(carrier.phase_rad if carrier else 0.0)
            omega_rad_s = drive_delta_rad_s if frame_mode == "rotating" and rwa else carrier_omega_rad_s
            H.append([op_x, engine._modulated_coeff(coeff_env, omega_rad_s=omega_rad_s, phase_rad=phase_rad, trig="cos")])
            if frame_mode == "rotating" and rwa:
                H.append([op_y, engine._modulated_coeff(coeff_env, omega_rad_s=omega_rad_s, phase_rad=phase_rad, trig="sin")])
        else:
            H.append([op, coeff_env])


def _append_readout_drive_terms(
    *,
    engine,
    H: list[Any],
    readout_controls: list[Any],
    setup: QutipPlan,
    cavity_a,
    cavity_adag,
) -> dict[str, float] | None:
    if not engine._is_cqed_model(setup.model_type) or cavity_a is None or cavity_adag is None:
        return None

    cavity_x = cavity_a + cavity_adag
    cavity_y = -1j * (cavity_a - cavity_adag)
    if setup.readout_mode == "hybrid_classical":
        hybrid_arg_store = {"hybrid_ro_re": 0.0, "hybrid_ro_im": 0.0}
        H.append([cavity_x, engine._arg_coeff("hybrid_ro_re", hybrid_arg_store)])
        H.append([cavity_y, engine._arg_coeff("hybrid_ro_im", hybrid_arg_store)])
        return hybrid_arg_store

    readout_drive_scale = engine._readout_coupling_prefactor(setup.readout_chain.get("kappa_ext_Hz", 0.0))
    for ctrl in readout_controls:
        coeff_env = engine._control_envelope(ctrl)
        phase_rad = float(ctrl.carrier_phase_rad or 0.0)
        carrier_omega_rad_s = float(ctrl.carrier_omega_rad_s or 0.0)
        if setup.frame_mode == "rotating" and setup.rwa:
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
                    engine._modulated_coeff(
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
                    engine._modulated_coeff(
                        scaled_env,
                        omega_rad_s=carrier_omega_rad_s,
                        phase_rad=phase_rad,
                        trig="sin",
                    ),
                ]
            )
    return None
