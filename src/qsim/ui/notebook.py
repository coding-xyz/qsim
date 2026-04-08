"""Notebook helper utilities for the model-first workflow API."""

from __future__ import annotations

from qsim.pulse.visualize import plot_pulses, plot_report, plot_trajectory
from qsim.workflow.model import Model


def plot_default(model: Model) -> dict[str, object]:
    """Build the default figure bundle for a completed ``Model``.

    Args:
        model: A model that has already completed ``model.run()``.

    Returns:
        A mapping with optional matplotlib figures under
        ``pulses``, ``trajectory``, and ``report``.
    """
    if not model.results.trajectories:
        raise ValueError("plot_default expects a model that has already been run.")
    solver_id = sorted(model.results.trajectories.keys())[0]
    bundle = model.results.solver_runs[solver_id]
    trajectory = bundle.trajectory
    assert trajectory is not None

    report_payload = {}
    if bundle.analyses:
        analyser_id = sorted(bundle.analyses.keys())[0]
        report_payload = dict(bundle.analyses[analyser_id].report or {})

    return {
        "pulses": plot_pulses(bundle.pulse_ir) if bundle.pulse_ir is not None else None,
        "trajectory": plot_trajectory(trajectory),
        "report": plot_report(report_payload),
    }


__all__ = ["plot_default"]
