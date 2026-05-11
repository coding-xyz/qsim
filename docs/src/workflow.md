# 工作流指南 (Workflow Guide)

`qsim` 采用一个统一的、以模型为中心的仿真工作流。本指南介绍了从创建模型到执行分析的完整生命周期。

## 1. 标准仿真流程

一个典型的仿真任务遵循以下步骤：

### 1.1 创建模型 (Model Creation)
使用 `create_model` 函数将各种配置文件加载到一个 `Model` 对象中。
- **输入**：任务配置 (`task_config`)、求解器配置 (`solver_config`)、设备配置 (`device_config`) 等。
- **结果**：一个初始化完毕的 `Model` 对象，包含所有必要的配置。

### 1.2 执行求解 (Solving)
通过调用 `model.run_solver()` 或 `model.run_study()`，系统会执行以下内部链路：
1. **编译**：`Backend` 将 `ModelConfig` 转换为 `ModelSpec`（域模型）和 `Pulse IR`（脉冲中间表示）。
2. **执行**：`Engine` 消费 `ModelSpec` 并运行数值仿真。
3. **存储**：结果被封装在 `RunResult` 中，连同编译产物一起存储在 `ModelRun` 中，并添加到 `model.runs` 字典。

### 1.3 执行分析 (Analysis)
使用 `model.run_analysis()` 对一个或多个运行结果进行后处理。
- **输入**：分析器 ID (`analyser_id`)。
- **过程**：分析器读取 `model.runs` 中的 `Trajectory` 数据，计算指标（Metrics）。
- **存储**：分析产物存储在 `ModelAnalysis` 对象中，并添加到 `model.analyses` 字典。

### 1.4 持久化 (Persistence)
使用 `model.save(path)` 将整个模型（包括所有配置、运行记录和分析结果）保存到磁盘。之后可以通过 `load_model(path)` 快速恢复会话。

## 2. 核心 API 速查

| 操作 | API 方法 | 描述 |
| :--- | :--- | :--- |
| **初始化** | `create_model(...)` | 从文件构建 `Model` |
| **单步运行** | `model.run_study(...)` | 运行一个特定的研究步骤 |
| **全量求解** | `model.run_solver(solver_id)` | 运行指定求解器的所有步骤 |
| **执行分析** | `model.run_analysis(...)` | 运行指定的分析器 |
| **一键运行** | `model.run_all()` | 运行所有求解器 $\rightarrow$ 所有分析器 |
| **保存/加载** | `model.save()` / `load_model()` | 模型持久化 |

## 3. 结果访问

你可以通过 `Model` 提供的便捷方法访问最终结果：
- **获取轨迹**：`model.get_trajectory(solver_id=..., study_name=...)`
- **获取分析结果**：`model.get_analysis(analyser_id=..., study_name=...)`