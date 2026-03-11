# [UI-P0] Workflow 最终形态：Task/Solver/Hardware 三配置 + Target/Engine 依赖约束

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-11

## 1. 背景与目标
- 背景：
  - 当前 task-config 在 `input/run/feature/output` 中仍混入大量全量 keys，未做到按 target 收敛。
  - `run` 中部分参数实际上依赖 engine 选择，但缺少显式依赖约束与校验。
  - `output` 目前不是严格 target-driven，容易产生与当前任务无关的冗余输出。
  - `examples/backend.yaml` 与 workflow config 职责重叠，模型边界不清晰。
- 目标：
  - 将配置拆分为三类：`task`、`solver`、`hardware`。
  - 以 `target` 驱动可用 keys 与输出产物，禁止无关字段进入当前任务。
  - 以 `engine` 驱动 solver 参数约束，建立清晰依赖与验证规则。
  - 提供内置 solver/hardware 模板，覆盖常用场景并可调参。
  - 文档明确“每个 target 支持哪些 keys、每个 engine 支持哪些 solver 参数、每个 target 产出哪些 output”。

## 2. 范围
- In Scope：
  - 新增三配置契约与加载入口：`task.yaml`、`solver.yaml`、`hardware.yaml`。
  - 建立 `target -> supported keys` 白名单约束（至少覆盖 `input/output/features`）。
  - 建立 `engine -> solver keys` 依赖约束与校验报错。
  - 建立 `target -> output artifacts` 产物映射并接入写盘策略。
  - 在 `src` 下提供一组固定模板：solver 模板与 hardware/noise 模板。
  - 给出 `backend.yaml` 的替代与迁移路径（最终可完全替代）。
  - docs/wiki 完整更新：结构说明 + 用法 + schema + keys 矩阵 + 示例。
- Out of Scope：
  - 不更改底层物理算法正确性与数值实现。
  - 不新增分布式调度能力。

## 3. 输入与输出（I/O）
- 输入：
  - `task.yaml`
    - 必含：`target`、`input`、`output`
    - 可含：任务元信息（例如 `name`、`description`）
  - `solver.yaml`
    - 必含：`engine`
    - 可含：算法与求解参数（受 engine 约束）
  - `hardware.yaml`
    - 必含：硬件/噪声模型基础字段
    - 可含：可调参数
- 输出：
  - 运行结果（结构化 result）。
  - 目标化 artifacts（仅写当前 target 对应产物）。
  - 运行 manifest（记录 target/engine/模板来源与实际启用 keys）。
- 相关 schema/version：
  - `task_schema_version: 2.0`
  - `solver_schema_version: 1.0`
  - `hardware_schema_version: 1.0`

## 4. 技术方案
- 顶层入口保持两种：
  - Python：`run_task(task_config, solver_config, hardware_config)`
  - CLI：`qsim run-task --task-config ... --solver-config ... --hardware-config ...`
- 设计要点：
  - `task` 只表达“做什么”和“要什么输出”。
  - `solver` 只表达“怎么解”（与 engine 绑定）。
  - `hardware` 只表达“在什么硬件/噪声条件下解”。
  - planner 先做依赖裁剪：`target -> stages/keys/output`。
  - 校验层分两步：
    - `target` 白名单校验（task 维度）
    - `engine` 参数校验（solver 维度）
  - 写盘层按 target 产物映射输出，不再全量输出。
- 模板策略：
  - 在 `src/qsim/workflow/templates/solvers/` 提供常用 solver 模板。
  - 在 `src/qsim/workflow/templates/hardware/` 提供常用 hardware/noise 模板。
  - 支持“模板 + 局部覆写”模式。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 契约重构：定义三配置 schema 与加载逻辑。
2. 依赖系统：实现 `target -> keys/output/stages` 规则表。
3. 引擎依赖：实现 `engine -> solver keys` 规则表。
4. 运行编排：将 planner、validator、writer 串成主链路。
5. 模板仓：新增 solver/hardware 固定模板与覆盖机制。
6. 迁移与兼容：给出 `backend.yaml` 替代方案和迁移说明。
7. 文档与示例：补齐用法、schema、支持矩阵、常见错误排查。

## 7. 验收标准（DoD）
- [x] 运行入口支持三配置输入并能完整执行。
- [x] 未被当前 `target` 支持的 keys 会被明确拒绝（带可读报错）。
- [x] 未被当前 `engine` 支持的 solver 参数会被明确拒绝（带可读报错）。
- [x] 输出严格按 target 控制，不再产生无关产物。
- [x] `src` 下提供可复用 solver/hardware 模板。
- [x] `backend.yaml` 功能可由三配置完全替代，并有迁移文档。
- [x] docs 明确列出：
  - 每个 target 支持的 keys
  - 每个 engine 支持的 solver keys
  - 每个 target 对应的 output 产物
- [x] `docstring` 与 `docs/src`/`docs/site` 同步更新完成。

## 7.1 验收记录（2026-03-11）
- 配置形态：
  - task 主文件包含 `input.solver_config` / `input.hardware_config` 引用。
  - solver key 集合收敛为：
    - `backend: level / analysis_pipeline / truncation`
    - `run: engine / solver_mode / sweep / seed / dt / schedule_policy / reset_feedback_policy`（以及可选运行扩展键）
  - `output.out_dir` 作为唯一输出目录入口。
  - `decoder` 仅在 QEC 相关 target 强制要求；动力学 `trace` 不强制。
- 验证命令：
  - `pytest -q tests/test_workflow_task_io.py tests/test_workflow_planner.py tests/test_workflow_targets.py -p no:cacheprovider`
  - `pytest -q tests/test_qec_workflow.py tests/test_workflow_dynamics.py tests/test_workflow_session.py -p no:cacheprovider`
  - `mkdocs build --clean`
- 验证结果：
  - 全部通过（测试通过 + 文档构建通过）。

## 8. 测试计划
- 单元测试：
  - target 白名单校验。
  - engine 参数依赖校验。
  - target 输出映射与写盘裁剪。
- 集成测试：
  - Python/CLI 三配置端到端运行。
  - 模板加载 + 参数覆写。
- 回归测试：
  - 现有核心任务主链路不回归。
- 样例命令：
  - `pytest -q -p no:cacheprovider`

## 9. 风险与回滚
- 主要风险：
  - 配置拆分后短期迁移成本增加。
  - target/engine 规则定义不全导致误拒绝。
- 缓解策略：
  - 增加规则覆盖测试与错误信息指引。
  - 提供最小可运行模板与迁移对照表。
- 回滚策略：
  - 若出现阻塞回归，先回退到“规则仅告警、不阻断”模式，再逐步收紧。

## 10. 依赖与阻塞
- 前置依赖：
  - workflow 主链路（pipeline/stages/persistence）可持续演进。
- 外部依赖：
  - 无新增强制第三方依赖。
- 潜在阻塞：
  - 历史文档与示例未同步，导致用户对新模型理解偏差。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：4-7 天
- 负责人：待指派

## 12. 参考
- `issues/ISSUE_TEMPLATE.md`
- `issues/done/ISSUE_UI_P0_WORKFLOW_FINAL_SHAPE_TASK_ONLY.md`
- `issues/done/ISSUE_UI_P1_WORKFLOW_REFACTOR_TASK_DRIVEN_PIPELINE.md`
- `issues/done/ISSUE_UI_P1_WORKFLOW_TARGET_DEPENDENCY_TEMPLATE_PLAN.md`
- `issues/done/ISSUE_UI_P1_WORKFLOW_ARTIFACT_WRITER_STRUCTURED_SERVICE.md`
