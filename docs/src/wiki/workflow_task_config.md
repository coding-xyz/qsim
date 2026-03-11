# Workflow 用法（Task / Solver / Hardware）

## 1. 调用方式

推荐：`task` 主配置中引用 `solver` 和 `hardware` 文件。

### Python

```python
from qsim.workflow import run_task_files

result = run_task_files(task_config="tasks/task_trace.yaml")
print(result["runtime"]["out_dir"])
```

也可用覆盖参数临时替换：

```python
result = run_task_files(
    task_config="tasks/task_trace.yaml",
    solver_config="solvers/qutip_default.yaml",
    hardware_config="hardware/transmon_default.yaml",
)
```

### CLI

```bash
qsim run-task --task-config tasks/task_trace.yaml
```

可选覆盖：

```bash
qsim run-task \
  --task-config tasks/task_trace.yaml \
  --solver-config solvers/qutip_default.yaml \
  --hardware-config hardware/transmon_default.yaml
```

## 2. Task 配置

```yaml
target: trace
input:
  qasm_path: circuits/bell.qasm
  solver_config: solvers/qutip_default.yaml
  hardware_config: hardware/transmon_default.yaml
output:
  out_dir: runs/task_trace
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: false
  export_dxf: false
features: {}
```

- `input`：
  - `qasm_text` 与 `qasm_path` 二选一
  - 必填：`solver_config`, `hardware_config`
  - 可选：`param_bindings`
- `output`：
  - 必填：`out_dir`
  - 可选：`persist_artifacts`, `artifact_mode`, `export_plots`, `export_dxf`, `session_*`

## 3. Solver 配置

按你确认的 key 列表：

```yaml
backend:
  level: qubit
  analysis_pipeline: default
  truncation: {}
run:
  engine: qutip
  solver_mode: me
  sweep: []
  seed: 1234
  dt: 1.0
  schedule_policy: serial
  reset_feedback_policy: parallel
```

说明：
- `solver` 配置中没有 `hardware` 顶层 key。
- `decoder` 不是动力学必须项；仅 QEC 目标需要。

## 4. Hardware 配置

当前先保持简单：

```yaml
hardware: {}
noise:
  model: markovian_lindblad
  t1: 5.0e-5
  t2: 3.0e-5
```

## 5. 目标与依赖规则

- `trace` 目标：不要求 `decoder`。
- `logical_error / sensitivity_report / decoder_eval_report / scaling_report / error_budget_pauli_plus`：要求 `run.decoder`。
- `cross_engine_compare`：要求 `run.compare_engines`。

## 6. Engine 依赖规则

通用 `run` 键：
- `engine`, `solver_mode`, `sweep`, `seed`, `dt`, `schedule_policy`, `reset_feedback_policy`
- `compare_engines`, `allow_mock_fallback`, `mcwf_ntraj`
- `prior_backend`, `decoder`, `decoder_options`, `qec_engine`

Julia 专属键：
- `julia_bin`, `julia_depot_path`, `julia_timeout_s`

`engine=qutip` 传入 Julia 专属键会报错。
