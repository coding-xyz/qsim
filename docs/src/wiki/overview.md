# 概览

`qsim` 提供了一条从电路输入、编译与 lowering，到求解、分析、产物落盘的完整工作流。它的核心目标不是单点功能，而是把一整次仿真任务稳定地组织成“配置 -> 执行 -> 产物 -> 复现”。

## 整体流程

一次典型运行通常包含以下阶段：

1. 读取 `task / solver / device / pulse / analyser` 五类配置
2. 解析 OpenQASM 电路并做标准化
3. 根据设备与脉冲参数完成 lowering 和模型构建
4. 调用求解器运行仿真并生成 raw `trajectory`
5. 调用 analyser 基于 `trajectory` 生成派生分析结果
6. 把中间产物和最终结果写入输出目录

常用入口有：

- CLI：`qsim run-model`
- Python：`qsim.workflow.create_model`

## 代码模块分工

### `src/qsim/workflow/`

负责把五类配置组织成一次可执行任务，包括：

- 配置读取与模板合并
- target 驱动的执行计划
- 主 pipeline 和可选插件阶段
- 产物落盘与 manifest

### `src/qsim/circuit/`

负责电路导入、标准化与导出。

### `src/qsim/backend/`

负责 compile pipeline、lowering、调度和 `ExecutableModel -> ModelSpec` 的构建。

### `src/qsim/pulse/`

负责脉冲 catalog、序列生成、采样与可视化。

### `src/qsim/engines/`

负责数值求解引擎接入。

### `src/qsim/qec/`

负责 logical error、decoder eval、scaling 和 Pauli+ 相关分析流程。

### `src/qsim/analysis/`

负责 observables、error budget、sensitivity 等分析逻辑。

## 当前推荐口径

当前对外只保留一套最新文档口径：

- `task`：继续使用扁平写法
- `device`：使用组件化设备结构
- `pulse`：使用结构化脉冲描述
- `solver`：只负责数值求解
- `analyser`：只负责派生分析

如果你只记一条规则，建议记住这句：

> 以当前模板和当前加载器真实支持的字段为准。

## 常用目标

当前常用 `target` 包括：

- `trajectory`
- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`
- `cross_engine_compare`


