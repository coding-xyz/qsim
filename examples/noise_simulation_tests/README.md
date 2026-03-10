# Noise Simulation Tests

这个目录统一承载当前噪声仿真相关的 notebook、配置文件、运行结果和专题拆分内容。

## 目录说明

- `required_tasks_tri_engine.ipynb`
  - 对应 `required_tasks.txt` 的 7 个任务。
  - 现在改为“配置文件 + 直接调用 `run_workflow`”的工作范式，不再在 notebook 里定义专用的参数扫描函数。
- `required_tasks_tri_engine/`
  - `required_tasks_tri_engine.ipynb` 使用的任务配置目录。
  - 每个任务一个 JSON 文件，文件内直接包含 QASM、case、引擎列表以及展示指标。
- `roadmap_2026H1/`
  - 同一批噪声仿真工作的专题拆分版。
- `runs/`
  - 存放本目录下 notebook 生成的结果。
  - `runs/required_tasks_tri_engine/`：7 个任务的集中对比结果。
  - `runs/roadmap_2026H1/`：专题 notebook 的运行结果。

## 当前约定

- 跟本批噪声仿真测试直接相关的内容，统一收口到 `examples/noise_simulation_tests/`。
- 如果继续扩展三引擎噪声对比，优先在本目录下新增配置文件、notebook 或子目录，而不是再分散到 `examples/notebooks/` 或 `examples/runs/`。
- 三引擎结果解读时，优先看 `state_encoding` 和 `compare_status`。
  - `per_qubit_excited_probability`：可以做逐项数值对比。
  - `basis_population_single_qubit`：可做单比特基态/激发态人口解释，但不应直接当成多比特逐比特概率。
  - `ambiguous_population_vector`：需要先做语义审查，不直接做逐项误差比较。

## Task1 Visual Compare (Issue DYN-P1)

- Script: `examples/noise_simulation_tests/task1_single_qubit_visual_compare.py`
- Purpose:
  - Read existing Task1 run artifacts under `runs/required_tasks_tri_engine/`.
  - Build semantically aligned single-qubit `p1(t)` dynamics for all engines.
  - Export PNG/CSV artifacts for manual engine-call validation.
- Default output directory:
  - `<repo>/task1_outputs/`
- Run command:
  - `python examples/noise_simulation_tests/task1_single_qubit_visual_compare.py`
  - optional: `--out-dir <path>`
- Generated files (default):
  - `task1_single_qubit_baseline_visual_compare_summary.csv`
  - `task1_p1_dynamics_long.csv`
  - `task1_baseline_p1_dynamics.png`
  - `task1_detuned_p1_dynamics.png`
  - `task1_final_p1_bar.png`

## Task1 Native References

- `examples/noise_simulation_tests/task1_qutip_native_reference.py`
- `examples/noise_simulation_tests/task1_quantumoptics_native_reference.jl`
- `examples/noise_simulation_tests/task1_quantumtoolbox_native_reference.jl`

These references provide a direct native-solver baseline for trend-level checks
(`final_p1`, `mean_p1`, curve shape) when verifying that your engine path is
actually invoking the intended backend.

- Unified one-click runner:
  - `examples/noise_simulation_tests/task1_native_tri_compare.py`
  - Run:
    - `python examples/noise_simulation_tests/task1_native_tri_compare.py`
    - only QuTiP: `python examples/noise_simulation_tests/task1_native_tri_compare.py --skip-julia`
    - custom Julia binary: `python examples/noise_simulation_tests/task1_native_tri_compare.py --julia-bin <path>`
  - Output:
    - `<repo>/task1_outputs/task1_native_tri_compare_summary.csv`
