import json
from pathlib import Path

from qsim.common.schemas import Trajectory
from qsim.workflow import AnalysisResult, DefaultAnalyserConfig, create_model, load_model


def _example_dir(name: str) -> Path:
    return Path("examples/noise_simulation_tests").resolve() / name


def test_model_save_writes_runtime_metadata_and_trajectory(tmp_path: Path):
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))
    model.run()
    out = model.save(tmp_path / "saved_model")

    assert (out / "results" / "solver_0" / "runtime_metadata.json").exists()
    assert (out / "results" / "solver_0" / "trajectory.h5").exists()
    assert (out / "results" / "solver_0" / "analyses" / "analyser_0.json").exists()


def test_model_save_roundtrip_supports_rerun(tmp_path: Path):
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("analyser_0", "solver_0", DefaultAnalyserConfig(metrics=["population"]))
    model.run()
    out = model.save(tmp_path / "saved_task1")

    reloaded = load_model(out)
    reloaded.run()
    assert "solver_0" in reloaded.results.trajectories
    assert "analyser_0" in reloaded.results.analyses


def test_model_save_rewrites_managed_analysis_paths(tmp_path: Path):
    base = _example_dir("task1")
    model = create_model(
        task_config=base / "task.yaml",
        solver_config={
            "qutip": base / "qutip.yaml",
            "qtoolbox": base / "qtoolbox.yaml",
        },
        analyser_config=None,
    )
    model.add_analyser("pop", "qutip", DefaultAnalyserConfig(metrics=["population"]))
    model.results.ensure_solver("qutip").trajectory = Trajectory(
        engine="qutip",
        times=[0.0],
        density_matrix={"actual_kind": "density_matrix", "encoding": "complex", "snapshots": [[[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]]]},
        metadata={},
    )
    model.results.ensure_solver("qutip").analyses["pop"] = AnalysisResult(
        analyser_id="pop",
        trajectory_id="qutip",
        metrics={"population": {"times": [0.0], "values": {"0": [1.0]}}},
    )

    first_out = model.save(tmp_path / "saved_rewrite")
    assert (first_out / "results" / "qutip" / "analyses" / "pop.json").exists()

    model.analysers["pop"].solver_id = "qtoolbox"
    model.results.solver_runs.clear()
    model.results.ensure_solver("qtoolbox").trajectory = Trajectory(
        engine="qtoolbox",
        times=[0.0],
        density_matrix={"actual_kind": "density_matrix", "encoding": "complex", "snapshots": [[[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]]]},
        metadata={},
    )
    model.results.ensure_solver("qtoolbox").analyses["pop"] = AnalysisResult(
        analyser_id="pop",
        trajectory_id="qtoolbox",
        metrics={"population": {"times": [0.0], "values": {"0": [1.0]}}},
    )
    out = model.save(first_out)

    assert not (out / "results" / "qutip" / "analyses" / "pop.json").exists()
    assert (out / "results" / "qtoolbox" / "analyses" / "pop.json").exists()
    saved_payload = json.loads((out / "results" / "qtoolbox" / "analyses" / "pop.json").read_text(encoding="utf-8"))
    assert saved_payload["analyser_id"] == "pop"
    assert saved_payload["trajectory_id"] == "qtoolbox"


def test_result_reprs_omit_absent_optional_sections():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0],
        density_matrix={"actual_kind": "density_matrix", "encoding": "complex", "snapshots": [[[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]]]},
    )
    analysis = AnalysisResult(metrics={"population": {"times": [0.0], "values": {"0": [1.0]}}})

    trajectory_repr = repr(trajectory)
    analysis_repr = repr(analysis)

    assert "wave_function" not in trajectory_repr
    assert "measurements" not in trajectory_repr
    assert "iq" not in analysis_repr
    assert "sensitivity" not in analysis_repr
    assert "error_budget" not in analysis_repr


def test_sparse_instance_annotations_omit_absent_fields():
    trajectory = Trajectory(
        engine="qutip",
        times=[0.0],
        density_matrix={"actual_kind": "density_matrix", "encoding": "complex", "snapshots": [[[1.0 + 0.0j, 0.0j], [0.0j, 0.0j]]]},
    )
    analyser = DefaultAnalyserConfig(solver_id="solver_0", metrics=["population"])
    analysis = AnalysisResult(metrics={"population": {"times": [0.0], "values": {"0": [1.0]}}}, report={})

    assert "density_matrix" in trajectory.__annotations__
    assert "wave_function" not in trajectory.__annotations__
    assert "measurements" not in trajectory.__annotations__
    assert "iq_discrimination" not in analyser.__annotations__
    assert "noise_analysis" not in analyser.__annotations__
    assert "iq" not in analysis.__annotations__
    assert "sensitivity" not in analysis.__annotations__


def test_run_analysis_records_trajectory_id():
    base = _example_dir("task1")
    model = create_model(task_config=base / "task.yaml", analyser_config=None)
    model.add_analyser("pop", "solver_0", DefaultAnalyserConfig(metrics=["population"]))

    model.run()
    analysis = model.results.analyses["pop"]

    assert analysis.analyser_id == "pop"
    assert analysis.trajectory_id == "solver_0"
