from pathlib import Path

from qsim.workflow import DefaultAnalyserConfig, Model, create_model, load_model


def _example_dir(name: str) -> Path:
    return Path("examples/noise_simulation_tests").resolve() / name


def test_create_model_task1_roundtrip():
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    assert isinstance(model, Model)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))

    model.run()
    assert "solver_0" in model.results.trajectories
    assert "analyser_0" in model.results.analyses
    assert "population" in model.results.analyses["analyser_0"].metrics

    saved = model.save(base / "runs_model_api_pytest")
    loaded = load_model(saved)
    loaded.run()
    assert "solver_0" in loaded.results.trajectories
    assert loaded.results.trajectories["solver_0"].engine == model.results.trajectories["solver_0"].engine


def test_create_model_task2_iq_outputs():
    base = _example_dir("task2")
    model = create_model(task_config=base / "task.yaml")
    model.run()
    analysis = model.results.analyses["analyser_0"]

    assert "solver_0" in model.results.trajectories
    assert "assignment_fidelity" in analysis.iq
    assert "snr" in analysis.iq


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

