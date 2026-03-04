# Noise Simulation Tests

这个目录统一承载当前噪声仿真相关的 notebook、结果和专题拆分内容。

## 目录说明

- `required_tasks_tri_engine.ipynb`
  - 对应 `required_tasks.txt` 的 7 个任务。
  - 核心目标是对 `qutip`、`quantumtoolbox.jl`、`quantumoptics.jl` 做横向对比。
- `roadmap_2026H1/`
  - 是同一批噪声仿真工作的专题拆分版。
  - 可以理解为 `tri_engine` 任务包的分册和扩展研究记录，不再视为独立平行项目。
- `runs/`
  - 统一放本目录下 notebook 生成的结果。
  - `runs/required_tasks_tri_engine/`：7 个任务的集中对比结果。
  - `runs/roadmap_2026H1/`：专题 notebook 的运行结果。

## 当前约定

- 跟本批噪声仿真测试直接相关的内容，统一收口到 `examples/noise_simulation_tests/`。
- 若后续继续扩展三引擎噪声对比，优先在本目录下新增 notebook 或子目录，而不是再在 `examples/notebooks/`、`examples/runs/` 下平行散落。
- 三引擎结果解读时，优先看 `state_encoding` 与 `compare_status`：
  - `per_qubit_excited_probability`：可做逐项数值对比。
  - `basis_population_single_qubit`：可做单比特基态/激发态人口解释，但不应误当成多比特逐比特概率。
  - `ambiguous_population_vector`：需要先做语义审查，不直接做逐项误差比较。
