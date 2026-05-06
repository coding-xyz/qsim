# 概览

`qsim` 是一条 workflow-first 的量子仿真管线。它把一次运行拆成配置、标准化 IR、engine-neutral 模型、engine-specific runtime 和可复现输出，方便比较不同设备、脉冲、噪声和求解器设置。

## 整体流程

一次典型运行通常经过：

1. 读取 `task / solver / device / pulse / analyser` 五类配置
2. 解析 OpenQASM 或已有 `CircuitIR`
3. 根据设备和脉冲配置生成 `PulseIR` 与 `ExecutableModel`
4. lower 成 engine-neutral `ModelSpec`
5. 选定 engine，把 `ModelSpec` 转成后端 runtime
6. 运行求解器并生成 `Trajectory`
7. 根据 analyser 配置生成派生分析结果
8. 写出 `model_spec.json`、`trajectory.h5`、`settings_report.json` 和 manifest

常用入口：

- CLI：`qsim run-model`
- Python：`qsim.workflow.create_model`

## 核心 IR

qsim 当前主要 IR 分层是：

```text
CircuitIR
  逻辑电路和门序列

PulseIR
  采样前的通道、pulse 和 carrier 描述

ExecutableModel
  pulse lowering 后传给模型构建阶段的中间对象

ModelSpec
  engine-neutral simulation IR

Trajectory
  engine 运行后的时间序列、测量和 metadata
```

`ModelSpec` 是最重要的边界：它描述模型本身，不绑定某个 engine。真正执行时，workflow 或 `SolverSpec.engine` 决定使用 `qutip`、`qoptics` 或 `qtoolbox`。

## 代码模块分工

### `src/qsim/workflow/`

负责把配置组织成一次可执行任务：

- 配置读取与模板合并
- target 驱动的执行计划
- 主 pipeline 和可选插件阶段
- 产物落盘与 manifest

### `src/qsim/circuit/`

负责电路导入、标准化与导出。

### `src/qsim/pulse/`

负责 pulse catalog、门到脉冲 lowering、采样和可视化。

### `src/qsim/backend/`

负责从标准化配置构建 engine-neutral `ModelSpec`。这里不应该出现 QuTiP `Qobj`、Julia runtime 调用或某个 engine 私有 API。

### `src/qsim/schemas/`

保存公开 IR 和配置 dataclass。`qsim.common.schemas` 目前只是兼容导出入口，新代码优先从 `qsim.schemas` 或其子模块导入。

### `src/qsim/engines/`

负责数值求解 engine。QuTiP、QuantumOptics.jl 和 QuantumToolbox.jl 各自把 `ModelSpec` 转成自己的 runtime 表示。

### `src/qsim/analysis/` 和 `src/qsim/qec/`

负责 trajectory 后处理、observable、error budget、decoder eval、scaling 和 Pauli+ 相关流程。

## 当前推荐口径

- `task`：描述目标、输入路径和输出策略
- `solver`：描述运行 engine、solver mode、时间步长和参考系
- `device`：描述组件、连接和噪声
- `pulse`：描述 gate-to-pulse catalog、通道和采样设置
- `analyser`：描述从 `Trajectory` 出发的派生分析

如果只记一条规则：

> 配置文件面向用户，`ModelSpec` 面向 engine，`Trajectory` 面向分析。

## 常用目标

当前常用 `target` 包括：

- `trajectory`
- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`
- `cross_engine_compare`
