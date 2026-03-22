# qsim

`qsim` 是一个面向量子电路仿真、脉冲建模和量子纠错分析的工作流工具。它把一次仿真任务拆分为清晰的配置文件和标准化执行阶段，使电路输入、设备参数、求解器设置、脉冲参数和分析产物可以被统一管理、重复运行和稳定复现。

项目当前覆盖的核心能力包括：

- 读取 OpenQASM 电路并完成标准化处理
- 将电路编译并 lowering 到脉冲与可执行模型
- 通过 QuTiP 或 Julia 相关后端接口执行仿真
- 生成 trace、可视化图像、误差分析和量子纠错相关产物
- 将运行结果写入结构化输出目录，并生成 manifest 与 session 归档

## 适用场景

`qsim` 适合以下几类工作：

- 快速验证一个量子电路在给定设备和噪声参数下的仿真结果
- 统一管理 task / solver / device / pulse 四类配置
- 产出可复现的 trace、图像和分析文件
- 对 decoder、logical error、sensitivity、Pauli+ 等结果做离线分析

## 主要模块

- `src/qsim/workflow/`：任务装配、配置加载、执行计划、产物落盘
- `src/qsim/circuit/`：QASM 导入与电路标准化
- `src/qsim/backend/`：编译、lowering、模型构建
- `src/qsim/pulse/`：脉冲配方、序列、可视化
- `src/qsim/engines/`：仿真与 QEC 分析引擎
- `src/qsim/qec/`：prior、decoder、decoder eval
- `src/qsim/analysis/`：sensitivity、error budget、Pauli+
- `src/qsim/session/`：结果归档与 session 管理

## 安装依赖

最低运行依赖定义在 `pyproject.toml`：

```bash
pip install -e .
```

常见可选依赖：

- `pip install -e .[qutip]`：使用 QuTiP 求解器
- `pip install -e .[viz]`：导出 matplotlib 图
- `pip install -e .[dxf]`：导出 DXF
- `pip install -e .[stim]`：启用 Stim 相关 QEC 分析
- `pip install -e .[cirq]`：启用 Cirq 相关 QEC 分析
- `pip install -e .[xlsx]`：把 JSON 表格导出为 `.xlsx`
- `pip install -e .[docs]`：构建文档站点

如果只想先跑通基础流程，推荐至少安装：

```bash
pip install -e .[qutip,viz]
```

## 快速开始

`qsim` 的常用入口是 Python API `run_task` / `run_task_files`，以及命令行 `qsim run-task`。

配置文件格式方面，当前加载器同时支持：

- `.json`
- `.yaml`
- `.yml`

但项目内置模板全部使用 `YAML`，文档示例也统一按 `YAML` 编写。实际使用时，推荐直接使用 `YAML`。

最基本的流程是准备 4 个配置文件，然后执行：

```bash
qsim run-task --task-config path/to/task.yaml
```

如果 `task.yaml` 里已经写了另外 3 个配置文件路径，这一条命令就够了。也可以在命令行临时覆盖：

```bash
qsim run-task ^
  --task-config path/to/task.yaml ^
  --solver-config path/to/solver.yaml ^
  --device-config path/to/device.yaml ^
  --pulse-config path/to/pulse.yaml
```

对应的 Python 入口：

```python
from qsim.workflow import run_task_files

result = run_task_files(task_config="path/to/task.yaml")
print(result["runtime"]["out_dir"])
```

一次典型运行会经历：

1. 读取任务配置和输入电路
2. 合并 solver / device / pulse 配置
3. 编译电路并生成模型
4. 调用求解引擎执行仿真
5. 导出 trace、图像和分析产物

## 4 个配置文件分别管什么

### 1. task 配置

任务入口文件，负责描述这次要跑什么、输出到哪里、是否开启额外分析。

- `target`：本次运行目标，例如 `trace`、`logical_error`
- `input`：QASM 输入，以及另外 3 个配置文件路径
- `output`：输出目录、图形导出、session 提交
- `features`：可选分支，如 `decoder_eval`、`pauli_plus_analysis`

### 2. solver 配置

求解器和运行时配置，主要对应 `WorkflowSolverConfig`。

- `backend`：模型级别、analysis pipeline、truncation
- `run`：`engine`、`solver_mode`、时间步长、decoder 相关参数
- `frame`：reference frame 与 RWA 设置

### 3. device 配置

设备与噪声配置，主要对应 `WorkflowDeviceConfig`。

- `device`：器件参数、仿真层级相关参数
- `noise`：噪声模型与退相干时间等

### 4. pulse 配置

脉冲层参数，运行时会并入 device 配置中的 `pulse` 字段。

- 单比特门时长
- XY/RO 载频
- 读出、reset 等脉冲细节

## 推荐阅读顺序

1. [概览](wiki/overview.md)
2. [基本用法](wiki/basic_usage.md)
3. [任务配置](wiki/workflow_task_config.md)
4. [设备配置](wiki/device_config.md)
5. [脉冲配置](wiki/pulse_config.md)
6. [求解器配置](wiki/solver_config.md)
7. [可视化](wiki/visualization.md)
8. [量子纠错](wiki/qec_analysis.md)
9. [文件 IO](wiki/io_session.md)
10. [开发进度](wiki/gaps.md)

## 文档维护

- 文档源文件在 `docs/src/`
- 生成站点在 `docs/site/`
- 本地预览：`mkdocs serve`
- 重新构建：`mkdocs build --clean`
