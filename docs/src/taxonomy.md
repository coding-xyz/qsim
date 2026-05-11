# 数据分类学 (Data Taxonomy)

为了保持系统的结构稳定性，`qsim` 对所有重要对象进行了严格的分类。每个对象必须且只能属于以下类别之一。这种分类决定了对象的表示方式（类 vs 字典）及其在 `Model` 中的存储位置。

## 1. 分类矩阵

| 类别 | 语义定义 | 表示要求 | 权威存储位置 | 示例 |
| :--- | :--- | :--- | :--- | :--- |
| **配置 (Config)** | 可编辑的输入定义，通常从文件或 UI 加载。 | 强类型类/dataclass | `Model.config` | `WorkflowTaskConfig`, `WorkflowDeviceConfig` |
| **运行时契约 (Runtime Contract)** | 执行期间在层级之间传递的结构化对象。 | 强类型类/dataclass | `ModelRun.runtime_task` | `WorkflowTask` |
| **域模型 (Domain Model)** | 与具体引擎无关的语义模型。 | 强类型类/dataclass | `RunArtifacts.model_spec` | `ModelSpec` |
| **IR / 产物 (IR / Artifact)** | 解析、归一化、降低或编译产生的中间产物。 | 类型化 IR 类 | `ModelRun.artifacts` | `Pulse IR`, `Normalized Circuit` |
| **结果 (Result)** | 执行过程中直接产生的客观输出。 | 强类型类/dataclass | `ModelRun.result` | `Trajectory`, `RunResult` |
| **衍生分析 (Derived Analysis)** | 基于结果的后处理总结和分析产物。 | 强类型类/dataclass | `Model.analyses` | `ReadoutAnalysis`, `IQAnalysis` |
| **元数据 (Metadata)** | 非核心的注释、调试信息或扩展负载。 | 允许使用 `dict` | 嵌套在强类型父对象中 | `metadata`, `extras` |

## 2. 详细定义与规则

### 2.1 配置 (Config)
配置是用户可调的参数。
- **规则**：绝不能将运行时产物（如编译后的模型）混入配置对象中。
- **目标形态**：`ModelConfig` $\rightarrow$ `(Task, Device, Pulse, Solvers, Analysers)`。

### 2.2 运行时契约 (Runtime Contract)
契约定义了执行层需要做什么。
- **规则**：它由配置派生，但一旦生成，它就属于特定的 `ModelRun`。

### 2.3 域模型 (Domain Model)
`ModelSpec` 是核心的域模型。
- **规则**：一个 Run 必须且只能有一个权威的 `ModelSpec`，存储在 `ModelRun.artifacts.model_spec`。

### 2.4 IR / 产物 (IR / Artifact)
IR 是面向机器的中间表示。
- **规则**：IR 对象应足够丰富，避免使用脆弱的字典键值访问。
- **示例**：Pulse IR 描述了实际发送到硬件的波形序列，而非用户定义的脉冲配置。

### 2.5 结果 (Result)
结果是求解器（Solver）事实性地产生的数据。
- **规则**：`RunResult` 仅存储客观输出（如轨迹），不应存储编译阶段的元数据。

### 2.6 衍生分析 (Derived Analysis)
分析是对结果的加工。
- **规则**：分析存储在 `Model` 级别，因为一次分析可能依赖于多个 `ModelRun`。必须显式声明 `input_run_ids`。

## 3. 类型选择指南

在实现新功能时，请遵循以下选择路径：

1. **是否是核心域概念 $\rightarrow$ 是 $\rightarrow$ 使用强类型 dataclass**
2. **是否是编译/降低过程的中间产物 $\rightarrow$ 是 $\rightarrow$ 使用 IR 类**
3. **是否是需要高度可扩展的非核心信息 $\rightarrow$ 是 $\rightarrow$ 使用嵌套在强类型对象中的 `dict` (名为 `extras` 或 `metadata`)**

**绝对禁忌**：
- $\times$ 使用 `dict[str, Any]` 作为顶层核心结构。
- $\times$ 将运行结果存储在配置对象中。
- $\times$ 在 `Model` 顶层存储特定于某个 Run 的产物。