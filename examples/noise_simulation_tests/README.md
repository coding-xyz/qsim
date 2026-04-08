# Noise Simulation Tests

These examples now use the model-first API.

```python
from pathlib import Path

from qsim.workflow import create_model

BASE = Path("examples/noise_simulation_tests/task1")
model = create_model(task_config=BASE / "task.yaml")
model.run()

trajectory = model.results.trajectories["solver_0"]
analysis = model.results.analyses["analyser_0"]
```
