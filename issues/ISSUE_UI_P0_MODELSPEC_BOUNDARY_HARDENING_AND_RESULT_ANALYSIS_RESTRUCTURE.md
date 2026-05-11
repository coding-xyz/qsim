# [UI-P0] ModelSpec 边界加固与结果/分析结构化重构

## 0. 状态
- 状态：In Progress
- 负责人：待指派
- 更新时间：2026-05-09

## 1. 背景与目标
- 背景：
  - 当前主求解链路在进入引擎前基本统一到 `ModelSpec`，但 solver 后处理仍并行使用 `trajectory/pulse_ir/runtime_metadata` 等多种结构，边界偏软。
  - `model.results` 当前以 `solver_runs` 聚合，单条 `SolverRunResult` 同时承载编译工件、求解输出、分析输出与运行元数据，职责耦合高。
  - analysis 层存在“typed 外壳 + dict 内核”现状，`readout/iq/metrics` 协议缺少强约束，字段演进风险高。
- 目标：
  - 固化从 compile->solver->analysis->visualize 的分层边界，确保 solver 核心只消费 `ModelSpec`。
  - 将结果层与分析层解耦重构：`results` 只承载事实结果，`analyses` 同级管理并支持多结果聚合分析。
  - 完成 analysis 最小 typed 化闭环，先稳定总出口协议，再逐步收敛内部 payload。
- 为什么现在做（业务 / 研究价值）：
  - 支撑后续 study/sweep 扩展与多引擎一致性验证，降低迭代时结构漂移造成的回归风险。
  - 为 notebook/UI/文档建立稳定消费协议，减少隐式字段约定与重复分析实现。

## 2. 范围
- In Scope：
  - 明确并实施四道边界：solver 输入边界、post-solver 结果边界、analysis 输入边界、visualize 消费边界。
  - 重构 `Model` 结果组织：从 `solver_runs` 内嵌分析改为 `results` 与 `analyses` 同级结构。
  - 引入最小分析 schema（先 dataclass typed，保留必要兼容适配）。
  - 修正 workflow 中 run/study/scan 语义分层，避免调度语义与 solver 语义混用。
- Out of Scope：
  - 一次性引入 Pydantic 全面替换所有现有 schema。
  - 全量替换历史持久化文件布局（允许兼容读取与渐进迁移）。
  - 改写数值引擎物理实现细节（QuTiP/Julia 内核方程本身不在本 issue）。

## 3. 输入与输出（I/O）
- 输入：
  - `ModelSpec`（单点求解语义）
  - `RunControl`（执行策略）与 `StudyPlan`（扫描定义）
  - 现有 workflow 运行产物：`trajectory`, `pulse_ir`, `compile_report`, `runtime_metadata`
- 输出：
  - 新版 `Model` 结构（`spec/run_plan/results/analyses`）
  - 单条结果对象（建议命名 `RunResult`）仅承载 `trajectory` 事实与可追溯引用
  - 独立 `AnalysisResult` 列表，支持 `input_result_ids: list[str]`
  - analysis typed 最小协议（`AnalysisOutput` + `IQAnalysis` + `ReadoutAnalysis` + `MetricsOutput`）
- 相关 schema / version（如适用）：
  - `schema_version: 2.0`（Model 顶层）
  - `schema_version: 1.x`（analysis 子对象，可增量升级）

## 4. 技术方案
- 方案概述：
  - 将 solver 运行期原始返回视为内部中间态（raw），统一归一化为稳定结果对象后再进入 analysis。
  - 在 `workflow/model.py` 重构结果容器，明确 `results`（事实）与 `analyses`（解释/聚合）同级。
  - 在 `workflow/stages.py` 收敛 analysis 出口为 typed 对象，再由持久化层做 payload 序列化。
- 关键设计决策：
  - 决策 1：solver 内核仍仅消费 `ModelSpec`，`run/study` 属于编排层，不进入引擎核心接口（确保 IR 边界硬）。
  - 决策 2：`RunResult` 中主结果字段命名使用 `trajectory`（不使用 `simulation`），与现有语义与用户心智对齐。
  - 决策 3：`AnalysisResult` 与 `results` 同级，通过 `input_result_ids` 建立血缘，支持多结果聚合分析。
  - 决策 4：优先 dataclass typed 过渡，后续可平滑升级到 Pydantic（避免一次性大迁移风险）。
- 可替换点 / 扩展点（接口、插件、引擎等）：
  - 扩展点 1：analysis 指标注册机制（`MetricRegistry`）继续保留，但输出契约改为 typed。
  - 扩展点 2：post-solver 归一化器可按引擎实现 adapter，不影响统一 `Trajectory` 结构。

### 4.1 详细目标 Schema 映射

为了确保重构不丢失 `Solver -> Study -> Run` 的层级语义，采用**基于 ID 的溯源图 (Provenance Graph)** 结构：

#### A. Model 顶层分层
```text
Model
├─ spec: ModelSpec (单点求解语义，Solver 唯一输入)
├─ run_plan: RunControl | StudyPlan (运行编排语义：run/study/scan/sweep)
├─ results: dict[result_id, RunResult] (客观事实结果池)
└─ analyses: dict[analysis_id, AnalysisResult] (解释/聚合结论池)
```

#### B. RunResult (事实层)
仅承载求解产物，严禁包含任何分析结论。
- `result_id`: str (全局唯一 ID)
- `trajectory`: Trajectory (唯一核心 payload)
- `provenance`: 溯源元数据
    - `solver_id`: str (指向 Model.solvers)
    - `study_name / study_index`: str/int (溯源至 run_plan 中的具体步骤)
    - `spec_ref`: str (指向产生该结果的 ModelSpec 版本/哈希)
    - `plan_ref`: str (指向触发该运行的编排定义)
- `runtime_metadata`: dict (引擎版本, 耗时, 物理路径等客观记录)
- `schema_version`: str

#### C. AnalysisResult (解释层)
支持 $1 \to 1$ 或 $N \to 1$ 的聚合分析。
- `analysis_id`: str (全局唯一 ID)
- `analyser_id`: str (指向 Model.analysers)
- `input_result_ids`: list[str] (血缘引用：1..N 个 RunResult ID)
- `output`: AnalysisOutput (强类型输出，见下文)
- `schema_version`: str

#### D. AnalysisOutput 强类型拆解
```text
AnalysisOutput
├─ metrics: MetricsOutput | None
│  └─ metric_items: dict[name, MetricSeries] (MetricSeries: {times: list, values: list})
├─ readout: ReadoutAnalysis | None
│  ├─ signals: { quantum: {cavity: ...}, io_chain: {adc: ...} }
│  ├─ demodulation: { mode: ..., window: ... }
│  └─ shots: list[ShotData]
└─ iq: IQAnalysis | None
   ├─ centroids: dict[label, complex]
   ├─ confusion_matrix: {labels: list, values: matrix}
   ├─ assignment_fidelity: float
   ├─ noise_sigma: float
   └─ snr: float
```

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 边界定义固化与 workflow 分层清理  
   - 明确 `ModelSpec`、`RunControl`、`StudyPlan` 的职责边界。  
   - 统一 run/study/scan 的调度语义，移除重复覆盖逻辑。
2. 结果结构重构  
   - 新增 `RunResult`（`trajectory` 为核心字段）与顶层 `results` 列表。  
   - 从 `solver_runs` 模式迁移并保留兼容读取。
3. 分析结构重构  
   - 新增同级 `analyses` 列表，支持 `input_result_ids`（1..N）。  
   - 将 analysis 从“挂在单 run 下”升级为“可跨 run 聚合任务”。
4. analysis typed 最小闭环  
   - 定义并落地 `AnalysisOutput`、`IQAnalysis`、`ReadoutAnalysis`、`MetricsOutput`。  
   - `run_analysis_stage` 出口改 typed，保留旧 payload adapter。
5. 持久化与加载兼容  
   - 更新 `save/load` 逻辑，支持新旧结构双读，优先新结构写出。  
   - 增加 schema version 迁移与兼容测试。
6. 文档与示例同步  
   - 更新 `docs/src` 中 model/workflow/analysis 相关文档。  
   - 更新 notebook 辅助层说明，明确其不重算 analysis 核心口径。

## 7. 验收标准（DoD）
- [ ] solver 核心接口仅消费 `ModelSpec`，且 run/study 不再混入 solver 核心语义
- [ ] `Model` 顶层形成 `spec + run_plan + results + analyses` 分层结构
- [ ] `RunResult` 以 `trajectory` 为事实结果字段，`AnalysisResult` 与 `results` 同级
- [ ] analysis 支持多 `result_id` 聚合输入（`input_result_ids`）
- [ ] `run_analysis_stage` 不再输出裸 dict 作为最终对外结构
- [ ] `docstring` 已补全或更新
- [ ] `docs/` 已补全或更新
- [ ] `docs/src` 与 `docs/site` 已通过构建同步且内容一致

## 8. 测试计划
- 单元测试：
  - `Model` 新结构构造/序列化/反序列化一致性（含 schema version）
  - `RunResult` 与 `AnalysisResult` typed 字段约束测试
  - `input_result_ids` 聚合分析路径测试
- 集成测试：
  - 单 solver + 单 study + 单 analysis 路径端到端测试
  - 单 solver + 多 study + 聚合 analysis 路径端到端测试
  - 多 solver 配置下 analysis 绑定与解析测试
- 回归测试：
  - 旧结果目录可成功 `load_model`
  - notebook 默认展示路径可读取新结构且不破坏现有行为
- 样例命令（如适用）：
  - `pytest -q tests/workflow`
  - `pytest -q tests/analysis`
  - `pytest -q tests/ui`

## 9. 风险与回滚
- 主要风险：
  - 结果结构变更影响保存/加载与 notebook 消费路径。
  - analysis typed 化初期可能导致历史宽松字段被拒绝。
- 缓解策略：
  - 新旧结构双读、统一新结构写；提供 adapter 层逐步迁移。
  - 在 typed 模型中保留受控 `extras` 缓冲字段，并记录 deprecation。
- 回滚策略：
  - 保留旧 `solver_runs` 读取逻辑与 legacy 输出开关，出现阻断时可临时切回旧序列化路径。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 `ModelSpec` 构建链路稳定（`backend/model/build.py` + `workflow/stages.py`）。
- 外部依赖（库 / 环境 / 数据）：
  - 无新增外部依赖（先不引入 Pydantic）。
- 潜在阻塞：
  - 历史 runs 目录结构差异导致兼容逻辑复杂。
  - notebook 层存在重复分析逻辑，需同步收敛消费协议。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：6-8 天
- 负责人：待指派

## 12. 参考
- 相关文件：
  - `src/qsim/schemas/model.py`
  - `src/qsim/workflow/model.py`
  - `src/qsim/workflow/stages.py`
  - `src/qsim/analysis/metrics.py`
  - `src/qsim/analysis/readout_chain.py`
  - `src/qsim/analysis/trajectory_semantics.py`
  - `src/qsim/ui/notebook.py`
- 相关 issue / PR：
  - `issues/done/ISSUE_UI_P0_MODEL_OBJECT_API_AND_SOLVER_ANALYSER_SPLIT.md`
  - `issues/done/ISSUE_UI_P0_WORKFLOW_FINAL_SHAPE_TASK_ONLY.md`
  - `issues/done/ISSUE_UI_P1_WORKFLOW_REFACTOR_TASK_DRIVEN_PIPELINE.md`
- 相关文档：
  - `docs/src/`
