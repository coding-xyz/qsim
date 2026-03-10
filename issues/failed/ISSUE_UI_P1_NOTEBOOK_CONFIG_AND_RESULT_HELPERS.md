## Archive Status
- Final status: Failed
- Archived at: 2026-03-10
- Reason: Results are incorrect; request switched to manual code audit.

# [UI] Notebook 配置驱动与结果整理收口

## 0. 状态
- 状态：Failed
- 负责人：
- 更新时间：2026-03-04

## 1. 背景与目标
- 背景：
  当前 `examples/noise_simulation_tests/required_tasks_tri_engine.ipynb` 已初步改成配置驱动，但仍存在几个问题：
  1. notebook 启动段包含偏重路径探测的样板代码，可继续收敛。
  2. 任务配置仍是单文件聚合，不符合“一个任务一个配置文件，QASM 直接写入配置”的目标。
  3. `pulse_metrics`、`summarize_result` 一类结果整理逻辑仍停留在 notebook 层，没有进入 `src` 的可复用接口。
  4. notebook 中文内容存在编码损坏，需要重新以 UTF-8 正确落盘。
- 目标：
  - 将 tri-engine notebook 改为按目录加载“每任务一个配置文件”。
  - 将结果整理 helper 收口到 `src/qsim/ui/`，供 notebook 直接调用。
  - 清理 notebook 中不必要的路径样板，并修复 UTF-8 中文内容。
- 为什么现在要做（业务 / 研究价值）：
  - 验证“任务配置文件 + 直接调用 workflow”的工作范式是否能作为后续 notebook 的标准模式。
  - 降低 notebook 层重复逻辑，避免结果表构造在不同 notebook 中继续散落。

## 2. 范围
- In Scope：
  - `examples/noise_simulation_tests/required_tasks_tri_engine.ipynb`
  - tri-engine 任务配置目录与配置文件
  - `src/qsim/ui/` 下结果整理 helper
  - README 中相关说明
- Out of Scope：
  - 新增通用批量 workflow runner
  - 修改 un_workflow` 主执行语义
  - 改造 roadmap 目录下其他 notebook

## 3. 输入与输出（I/O）
- 输入：
  - 每任务一个 JSON 配置文件，内含任务元数据、QASM、case、引擎与展示指标。
- 输出：
  - notebook 基于配置执行并生成原有 summary CSV。
  - `src/qsim/ui/` 暴露可复用结果整理 helper。
- 相关 schema / version（如适用）：
  - task workflow config schema `1.0`

## 4. 技术方案
- 方案概述：
  - 在 `examples/noise_simulation_tests/required_tasks_tri_engine/` 下按任务拆分 JSON。
  - notebook 只负责加载配置目录、调用 un_workflow`、展示结果。
  - 将 pulse 指标提取、结果行汇总、比较状态标注上收至 `src/qsim/ui/`。
- 关键设计决策：
  - 不引入新的 workflow 批执行入口，继续复用现有 un_workflow`。
  - task config 直接内嵌 QASM，避免 notebook 保留第二份线路定义。
  - notebook 保留展示逻辑，结果整理与表结构构造进入 `src`。
- 可替换点 / 扩展点（接口、插件、引擎等）：
  - 后续可在 `src/ui` 增加更通用的 workflow batch helper，而不影响本次 task-config 目录结构。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 同步检查并补全相关 `docstring`。
3. 同步更新 `docs/` 下对应文档内容。
4. 若 `docs/site/` 为构建产物，则优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 提交前确认 issue 中的“文档更新”和“docstring 更新”条目已勾选。

## 6. 任务拆分
1. 建立 task-config 目录并拆分 tri-engine 配置文件。
2. 在 `src/qsim/ui/` 中实现结果整理 helper。
3. 重写 notebook 以加载配置目录并修复 UTF-8 文本。

## 7. 验收标准（DoD）
- [ ] tri-engine notebook 不再内置 QASM 常量和单文件 tasks 配置
- [ ] 每任务一个配置文件并可直接驱动 un_workflow`
- [ ] 结果整理 helper 从 notebook 上收至 `src/qsim/ui/`
- [ ] 产物落盘（如 manifest / report / trace）
- [ ] 相关 `docstring` 已新增或更新
- [ ] `docs/` 下对应文档已新增或更新

## 8. 测试计划
- 单元测试：如有必要，为结果整理 helper 增加最小测试。
- 集成测试：最小 smoke run 验证配置文件 -> notebook 参数 -> un_workflow`。
- 回归测试：编译 notebook code cells，确认 UTF-8 文本正确。
- 样例数据 / 命令：
  - `python` smoke 脚本直接从 task-config 读取首个任务调用 un_workflow`

## 9. 风险与回滚
- 主要风险：
  - notebook JSON 手工重写时引入编码或语法问题。
  - helper 上收后字段名变化影响现有展示列。
- 监控 / 告警点：
  - summary CSV 字段是否保持可读且与现有 notebook 兼容。
- 回滚策略：
  - 回退到此前 notebook-only helper 版本。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 un_workflow` 保持参数接口稳定。
- 外部依赖（库 / 环境 / 数据）：
  - 本地 Python / notebook 执行环境。
- 潜在阻塞：
  - Windows 控制台编码与 notebook UTF-8 生成脚本可能冲突。

## 11. 估时与优先级
- 优先级：P1
- 预计工期：0.5d
- 负责人：

## 12. 参考
- 相关文件：
  - `examples/noise_simulation_tests/required_tasks_tri_engine.ipynb`
  - `src/qsim/ui/notebook.py`
  - `examples/noise_simulation_tests/README.md`
- 相关 issue / PR：
  - 无
- 相关文档：
  - equired_tasks.txt`



