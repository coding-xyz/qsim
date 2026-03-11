# [UI-P1] Task-Driven Workflow 重构：主链路与分支链路解耦

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-10
- 实施进展：
  - [x] PR1（contracts + facade）已落地：新增 `qsim.workflow`，`ui.notebook.run_workflow` 已变为兼容入口。
  - [x] PR2（runner/pipeline 分层）已落地：执行主体下沉到 `qsim.workflow.pipeline`，`runner`/`ui` 仅保留入口封装。
  - [x] PR3（stages/plugins/output 分层）已落地：`pipeline` 仅负责编排，主阶段、可选分支、输出辅助已拆分到独立模块。
  - [x] PR4（persistence service 分层）已落地：artifact 写盘、可视化导出、依赖采集与 manifest 组装已迁移到 `qsim.workflow.persistence`。
  - [x] PR5（task contract 分段）已落地：`WorkflowTask` 已拆分为 `WorkflowInput/RunOptions/FeatureFlags/OutputOptions` 并保留 legacy 参数兼容映射。
  - [x] PR6（task file 入口）已落地：新增 `qsim.workflow.task_io.load_task_file`，CLI 新增 `run-task --task-config`。
  - [x] PR7（session 适配收口）已落地：workflow 支持 `session_auto_commit`，新增 `session_commit_report` 与 CLI/session 配置映射。
  - [x] 文档同步：`docs/src` 已更新 workflow 分层入口说明，并完成 `mkdocs build --clean` 同步 `docs/site`。
  - [x] 兼容性回归：`pytest` 全量通过（64 passed）。
  - [x] 最终收口验证：`mkdocs build --clean` 无 warning；workflow 相关新增测试通过（5 passed）。

## 1. 背景与目标
- 背景：
  - 当前 `src/qsim/ui/notebook.py` 中 `run_workflow` 同时承担主仿真、QEC 分析、可视化导出、落盘、manifest 组装，职责耦合严重。
  - 参数数量和分支逻辑持续增长，导致测试粒度粗、维护成本高、变更风险大。
  - `docs/src` 与 `docs/site` 长期被并行修改，出现内容与功能不一致。
- 目标：
  - 建立“任务文件 + 配置文件 -> 模拟结果”的清晰主流程。
  - 将主链路（必须执行）和分支链路（按开关执行）解耦。
  - 将输出副作用（artifact/viz/manifest）从计算流程中拆分。
  - 建立文档单一真源策略：`docs/src` 为源，`docs/site` 仅作为构建产物。

## 2. 范围
- In Scope：
  - 设计并落地统一任务契约（Task/Result/Context）。
  - 拆分 `run_workflow` 为编排层、阶段层、输出层。
  - 明确主链路与分支链路的执行协议。
  - 建立并执行 docs 同步规则（`docs/src -> mkdocs build -> docs/site`）。
- Out of Scope：
  - 改写底层数值引擎算法（QuTiP/Julia/Stim/Cirq）。
  - 引入分布式调度系统。
  - 大幅变更 CLI 对外参数语义。

## 3. 输入与输出（I/O）
- 输入：
  - 任务文件（program/backend/hardware/noise/algorithm）
  - 运行配置（engine/solver/seed/features/output policy）
- 输出：
  - 统一 `SimulationResult`（内存对象）
  - 可选 artifacts（JSON/H5/CSV/PNG/manifest）
  - 可选 session revisions
- schema/version：
  - `task_schema_version: 1.0`
  - `result_schema_version: 1.0`

## 4. 技术方案
- 方案概述：
  - 新增 workflow 模块，形成三层结构：
    - Application：`run_task(task) -> result`
    - Domain stages：compile/simulate/decode/analysis
    - Infrastructure：persist/viz/manifest/session
  - `run_workflow` 保留为兼容 facade，仅做参数映射与结果投影。
- 关键决策：
  - 主链路固定顺序，确保“给任务就出结果”。
  - 分支能力通过插件阶段接入，避免主函数堆叠 `if`。
  - `Session` 只做版本追溯，不承担求解逻辑。
  - 文档维护统一为“源-构建”模式，禁止直接手改 `docs/site`。

## 5. 固定流程
1. 先完成结构拆分与兼容层接入。
2. 同步更新相关 `docstring`。
3. 同步更新 `docs/src/` 文档。
4. 执行 `mkdocs build --clean` 同步生成 `docs/site/`。
5. 提交前确认代码、测试、docstring、docs 全部一致。

## 6. 任务拆分
1. 定义 `SimulationTask` / `SimulationResult` / `WorkflowContext`。
2. 提取主链路阶段：parse/compile/lower/build_model/engine_run/basic_analysis。
3. 提取分支插件：decoder_eval、pauli_plus、cross_engine_compare。
4. 提取输出服务：artifact writer、viz exporter、manifest builder。
5. 接入 `Session` 适配器（可选 commit 策略）。
6. 将 `run_workflow` 改为兼容 facade，保持 CLI/Notebook 现有行为。
7. 补齐测试和文档同步规范。

## 6.1 旧代码整合与迁移路径
- 归属映射（from -> to）：
  - `src/qsim/ui/notebook.py::run_workflow` -> facade（参数归一化、编排调用、兼容返回）
  - 主链路片段 -> `workflow/pipeline.py` 固定 stages
  - 分支片段 -> `workflow/plugins/*.py`
  - 写盘/绘图/manifest -> `workflow/output/*.py`
  - `src/qsim/ui/cli.py` -> 保持命令形态，仅切到 facade
  - `src/qsim/ui/result_summary.py` -> 兼容旧 dict + 新 result
  - `src/qsim/session/session.py` -> 保持 `commit/get` API，新增 workflow 适配
- 分阶段迁移（按 PR）：
  1. PR1：contracts + facade（零语义变更）
  2. PR2：主链路迁移到 stages
  3. PR3：分支迁移到 plugins
  4. PR4：输出副作用迁移到 output services
  5. PR5：session 收口 + docs + 回归基线
- 兼容期策略：
  - 保留 `run_workflow` 签名至少一个版本周期。
  - 保留关键返回字段，必要时由新对象投影生成。
  - 旧内部路径标注 deprecated，不立即删除。

## 7. 验收标准（DoD）
- [x] CLI/Notebook 主入口保持可用且默认行为不回归。
- [x] `run_workflow` 显著瘦身，主链路和分支链路已物理拆分。
- [x] 输出副作用与核心计算解耦。
- [x] `Session` 职责清晰且不侵入求解流程。
- [x] `timings` 阶段语义保持清晰。
- [x] `docs/src` 与 `docs/site` 已同步，且无手改 `docs/site` 痕迹。
- [x] 文档中已明确“`docs/src` 为真源，`docs/site` 为构建产物”。

## 8. 测试计划
- 单元测试：
  - Task/Result schema 校验。
  - stage 输入输出契约。
  - output policy 开关行为。
- 集成测试：
  - `qasm + backend -> trace + analysis` smoke。
  - decoder_eval/pauli_plus/compare 分支回归。
- 文档一致性检查：
  - 修改 `docs/src` 后执行 `mkdocs build --clean`。
  - 确认 `docs/site` 与当前源码文档一致。

## 9. 风险与回滚
- 主要风险：
  - 阶段拆分后默认参数或落盘路径发生隐性变化。
  - 兼容层覆盖不完整引起 CLI 行为偏差。
- 缓解：
  - 先做结构重构，不改业务语义。
  - 增加 golden-output 回归对比。
- 回滚：
  - 保留短期开关，必要时回退到旧编排路径。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 `engine.run` 与 QEC 接口稳定。
- 外部依赖：
  - 无新增强制第三方依赖。
- 潜在阻塞：
  - 外部调用方对旧返回 dict 字段存在隐式依赖。

## 11. 估时与优先级
- 优先级：P1
- 预计工期：3-5 天
- 负责人：待指派

## 12. 参考
- `src/qsim/ui/notebook.py`
- `src/qsim/ui/cli.py`
- `src/qsim/session/session.py`
- `src/qsim/ui/result_summary.py`
- `docs/src/`
- `docs/site/`
