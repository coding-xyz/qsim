# 基本用法

本页说明如何用 `qsim` 组织一次完整运行，包括配置文件准备方式、常用命令、推荐目录结构和输出结果的理解方式。对于第一次上手的用户，建议先通读本页，再继续阅读“任务配置”“设备配置”“脉冲配置”“求解器配置”几页。

## 1. 入口方式

当前推荐使用两类入口：

- 命令行入口：`qsim run-task`
- Python 入口：`qsim.workflow.run_task_files()` 或 `qsim.workflow.run_task()`

对于大多数日常运行，建议优先使用 `qsim run-task`，因为它直接围绕配置文件工作，最适合文档化、复现和批量测试。

## 2. 配置文件格式

当前配置加载器支持以下文件格式：

- `.json`
- `.yaml`
- `.yml`

也就是说，`task`、`solver`、`device`、`pulse` 四类配置既可以写成 `JSON`，也可以写成 `YAML`。  
不过仓库自带模板全部采用 `YAML`，因此文档中的手工编写示例也统一使用 `YAML`。如果只是自己编写和维护配置，建议统一使用 `YAML`，可读性更高，也更方便写注释。

## 3. 推荐的四文件组织方式

一次标准运行建议拆成四个文件：

1. `task.yaml`
2. `solver.yaml`
3. `device.yaml`
4. `pulse.yaml`

四者职责如下：

- `task`：定义本次要跑什么任务、输入电路是什么、输出到哪里
- `solver`：定义求解器、运行参数、frame 和 QEC 相关运行选项
- `device`：定义设备和噪声
- `pulse`：定义门时长、载频、读出和 reset 等脉冲参数

这种拆分方式有几个好处：

- 任务目标和物理参数分离，结构更清晰
- 切换引擎时只需要替换 `solver`
- 切换噪声或设备参数时只需要替换 `device`
- 调整脉冲参数时只需要替换 `pulse`

## 4. 推荐目录结构

建议在一个实验目录中按下面方式组织文件：

```text
experiment/
  circuits/
    bell.qasm
  tasks/
    trace.yaml
    qec.yaml
  solvers/
    qutip_default.yaml
    qoptics_default.yaml
  device/
    transmon_default.yaml
    low_noise_lab.yaml
  pulses/
    single_qubit_default.yaml
```

这样有几个直接好处：

- 路径关系清楚，适合长期维护
- `task.yaml` 可以直接引用旁边的 `solver/device/pulse` 文件
- 多组实验可以共享同一套设备或求解器模板

## 5. 最小可运行流程

最简单的使用方式是准备一个 `task.yaml`，在其中引用其他三个配置文件，然后执行：

```bash
qsim run-task --task-config tasks/trace.yaml
```

如果 `task.yaml` 中已经写好了：

- `input.solver_config`
- `input.device_config`
- `input.pulse_config`

那么命令行不需要再重复传这三个参数。

## 6. 最小示例

下面是一个最基础的 `task.yaml` 示例：

```yaml
target: trace
input:
  qasm_path: examples/bell.qasm
  solver_config: solvers/qutip_default.yaml
  device_config: device/transmon_default.yaml
  pulse_config: pulses/single_qubit_default.yaml
output:
  out_dir: runs/demo_trace
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: true
  export_dxf: false
```

执行命令：

```bash
qsim run-task --task-config task.yaml
```

这次运行会完成以下事情：

1. 读取 `task.yaml`
2. 根据 `input.*_config` 继续读取 `solver/device/pulse` 配置
3. 解析 `qasm_path` 指向的量子电路
4. 编译、lowering、构建模型
5. 调用求解器生成 `trace`
6. 按 `output` 设定写出结果和图像

## 7. 命令行覆盖方式

如果你想保留 `task.yaml` 不动，只在某一次运行里临时切换其中一个配置，可以使用命令行覆盖：

```bash
qsim run-task ^
  --task-config task.yaml ^
  --solver-config solvers/julia_qoptics.yaml ^
  --device-config device/low_noise_lab.yaml ^
  --pulse-config pulses/single_qubit_default.yaml
```

覆盖规则可以理解为：

- 先读取 `task.yaml`
- 再用命令行传入的 `solver/device/pulse` 覆盖其中对应路径

这个用法很适合做以下对比实验：

- 同一个任务切换不同求解器
- 同一个任务切换不同设备噪声
- 同一个任务比较不同 pulse 参数

## 8. Python 调用方式

如果你希望在脚本或 notebook 里直接运行，也可以用 Python：

```python
from qsim.workflow import run_task_files

result = run_task_files(task_config="tasks/trace.yaml")
print(result["runtime"]["out_dir"])
```

如果你想临时覆盖某一类配置，也可以：

```python
from qsim.workflow import run_task_files

result = run_task_files(
    task_config="tasks/trace.yaml",
    solver_config="solvers/julia_qoptics.yaml",
)
```

Python 接口最适合以下场景：

- notebook 交互运行
- 自动化脚本
- 对多组任务做批量调度

## 9. 运行结束后会生成什么

默认情况下，结果会被写入 `output.out_dir` 指定的目录。常见产物包括：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `pulse_samples.npz`
- `executable_model.json`
- `model_spec.json`
- `trace.h5`
- `settings_report.json`
- `run_manifest.json`
- `timings.json`

如果任务目标包含 QEC 或进一步分析，还会额外生成：

- `logical_error.json`
- `decoder_output.json`
- `sensitivity_report.json`
- `error_budget_v2.json`
- `decoder_eval_report.json`
- `scaling_report.json`

## 10. 推荐的起步顺序

第一次上手建议按以下顺序：

1. 使用仓库自带模板复制出 4 个配置文件
2. 把 `target` 先设为 `trace`
3. 使用 `qutip` 作为第一个引擎
4. 先确认 `trace.h5`、`settings_report.json` 和图像能正常生成
5. 再逐步打开 `logical_error`、`sensitivity_report` 等目标

这样可以先把基本链路跑通，再逐步增加复杂度。

## 11. 常见依赖选择

基础运行常见会用到：

- `pip install -e .[qutip]`
- `pip install -e .[viz]`

如需更多功能，可按需安装：

- `.[dxf]`：导出 DXF
- `.[stim]`：使用 Stim 相关 QEC 分析
- `.[cirq]`：使用 Cirq 相关 QEC 分析
- `.[xlsx]`：导出 XLSX 表格

## 12. 常见问题

### 为什么我只传了 `task.yaml` 就能跑

因为 `task.yaml` 的 `input` 段里已经记录了另外三个配置文件的路径。

### JSON 和 YAML 到底选哪个

两者都可以。  
如果是手写配置，推荐统一使用 `YAML`。  
如果是自动生成配置，`JSON` 也完全可以。

### 我应该先配 solver 还是先配 task

建议先从 `task.yaml` 入手，因为它决定一次运行的输入、目标和输出；然后再分别完善 `solver/device/pulse`。
