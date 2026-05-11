# 系统架构 (System Architecture)

`qsim` 是一个分层量化仿真工作流系统，旨在提供一个结构稳定、类型安全且可扩展的框架，用于超导量子计算机的噪声抑制研究。

## 1. 核心设计哲学

本系统的核心设计理念是 **"模型驱动 (Model-First)"**。所有的仿真配置、运行状态、中间产物和分析结果都统一组织在一个顶层 `Model` 对象中。

### 1.1 架构目标
- **单一权威来源**：每个概念在系统中只有一个权威的存储位置。
- **关注点分离**：配置 (Config)、运行状态 (State)、中间表示 (IR)、执行结果 (Result) 和分析 (Analysis) 严格分离。
- **类型安全**：优先使用强类型对象（dataclass/schema）而非原始字典，以减少运行时错误并提高代码可维护性。
- **结构稳定**：定义清晰的层级边界，防止功能实现过程中出现结构漂移。

## 2. 逻辑分层

`qsim` 的代码库分为以下关键层级：

| 层级 | 目录 | 职责 |
| :--- | :--- | :--- |
| **Schemas** | `schemas/` | 定义稳定的类型域模型和交换边界（数据结构）。 |
| **Workflow** | `workflow/` | 组合配置、构建运行时任务、编排执行流程、管理模型持久化。 |
| **Backend** | `backend/` | 将量子线路和设备描述编译为可执行的仿真模型。 |
| **Engines** | `engines/` | 具体的数值执行后端（如 QuTiP, Julia 等），消费中立的模型规范。 |
| **Analysis** | `analysis/` | 对轨迹 (Trajectory) 进行后处理，生成指标、读出分析和报告。 |
| **Pulse** | `pulse/` | 脉冲降低 (Lowering)、编译、波形生成及可视化。 |
| **Circuit** | `circuit/` | 线路导入、导出、归一化和门级操作。 |
| **QEC** | `qec/` | 解码器、先验概率、综合征及逻辑错误处理。 |
| **UI/Session** | `ui/`, `session/` | 提供 CLI、Notebook 交互界面和会话管理。 |
| **Common** | `common/` | 共享原语、序列化辅助工具和通用基础类。 |

## 3. 数据流向

系统遵循严格的单向数据流：

`配置 (Config) $\rightarrow$ 运行时契约 (Runtime Contract) $\rightarrow$ 编译产物 (Compiled Artifacts) $\rightarrow$ 引擎结果 (Engine Result) $\rightarrow$ 衍生分析 (Derived Analysis)`

## 4. 核心模型结构

`Model` 对象的逻辑结构如下：

- **Model**
    - `config`: `ModelConfig` (任务, 设备, 求解器, 脉冲, 分析器配置)
    - `state`: `ModelState` (轻量级会话状态，如最后运行的 ID)
    - `registry`: `ModelRegistry` (指标注册表等共享资源)
    - `runs`: `dict[str, ModelRun]` (每次执行的独立记录)
        - `identity`: `RunIdentity` (运行标识)
        - `runtime_task`: `WorkflowTask` (实际执行的任务契约)
        - `artifacts`: `RunArtifacts` (编译产物，如 `ModelSpec`, Pulse IR)
        - `result`: `RunResult` (事实执行结果，如 `Trajectory`)
    - `analyses`: `dict[str, ModelAnalysis]` (基于一个或多个 Run 的后处理结果)
    - `manifest`: `ModelManifest` (元数据清单)