# Noise Simulation Tests

`task1_test_engines.ipynb`, `task2_readout_io.ipynb`, and `task3_relaxation_dephasing.ipynb` are exploratory notebooks.
They include engine comparison, parameter sweeps, plotting, and result post-processing, so they are intentionally heavier than the minimal workflow entrypoint.

If you want the smallest runnable shape, use the self-contained task folders directly under `examples/noise_simulation_tests/`:

- `task1/`
- `task2/`
- `task3/`

Each task folder contains a direct workflow entry built around:

- `task.yaml`
- `solver.yaml` or engine-specific solver files
- `device.yaml`
- `pulse.yaml`

And the Python entrypoint is just:

```python
from pathlib import Path
from qsim.workflow import run_task_files

BASE = Path(__file__).resolve().parent
result = run_task_files(task_config=BASE / "task.yaml")
```

You can run either example directly:

```powershell
python examples/noise_simulation_tests/task1/run.py
python examples/noise_simulation_tests/task2/run.py
python examples/noise_simulation_tests/task3/run.py
```
