"""Native QuTiP reference for Task1 single-qubit baseline/detuned cases.

This reference mirrors the simplified single-qubit effective model used by the
Julia bridge helper (`scripts/julia_engine_bridge.jl`) for cross-checking
engine invocation and trend consistency.
"""

from __future__ import annotations

import numpy as np
import qutip as qt
import json

def rates_from_T1_T2(T1: float, T2: float, Tup: float | None = None) -> Tuple[float, float, float]:
    gamma_down = 0.0 if T1 <= 0 else 1.0 / T1
    gamma_up = 0.0 if not Tup or Tup <= 0 else 1.0 / Tup
    gamma_phi = max(0.0, (0.0 if T2 <= 0 else 1.0 / T2) - 0.5 * (gamma_down + gamma_up))
    return gamma_down, gamma_up, gamma_phi


def run_case(delta: float, omega: float, T1: float, T2: float, t_end: float, dt: float):
    tlist = np.arange(0.0, t_end + 0.5 * dt, dt)
    sx = qt.sigmax()
    sz = qt.sigmaz()
    sm = qt.sigmam()
    sp = qt.sigmap()
    psi0 = qt.basis(2, 0)

    gamma_down, gamma_up, gamma_phi = rates_from_T1_T2(T1=T1, T2=T2)
    H = 0.5 * delta * sz + 0.5 * omega * sx
    c_ops = []
    if gamma_down > 0:
        c_ops.append(np.sqrt(gamma_down) * sm)
    if gamma_up > 0:
        c_ops.append(np.sqrt(gamma_up) * sp)
    if gamma_phi > 0:
        c_ops.append(np.sqrt(gamma_phi) * sz)

    p1_op = 0.5 * (qt.qeye(2) + sz)
    res = qt.mesolve(H, psi0 * psi0.dag(), tlist, c_ops=c_ops, e_ops=[p1_op])
    p1 = np.asarray(res.expect[0], dtype=float)
    return tlist, p1


if __name__ == "__main__":
    # Use this omega estimate from pulse controls for trend check.
    omega_eff = 0.2
    cases = {
        "baseline": {"delta": 5.0, "T1": 120.0, "T2": 90.0, "t_end": 240.0, "dt": 1.0},
        "detuned": {"delta": 5.2, "T1": 80.0, "T2": 55.0, "t_end": 256.0, "dt": 1.0},
    }
    result = {
        "engine": "qutip_native",
        "cases": {},
    }
    for name, cfg in cases.items():
        t, p1 = run_case(
            delta=cfg["delta"],
            omega=omega_eff,
            T1=cfg["T1"],
            T2=cfg["T2"],
            t_end=cfg["t_end"],
            dt=cfg["dt"],
        )
        t = [float(x) for x in t]
        p1 = [float(x) for x in p1]

        result["cases"][name] = {
            "times": t,
            "p1_t": p1,
            "final_p1": p1[-1],
            "samples": len(t),
            "params": {
                "delta": cfg["delta"],
                "omega": omega_eff,
                "T1": cfg["T1"],
                "T2": cfg["T2"],
                "t_end": cfg["t_end"],
                "dt": cfg["dt"],
            },
        }

    print(json.dumps(result, ensure_ascii=False))