# [UI-P1] Workflow 目标驱动执行：依赖表 + 模板定义（已归档）

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-11

## 1. 归档说明
- 原目标：建立 `targets/template` 驱动的执行依赖规划机制。
- 归档原因：需求已上升为更高优先级的“三配置最终形态”统一重构，本 issue 的范围被新 P0 issue 完整覆盖。
- 处理方式：作为已完成归档项保留，后续不再单独推进。

## 2. 已形成的阶段性产出
- 已形成目标驱动执行与依赖裁剪的方向性方案。
- 已形成模板与目标关系的术语和边界定义。
- 已形成与写盘服务重构的依赖关系说明。

## 3. 后续承接
- 承接 issue：`issues/ISSUE_UI_P0_WORKFLOW_TASK_SOLVER_HARDWARE_SPLIT_AND_TARGET_SCHEMA.md`
- 承接内容：
  - `target -> keys` 的白名单化约束。
  - `target -> output` 的目标化输出控制。
  - 与 `solver`/`engine` 依赖规则统一治理。

## 4. 参考
- `issues/done/ISSUE_UI_P0_WORKFLOW_FINAL_SHAPE_TASK_ONLY.md`
- `issues/done/ISSUE_UI_P1_WORKFLOW_REFACTOR_TASK_DRIVEN_PIPELINE.md`
