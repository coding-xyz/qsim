# Noise Simulation Tests

这个目录现在采用“保留任务/参考文件，薄 notebook 调 helper”的结构。

## 保留不动的内容

- `required_tasks/`
  - 继续保存各个任务的原始 JSON 描述。
  - notebook 不再自己展开一堆参数，而是直接读取这里的文件。
- `references/`
  - 继续保存 Task1 的原生参考实现。
  - notebook 和脚本会直接读取这里的 reference 输出做对比。

## 新的最小调用层

- `minimal_workflow_helpers.py`
  - 把 `required_tasks/*.json` 适配到当前 `qsim.workflow.run_task(...)`。
  - 提供：
    - `run_required_task_grid(...)`
    - `run_required_task_suite(...)`
    - `load_task1_references(...)`
    - `compare_task1_to_references(...)`
    - `plot_case_series(...)`

这样 notebook 里通常只需要几行：

```python
from minimal_workflow_helpers import run_required_task_grid

bundle = run_required_task_grid(
    "required_tasks/task1_single_qubit_baseline.json",
    persist_artifacts=False,
)
```

## Notebook 约定

- `task1_tri_engine_compare.ipynb`
  - 最小化运行 Task1。
  - 直接用当前 qsim workflow 跑三引擎。
  - 和 `references/` 里的 native reference 做对比。
- `required_tasks_tri_engine.ipynb`
  - 最小化批量跑 `required_tasks/`。
  - 默认只跑 `qutip`，需要时可改成任务自带的三引擎列表。
- `roadmap_2026H1/*.ipynb`
  - 现在都是薄封装 notebook。
  - 每个 notebook 只选一个对应任务文件，调用 helper，展示简表。

## Task1 Reference CSV

- Script: `task1_native_tri_compare.py`
- Purpose:
  - 运行 `references/` 下的 Task1 native references
  - 导出紧凑 CSV 汇总
- Run:
  - `python examples/noise_simulation_tests/task1_native_tri_compare.py`
  - `python examples/noise_simulation_tests/task1_native_tri_compare.py --skip-julia`
  - `python examples/noise_simulation_tests/task1_native_tri_compare.py --julia-bin <path>`
