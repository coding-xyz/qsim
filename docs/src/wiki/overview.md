# 概览

`qsim` 提供了一条从量子电路输入到仿真、分析和结果归档的完整工作流。它的目标不是只完成某一个单点功能，而是把量子模拟任务中常见的几个环节串成统一流程：电路读取、编译与 lowering、设备和脉冲参数注入、求解器执行、误差分析、量子纠错分析，以及最终的文件输出与结果复现。

## 整体流程

一次典型运行通常包含以下阶段：

1. 读取 `task / solver / device / pulse` 四类配置
2. 解析 OpenQASM 电路并完成标准化
3. 根据设备和脉冲参数执行编译与 lowering
4. 构建求解模型并调用仿真引擎
5. 按任务目标决定是否执行 decode、analysis 或额外插件
6. 导出图像、JSON、HDF5、manifest 和 session 结果

常用入口：

- `qsim.workflow.run_task`
- `qsim.workflow.run_task_files`
- `qsim run-task`

## 功能组成

### 电路层

`src/qsim/circuit/` 负责电路导入、标准化和导出。

- OpenQASM 导入
- 电路标准化
- OpenQASM 导出

### 后端与模型层

`src/qsim/backend/` 负责把电路转换为后续求解所需的数据结构。

- 编译 pipeline
- lowering
- pulse compile
- model build
- scheduling

### 脉冲层

`src/qsim/pulse/` 负责门到脉冲的映射、PulseIR 生成和可视化导出。

- 门到脉冲配方
- pulse sequence 生成
- 脉冲绘图与 DXF 导出
- gate mapping catalog

### 求解与分析层

`src/qsim/engines/` 和 `src/qsim/analysis/` 负责数值求解与结果分析。

- QuTiP 仿真引擎
- Julia 相关求解接口
- sensitivity
- error budget
- Pauli+ / component ablation
- cross-engine compare

### 量子纠错层

`src/qsim/qec/` 提供离线量子纠错分析能力。

- prior 构建
- decoder
- decoder eval
- logical error 汇总

### 工作流与结果管理

`src/qsim/workflow/` 和 `src/qsim/session/` 负责把这些功能组织成可重复执行的任务。

- 配置读取与合并
- target 驱动执行计划
- 主阶段与插件阶段编排
- 产物落盘与 manifest
- session 自动提交

## 任务目标

工作流会根据 `target` 决定执行哪些阶段。当前常见目标包括：

- `trace`
- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`
- `cross_engine_compare`

## 配置组织方式

`qsim` 采用四类配置分工：

- `task`：定义本次任务的目标、输入和输出
- `solver`：定义求解器、运行参数和 frame
- `device`：定义设备与噪声
- `pulse`：定义脉冲相关参数

这种拆分方式便于在不改动整条任务的前提下，单独替换某一类配置做对比实验。
