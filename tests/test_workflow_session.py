from pathlib import Path

from qsim.workflow import DefaultAnalyserConfig, create_model, load_model


def _example_dir(name: str) -> Path:
    return Path("examples/noise_simulation_tests").resolve() / name


def test_model_save_writes_hierarchical_run_and_analysis_structure(tmp_path: Path):
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))
    model.run()
    out = model.save(tmp_path / "saved_model")

    assert (out / "config" / "task.json").exists()
    assert (out / "config" / "device.json").exists()
    assert (out / "config" / "pulse.json").exists()
    assert (out / "runs" / "solver_0" / "identity.json").exists()
    assert (out / "runs" / "solver_0" / "runtime_task.json").exists()
    assert (out / "runs" / "solver_0" / "artifacts" / "model_spec.json").exists()
    assert (out / "runs" / "solver_0" / "result" / "trajectory.h5").exists()
    assert (out / "analyses" / "analyser_0.json").exists()


def test_model_save_roundtrip_supports_rerun_and_model_level_analyses(tmp_path: Path):
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))
    model.run()
    out = model.save(tmp_path / "saved_task1")

    reloaded = load_model(out)
    reloaded.run()

    assert "solver_0" in reloaded.runs
    assert "analyser_0" in reloaded.analyses


def test_run_analysis_records_run_dependency_in_model_level_analysis():
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("pop", "solver_0", DefaultAnalyserConfig(metrics=["population"]))

    model.run()
    analysis = model.analyses["pop"]

    assert analysis.analyser_id == "pop"
    assert analysis.input_run_ids == ["solver_0"]
