"""Classical readout observables derived after quantum dynamics."""

from __future__ import annotations

from typing import Any

import numpy as np

from qsim.engines.qutip.runtime import QutipPlan, QutipSolverInputs, QutipSystem


def attach_postprocessed_readout(
    engine,
    *,
    metadata: dict[str, Any],
    setup: QutipPlan,
    system: QutipSystem,
    solver_inputs: QutipSolverInputs,
    result,
    readout_expect_ix: dict[str, Any],
) -> None:
    """Attach classical readout observables after a standard quantum solve."""
    if not engine._is_cqed_model(setup.model_type) or "cavity_a" not in readout_expect_ix:
        return

    tlist = setup.tlist
    cavity_a_series = engine._series_to_complex(engine._average_expect_series(result.expect[readout_expect_ix["cavity_a"]]))
    cavity_n_series = engine._series_to_float(engine._average_expect_series(result.expect[readout_expect_ix["cavity_n"]])).tolist()
    qubit_lowering_series = [
        engine._serialize_complex_series(engine._series_to_complex(engine._average_expect_series(result.expect[ix])))
        for ix in readout_expect_ix.get("qubit_lowering", [])
    ]
    shot_cavity = []
    if setup.solver == "mcwf":
        shot_cavity = [
            engine._series_to_complex(values)
            for values in engine._shot_expectation_series(result.expect[readout_expect_ix["cavity_a"]])
        ]
    drive = engine._sample_readout_drive(tlist, list(setup.readout_controls or []))
    classical_line = engine._simulate_classical_readout(
        tlist=tlist,
        drive=drive,
        cavity_avg=cavity_a_series,
        cavity_shots=shot_cavity,
        chain=setup.readout_chain,
        seed=solver_inputs.seed,
    )
    average_line = dict(classical_line.get("average", {}) or {})
    metadata["readout_observables"] = {
        "schema_version": "1.0",
        "times": tlist.astype(float).tolist(),
        "chain": setup.readout_chain,
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
        "a_in": engine._serialize_complex_series(np.asarray(average_line.get("a_in", drive), dtype=complex)),
        "cavity_a": engine._serialize_complex_series(cavity_a_series),
        "cavity_n": cavity_n_series,
        "a_out": engine._serialize_complex_series(
            np.asarray(average_line.get("a_out", drive - cavity_a_series), dtype=complex)
        ),
        "line_state": engine._serialize_complex_series(
            np.asarray(average_line.get("line_state", np.zeros_like(cavity_a_series)), dtype=complex)
        ),
        "measured_voltage": engine._serialize_complex_series(
            np.asarray(average_line.get("measured_voltage", np.zeros_like(cavity_a_series)), dtype=complex)
        ),
        "qubit_lowering": qubit_lowering_series,
        "shots": list(classical_line.get("shots", []) or []),
    }
