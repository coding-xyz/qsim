# 基本用法

本页说明如何用仓库里的模板和示例，组织一套可运行的 `qsim` 配置。

## 最小可运行示例

仓库自带的单比特示例是最好的起点：

```bash
qsim run-task --task-config examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml
```

这份任务会引用：

- `templates/solvers/qutip.yaml`
- `templates/devices/single_qubit.yaml`
- `templates/pulses/single_qubit.yaml`

## 四类配置文件

一套标准运行通常拆成四个文件：

1. `task.yaml`
2. `solver.yaml`
3. `device.yaml`
4. `pulse.yaml`

它们分别负责：

- `task`：目标、输入电路、输出目录
- `solver`：引擎、时间步长、分析设置
- `device`：设备结构、物理参数、噪声参数
- `pulse`：通道、载频、波形和操作映射

## 推荐起步方式

最实用的起步方式通常是：

1. 复制 `examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml`
2. 复制 `templates/solvers/qutip.yaml`
3. 复制 `templates/devices/single_qubit.yaml`
4. 复制 `templates/pulses/single_qubit.yaml`
5. 先只改相对路径、输出目录和少量物理参数

## 最小任务示例

当前推荐的 `task` 写法仍然是扁平结构：

```yaml
schema_version: "3.0"
target: trace
input:
  qasm_text: |
    OPENQASM 3;
    include "stdgates.inc";
    qubit[1] q;
    bit[1] c;
    x q[0];
    measure q[0] -> c[0];
  solver_config: ../../../templates/solvers/qutip.yaml
  device_config: ../../../templates/devices/single_qubit.yaml
  pulse_config: ../../../templates/pulses/single_qubit.yaml
output:
  out_dir: ../runs/demo_trace
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: false
  export_dxf: false
features: {}
tags: [demo]
```

然后运行：

```bash
qsim run-task --task-config path/to/task.yaml
```

## 路径解析规则

`task.input.solver_config`、`device_config`、`pulse_config` 和 `qasm_path` 都会相对当前 `task.yaml` 所在目录解析。

## 命令行覆盖

如果你想保留任务文件不动，只在某次运行里临时切换外部配置，可以直接覆盖：

```bash
qsim run-task ^
  --task-config examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml ^
  --solver-config templates/solvers/qoptics.yaml ^
  --device-config templates/devices/single_qubit.yaml ^
  --pulse-config templates/pulses/single_qubit.yaml
```

## Python 调用

```python
from qsim.workflow import run_task_files

result = run_task_files(
    task_config="examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml",
)
print(result["artifacts"]["out_dir"])
```

## 常见输出

常见输出包括：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `model_spec.json`
- `trace.h5`
- `settings_report.json`
- `run_manifest.json`

## 上手建议

建议按这个顺序逐步加复杂度：

1. 先跑 `trace`
2. 先用 `qutip`
3. 先确认 `trace.h5` 和 `pulse_ir.json` 正常生成
4. 再引入 readout、reset 和更复杂设备结构
5. 最后再增加分析目标
