# [UI-P0] Workflow 最终形态收敛：仅保留 Task-Driven 入口（移除 Legacy）

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-10
- 实施进展：
  - [x] API 收敛：删除 `run_workflow(...)` 与 legacy kwargs 映射，统一 `run_task(task)`。
  - [x] Contract 收敛：删除 `from_legacy_kwargs()` / `to_legacy_kwargs()`。
  - [x] CLI 收敛：移除 `run`，仅保留 `run-task --task-config`。
  - [x] 模块收敛：移除 `workflow/runner.py`，`pipeline.py` 直接以 task 为输入。
  - [x] 文档收敛：新增 task-config 用法与格式文档，更新架构与 I/O 文档。
  - [x] 验证：`pytest -q -p no:cacheprovider` 通过（65 passed）；`mkdocs build --clean` 通过。

## 1. 背景与目标
- 背景：
  - 当前仓库仍保留 `run_workflow(...)` 的长参数兼容入口，`runner/pipeline` 之间存在 legacy 映射，阅读与维护成本高。
  - 用户期望是 0.0 版本的“最终形态”，不需要历史兼容层，不需要旧参数和旧调用路径。
- 目标：
  - 对外只保留统一入口：`run_task(task)`（Python）与 `CLI + task file`（命令行）。
  - 删除所有 legacy 参数映射、旧 facade 和冗余入口，确保“接口、实现、文档”一致。
- 为什么现在做（业务 / 研究价值）：
  - 让 workflow 从“兼容导向”转为“产品导向”，降低认知负担，提升可维护性与可扩展性。

## 2. 范围
- In Scope：
  - 删除 legacy flat kwargs 入口与映射。
  - 统一为 task contract 驱动的执行 API。
  - 收敛模块职责与命名，明确主链路和分支链路边界。
  - 补齐“如何使用”的最小文档与示例。
- Out of Scope：
  - 不改底层数值算法与引擎物理语义。
  - 不新增分布式调度或远程执行能力。

## 3. 输入与输出（I/O）
- 输入：
  - `WorkflowTask`（Python 对象）或 task JSON 文件（CLI）。
- 输出：
  - 统一 `result` 字典（后续可演进为显式 `WorkflowResult`）。
  - 可选 artifacts、manifest、session commit 报告。
- 相关 schema / version（如适用）：
  - `task_schema_version: 1.0`
  - `result_schema_version: 1.0`

## 4. 技术方案
- 方案概述：
  - Public API 只保留：
    - `qsim.workflow.run_task(task: WorkflowTask) -> dict`
    - `qsim.workflow.load_task_file(path) -> WorkflowTask`
  - CLI 只保留 task-file 模式：`qsim run-task --task-config ...`。
  - 编排层只接受 `WorkflowTask`，不再接受 legacy flat 参数。
- 关键设计决策：
  - 删除 `WorkflowTask.from_legacy_kwargs()` / `to_legacy_kwargs()`（原因：避免双轨语义与参数漂移）。
  - 删除 `run_workflow(...)` legacy 入口（原因：避免“看似可用、实际不推荐”的分裂接口）。
  - 删除 `runner`，由 `pipeline.run_task` 直接承担 orchestrator 责任（原因：边界清晰，减少跳转层）。
- 可替换点 / 扩展点（接口、插件、引擎等）：
  - `stages`（主链路固定阶段）
  - `plugins`（可选分支阶段）
  - `persistence/session_adapter/engines`（基础设施适配）

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. API 收敛：
   - 删除 `run_workflow(...)` 公共入口与 legacy flat kwargs 路径。
   - 统一 `run_task(task)` 为唯一执行入口。
2. Contract 收敛：
   - 移除 `WorkflowTask` 的 legacy 映射方法。
   - task_io 仅支持 grouped schema（可保留字段校验与路径解析）。
3. CLI 收敛：
   - 移除 `run` 子命令，保留 `run-task`。
   - 保持 session 选项在 task 模式下可覆盖。
4. 模块收敛：
   - 清理/重命名让职责更直接（例如 entrypoint/orchestrator/stages）。
   - 删除仅用于兼容的 helper alias。
5. 文档收敛：
   - 新增“3 分钟使用 workflow”文档（Python + CLI 示例）。
   - 在 wiki 中明确主链路、分支链路、基础设施边界与调用图。
   - 明确 `task-config` 格式规范：
     - 必填字段、可选字段、默认值、类型约束。
     - 路径解析规则（相对路径基于 task 文件目录）。
     - `qasm_text` / `qasm_path` 使用规则与互斥关系。
     - session 相关字段（`session_dir` / `session_auto_commit` / `session_commit_kinds`）。
   - 提供两个 task-config 示例：
     - 最小可运行示例（minimal）。
     - 全功能示例（含 features/output/session）。
   - 提供“常见错误与排查”小节（字段缺失、路径错误、类型不匹配）。

## 7. 验收标准（DoD）
- [x] 仓库对外仅存在一个 workflow 执行入口：`run_task(task)`。
- [x] CLI 仅保留 task-file 模式且可完整运行。
- [x] 代码中不存在 legacy flat kwargs 映射路径。
- [x] `pipeline/stages/plugins/persistence` 职责边界在 docstring 和 docs 中清晰定义。
- [x] `docstring` 已补全或更新。
- [x] `docs/` 已补全或更新，包含 Python/CLI 基本用法。
- [x] `docs/` 已明确 `task-config` 结构（字段说明、默认值、路径规则、session 字段）。
- [x] `docs/` 提供 minimal/full 两个 task-config 样例并可直接复用。
- [x] `docs/` 提供常见错误与排查说明。
- [x] `docs/src` 与 `docs/site` 已通过构建同步且内容一致。

## 8. 测试计划
- 单元测试：
  - `WorkflowTask` grouped schema 校验与 task_io 路径解析。
  - 编排层仅接受 task contract 的约束测试。
- 集成测试：
  - `qsim run-task --task-config ...` 从输入到结果的 smoke test。
  - session auto-commit 在 task 模式下可用。
- 回归测试：
  - workflow 主链路与可选插件（decoder_eval / pauli_plus / cross-engine）输出不回归。
- 样例命令（如适用）：
  - `pytest -q -p no:cacheprovider`
  - `mkdocs build --clean`

## 9. 风险与回滚
- 主要风险：
  - 直接移除 legacy 入口会导致旧脚本立即失效。
  - 收敛过程中可能引入文档与代码短时不一致。
- 缓解策略：
  - 在 release notes 和 docs 中明确“breaking change”。
  - 提供 task JSON 迁移示例与参数映射表。
- 回滚策略：
  - 若主链路回归，回退至本 issue 起始 commit，并保留 task-only 分支继续修复。

## 10. 依赖与阻塞
- 前置依赖：
  - `workflow` 当前主链路测试稳定。
- 外部依赖（库 / 环境 / 数据）：
  - 无新增强制依赖。
- 潜在阻塞：
  - 历史 notebook 可能仍使用旧调用方式，按 0.0 版本策略统一视为 breaking change，不再保留兼容入口。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：2-3 天
- 负责人：待指派

## 12. 参考
- 相关文件：
  - `src/qsim/workflow/contracts.py`
  - `src/qsim/workflow/pipeline.py`
  - `src/qsim/workflow/stages.py`
  - `src/qsim/workflow/task_io.py`
  - `src/qsim/ui/cli.py`
  - `src/qsim/ui/notebook.py`
- 相关 issue / PR：
  - `issues/done/ISSUE_UI_P1_WORKFLOW_REFACTOR_TASK_DRIVEN_PIPELINE.md`
- 相关文档：
  - `docs/src/wiki/overview.md`
  - `docs/src/wiki/io_session.md`
