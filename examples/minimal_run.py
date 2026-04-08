from pathlib import Path

from qsim.workflow import create_model


if __name__ == "__main__":
    base = Path("examples/noise_simulation_tests/task1")
    model = create_model(task_config=base / "task.yaml")
    model.run()
    print(model.results.trajectories["solver_0"].engine)
