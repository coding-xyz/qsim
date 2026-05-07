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

Task7 runs QuTiP HEOM for 1/f dephasing and compares delay sweeps:
Ramsey (`pi/2 - delay - pi/2 - measure`) against spin echo
(`pi/2 - delay/2 - pi - delay/2 - pi/2 - measure`). The delay is
implemented with QASM `id` gates and controlled by `pulse.idle_duration_ns`.

```bash
python examples/noise_simulation_tests/task7/run.py
```

The display notebook is:

```text
examples/noise_simulation_tests/task7_1overf_spin_echo.ipynb
```
