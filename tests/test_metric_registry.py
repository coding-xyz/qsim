from pathlib import Path

from qsim.analysis.metrics import DEFAULT_METRIC_REGISTRY, build_default_metric_registry, resolve_metrics_payload
from qsim.common.schemas import Trajectory, model_spec_from_runtime_dict
from qsim.workflow import DefaultAnalyserConfig, create_model


def test_default_metric_registry_contains_builtin_metrics():
    names = DEFAULT_METRIC_REGISTRY.names()

    assert "population" in names
    assert "mean_excited" in names
    assert "variance" in names


def test_resolve_metrics_payload_uses_registered_metric():
    registry = build_default_metric_registry()

    def tail_sum_metric(trajectory, model_spec, metric_cfg, context):
        del model_spec, metric_cfg, context
        snapshots = list((trajectory.density_matrix or {}).get("snapshots", []) or [])
        final = snapshots[-1] if snapshots else []
        total = 0.0
        for i, row in enumerate(final):
            if i < len(row):
                total += float(row[i].real)
        return {"payload": total, "observable_updates": {"tail_sum": total}}

    registry.register("tail_sum", tail_sum_metric)

    trajectory = Trajectory(
        engine="qutip",
        times=[0.0, 1.0],
        density_matrix={
            "actual_kind": "density_matrix",
            "encoding": "complex",
            "snapshots": [
                [[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]],
                [[0.7 + 0.0j, 0.0j], [0.0j, 0.3 + 0.0j]],
            ],
        },
        metadata={"num_qubits": 1},
    )
    model_spec = model_spec_from_runtime_dict(
        solver="me",
        dimension=2,
        t_end=1.0,
        dt=1.0,
        model={"num_qubits": 1},
    )

    metrics, observables, report = resolve_metrics_payload(
        trajectory,
        model_spec,
        {"metrics": ["tail_sum"]},
        registry=registry,
    )

    assert metrics["tail_sum"] == 1.0
    assert observables.values["tail_sum"] == 1.0
    assert "tail_sum" in report.summary["metrics"]


def test_model_run_analysis_uses_model_metric_registry():
    base = Path("examples/noise_simulation_tests").resolve() / "task1"
    model = create_model(task_config=base / "task.yaml", analyser_config=None)

    def tail_sum_metric(trajectory, model_spec, metric_cfg, context):
        del model_spec, metric_cfg, context
        snapshots = list((trajectory.density_matrix or {}).get("snapshots", []) or [])
        final = snapshots[-1] if snapshots else []
        total = 0.0
        for i, row in enumerate(final):
            if i < len(row):
                total += float(row[i].real)
        return {
            "payload": total,
            "observable_updates": {"tail_sum": total},
        }

    model.register_metric("tail_sum", tail_sum_metric)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["tail_sum"]))
    model.run()

    analysis = model.results.analyses["analyser_0"]
    assert "tail_sum" in analysis.metrics
    assert "tail_sum" in analysis.report["summary"]["metrics"]


def test_add_analyser_binds_to_solver():
    base = Path("examples/noise_simulation_tests").resolve() / "task1"
    model = create_model(task_config=base / "task.yaml", analyser_config=None)

    model.add_analyser(
        "population_only",
        "solver_0",
        DefaultAnalyserConfig(metrics=["population"]),
    )
    model.run_all()

    assert model.analysers["population_only"].solver_id == "solver_0"
    assert "population" in model.results.analyses["population_only"].metrics
