from pathlib import Path

from qsim.workflow import DefaultAnalyserConfig, Model, create_model, load_model


def _example_dir(name: str) -> Path:
    return Path("examples/noise_simulation_tests").resolve() / name


def test_create_model_task1_roundtrip_uses_run_scoped_storage():
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    assert isinstance(model, Model)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))

    model.run()

    assert "solver_0" in model.runs
    run = model.runs["solver_0"]
    assert run.identity.solver_id == "solver_0"
    assert run.artifacts.model_spec is not None
    assert run.result is not None
    assert run.result.trajectory is not None

    assert "analyser_0" in model.analyses
    analysis = model.analyses["analyser_0"]
    assert analysis.output.metrics is not None
    assert len(analysis.output.metrics.metric_items) > 0
    assert analysis.input_run_ids == ["solver_0"]

    saved = model.save(base / "runs_model_api_pytest")
    loaded = load_model(saved)
    loaded.run()

    assert "solver_0" in loaded.runs
    assert loaded.runs["solver_0"].result is not None
    assert loaded.runs["solver_0"].result.trajectory.engine == model.runs["solver_0"].result.trajectory.engine


def test_create_model_task2_iq_outputs_are_model_level_analyses():
    base = _example_dir("task2")
    model = create_model(task_config=base / "task.yaml")
    model.run()

    assert len(model.runs) > 0
    assert "analyser_0" in model.analyses

    analysis = model.analyses["analyser_0"]
    assert analysis.input_run_ids
    assert analysis.output.iq is not None
    assert analysis.output.iq.assignment_fidelity is not None
    assert analysis.output.iq.snr is not None


def test_add_analyser_copies_shared_config_per_solver():
    base = _example_dir("task1")
    model = create_model(
        task_config=base / "task.yaml",
        solver_config={
            "qutip": base / "qutip.yaml",
            "qtoolbox": base / "qtoolbox.yaml",
        },
        analyser_config=None,
    )
    shared = DefaultAnalyserConfig(metrics=["population"])

    model.add_analyser("pop_qutip", "qutip", shared)
    model.add_analyser("pop_qtoolbox", "qtoolbox", shared)

    assert shared.solver_id is None
    assert model.analysers["pop_qutip"].solver_id == "qutip"
    assert model.analysers["pop_qtoolbox"].solver_id == "qtoolbox"
    assert model.analysers["pop_qutip"] is not model.analysers["pop_qtoolbox"]
