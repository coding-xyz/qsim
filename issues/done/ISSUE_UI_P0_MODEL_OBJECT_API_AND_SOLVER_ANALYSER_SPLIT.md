# [UI-P0] Top-Down Model Object API 与 Solver/Analyser 硬拆分

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-30

## 1. 背景与目标
- 背景：
  - 当前顶层执行入口是 `run_task(...) / run_task_files(...)`，主交互范式仍是“传入配置文件并返回结果字典”。
  - 这种 function-first 入口不适合 notebook 中的交互式建模、调参、重复运行和对象级持久化。
  - 当前 `solver` 与 `analysis` 仍然耦合，`solver.yaml` 中承载了分析配置，职责边界不清晰。
  - 当前 `results.trace`、`results.metrics`、`results.iq`、`results.readout`、`results.report` 共存于同一工作流输出中，但从架构上看，只有 raw solver 演化数据应属于 solver，其他都应属于 analyser。
- 目标：
  - 将顶层主入口重构为 `create_model(...) -> model`。
  - 允许通过 `model.task / model.circuit / model.device / model.pulse / model.solver / model.analyser` 直接查看和修改对象状态。
  - 用 `model.run()` 作为唯一正式执行入口。
  - 明确 `solver` 只产出 raw `trajectory`，所有衍生变量统一交由 `analyser` 计算。
  - 支持 `model.save(...)` / `load_model(...)`，实现模型对象的完整持久化与恢复。
- 为什么现在做（业务 / 研究价值）：
  - 为 notebook 驱动的参数扫描、交互式实验和中间态检查提供更自然的工作流。
  - 为后续模型缓存、增量重跑、对象级编辑和结果复用打下统一抽象。
  - 通过硬拆分 `solver` / `analyser`，使数值求解与后处理边界稳定，降低继续演化时的耦合成本。

## 2. 范围
- In Scope：
  - 新增 `create_model(...)`、`Model.run()`、`Model.save(...)`、`load_model(...)`。
  - 将当前 4 配置输入扩展为 5 配置输入：`task`、`solver`、`device`、`pulse`、`analyser`。
  - 将 `model.circuit` 作为顶层一等对象暴露给用户，供 notebook 中直接查看。
  - 重构 workflow 主链路，使中间产物沉淀到 `Model` 对象，而不是只存在于临时字典。
  - 将 `solver` 输出语义收敛为 raw `trajectory`，并将 population / iq / readout / report / sensitivity / error_budget 等统一归入 analyser。
  - 在代码、测试、文档、产物命名中统一将 `Trace` / `trace` / `trace.h5` / `plot_trace(...)` 等命名重构为 `Trajectory` / `trajectory` / `trajectory.h5` / `plot_trajectory(...)`，不保留双命名并存。
  - 重写顶层 API、docs、examples、notebook helper 与测试，使其围绕新的 model-first 入口组织。
- Out of Scope：
  - 不改变底层物理模型正确性与引擎数值算法本身。
  - 不新增分布式调度或远程执行能力。
  - 不保留任何旧 API、旧配置结构、旧 bundle 形态的兼容层。

## 3. 输入与输出（I/O）
- 输入：
  - `create_model(...)` 接收 5 个配置源：
    - `task_config`
    - `solver_config`
    - `device_config`
    - `pulse_config`
    - `analyser_config`
  - 对象创建后，可直接修改：
    - `model.task...`
    - `model.device...`
    - `model.pulse...`
    - `model.solver...`
    - `model.analyser...`
- 输出：
  - `Model` 对象，至少包含：
    - `model.task`
    - `model.circuit`
    - `model.device`
    - `model.pulse`
    - `model.solver`
    - `model.analyser`
    - `model.trajectory`
    - `model.analysis`
  - `model.run()` 执行后：
    - `model.trajectory` 保存 solver 原始输出
    - `model.analysis` 保存 analyser 派生输出
- 相关 schema / version（如适用）：
  - `model_schema_version: 1.0`
  - `solver_schema_version: 2.0`
  - `analyser_schema_version: 1.0`
  - `trajectory_schema_version: 2.0`

## 4. 技术方案
- 方案概述：
  - 引入 `Model` 作为新的 canonical runtime object。
  - `create_model(...)` 负责加载 5 个配置、构建对象图、生成可执行模型所需的中间对象，并把这些对象挂载到 `Model` 上。
  - `Model.run()` 负责串联：
    - build/compile/lower
    - solver run
    - analyser run
  - `solver` 只负责数值求解与 trajectory 生成。
  - `analyser` 只负责消费 `trajectory` 并生成派生分析结果。
  - `Model.save(...)` 负责保存配置快照、中间模型、trajectory、analysis 和 runtime metadata。
- 关键设计决策：
  - 决策 1：不提供 `children` 统一视图，直接暴露结构化属性。
    - 原因：`model.device.xxx`、`model.solver.xxx` 这样的访问方式更自然，也更利于静态结构和 notebook 使用。
  - 决策 2：`create_model(...)` 与 `Model.run()` 成为唯一正式入口。
    - 原因：避免 function-first 与 object-first 双轨并存造成语义分裂。
  - 决策 3：`solver` 与 `analyser` 硬拆分，不保留 `solver.analysis`。
    - 原因：保证 solver 产物的 raw trajectory 语义稳定，避免后处理逻辑再次回流到 solver。
  - 决策 4：不保留旧版本兼容。
    - 原因：这是一次明确的架构切换，继续兼容只会引入额外桥接层和长期维护负担。
  - 决策 5：`trajectory` 替代 `trace` 作为统一命名，且为强制重命名，不保留旧别名。
    - 原因：避免与 matrix trace / partial trace 混淆，并让“时序原始演化记录”的语义更直接。
- 可替换点 / 扩展点（接口、插件、引擎等）：
  - `Model.run_solver()` 与 `Model.run_analyser()` 可作为内部或半公开扩展点。
  - `analyser` 可继续挂接多种分析 pass，但必须统一从 `trajectory` 出发。
  - 引擎选择仍由 `model.solver` 管理，但必须只返回原始 trajectory 数据。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 顶层对象重构：
   - 定义 `Model`、`AnalysisResult` 及相关配置对象。
   - 建立 `create_model(...)`、`load_model(...)` 和 `Model.save(...)`。
2. 配置体系重构：
   - 将现有 4 配置 bundle 改为 5 配置 bundle。
   - 新增 `analyser` 契约与 loader。
   - 删除 `solver.analysis` 的旧结构。
3. pipeline 重构：
   - 将现有 `_run_core_stages(...)` 的中间产物沉淀到 `Model`。
   - 拆出明确的 build / solver / analyser 三阶段对象方法。
4. trajectory 语义重构：
   - 明确 `trajectory` 是 raw-only 数据容器。
   - 清理 population / iq / readout / report 等非 raw 数据在 trajectory/result 中的归属。
   - 全代码库将 `Trace` / `trace` 相关公开命名统一重构为 `Trajectory` / `trajectory`。
5. analyser 重构：
   - 将 population / variance / mean_excited / iq / readout / report / sensitivity / error_budget 全部统一为 analyser 产物，并统一从 `trajectory` 计算。
6. 入口清理：
   - 删除 `run_task(...)`、`run_task_files(...)` 及其相关旧式入口与辅助包装。
   - 清理 CLI / notebook / examples 中所有旧调用方式。
7. 文档与示例：
   - 新增 model-first 用法文档。
   - 更新 examples 和 notebook helper，展示 `create_model(...)`、对象修改、`model.run()`、`model.save(...)`。

## 7. 验收标准（DoD）
- [x] 仓库存在新的顶层入口：`create_model(...)`。
- [x] 存在 `Model` 对象，且它是唯一正式执行载体。
- [x] `Model` 至少暴露：`task`、`circuit`、`device`、`pulse`、`solver`、`analyser`、`trajectory`、`analysis`。
- [x] notebook 中可直接通过 `model.device...`、`model.solver...`、`model.analyser...` 修改参数后重新运行。
- [x] `model.run()` 能完整执行 build + solver + analyser 主链路。
- [x] `model.trajectory` 仅包含 raw trajectory 数据，不再包含 population / iq / report 等衍生结果。
- [x] population / variance / mean_excited / iq / readout / report / sensitivity / error_budget 全部由 analyser 生成。
- [x] 代码与公开接口中不再保留 `Trace` / `trace` 命名，统一切换为 `Trajectory` / `trajectory`。
- [x] 配置输入已切换为 5 配置结构，不保留旧 4 配置 bundle。
- [x] 旧 `run_task(...)` / `run_task_files(...)` 入口已移除。
- [x] `solver.yaml` 不再出现 `analysis` 配置。
- [x] 新增 `analyser.yaml` 并被主链路实际消费。
- [x] 支持 `model.save(...)` 与 `load_model(...)`。
- [x] `docstring` 已补全或更新。
- [x] `docs/` 已补全或更新。
- [x] `docs/src` 与 `docs/site` 已通过构建同步且内容一致。

## 8. 测试计划
- 单元测试：
  - `Model` 创建、保存、加载。
  - `solver` 与 `analyser` 配置 loader 与 schema 校验。
  - `trajectory` raw-only 语义校验。
  - analyser 各派生产物仅从 `trajectory` 计算，不依赖 solver 侧分析字段。
- 集成测试：
  - `create_model(...) -> model.run()` 端到端执行。
  - notebook 风格对象修改后重跑。
  - `model.save(...) -> load_model(...) -> rerun` 端到端执行。
- 回归测试：
  - 当前 task2 / readout / spam 相关主链路在新 model-first 架构下可运行。
  - 现有三引擎 trajectory 产物语义不回退为“夹带分析结果”的旧模式。
- 样例命令（如适用）：
  - `pytest -q -p no:cacheprovider`
  - `mkdocs build --clean`

## 9. 风险与回滚
- 主要风险：
  - 这是一项 breaking refactor，所有旧脚本、notebook、示例和文档都会立即失效。
  - `trajectory` raw-only 改造可能牵连现有 artifact writer、report builder 和 notebook helper。
  - `solver` / `analyser` 拆分不彻底时，容易出现配置遗漏或结果归属混乱。
  - 全量 `trace -> trajectory` 重命名会影响文件名、测试名、图形函数名和 schema 名称，改动面很大。
- 缓解策略：
  - 先定义清晰的对象契约与 trajectory schema，再进行实现搬迁。
  - 通过端到端测试覆盖 task2/readout 类场景，确保 analyser 真正消费的是 `trajectory`。
  - 对 docs、examples、tests 同步改造，不保留模糊入口。
- 回滚策略：
  - 若重构阶段出现阻塞回归，直接回退整个 model-first 分支，不引入半兼容状态到主干。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 workflow contracts / pipeline / stages 允许继续演进。
  - 当前 trajectory schema 与 analysis 产物分布已基本可定位。
- 外部依赖（库 / 环境 / 数据）：
  - 无新增强制第三方依赖。
- 潜在阻塞：
  - 现有示例与 notebook 大量使用 `run_task(...)` 思维，需要同步重写。
  - 现有 artifact/result schema 可能默认假设“run 完即有 metrics/readout/report”，需要重新梳理归属。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：5-8 天
- 负责人：待指派

## 12. 参考
- `issues/ISSUE_TEMPLATE.md`
- `issues/done/ISSUE_UI_P0_WORKFLOW_FINAL_SHAPE_TASK_ONLY.md`
- `issues/done/ISSUE_UI_P0_WORKFLOW_TASK_SOLVER_HARDWARE_SPLIT_AND_TARGET_SCHEMA.md`
- `src/qsim/workflow/contracts.py`
- `src/qsim/workflow/task_io.py`
- `src/qsim/workflow/pipeline.py`
- `src/qsim/workflow/stages.py`
- `src/qsim/ui/notebook.py`
