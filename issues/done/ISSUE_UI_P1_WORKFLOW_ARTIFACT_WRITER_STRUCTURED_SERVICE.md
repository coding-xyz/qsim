# [UI-P1] Workflow 写盘服务重构：从超长参数协议到结构化 Payload（已归档）

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-11

## 1. 归档说明
- 原目标：将 `write_artifacts(...)` 从超长调用协议重构为结构化写盘服务。
- 归档原因：需求已统一到更高优先级的“三配置 + 目标化输出”最终形态，写盘策略将随新 P0 issue 一并收敛。
- 处理方式：作为已完成归档项保留，后续不再单独推进。

## 2. 已形成的阶段性产出
- 明确了写盘层应使用结构化 payload，而不是长参数函数签名。
- 明确了写盘策略与执行计划（target-driven）的耦合边界。
- 明确了 `outputs map` 作为统一产物索引真源的方向。

## 3. 后续承接
- 承接 issue：`issues/ISSUE_UI_P0_WORKFLOW_TASK_SOLVER_HARDWARE_SPLIT_AND_TARGET_SCHEMA.md`
- 承接内容：
  - 输出项与 target 绑定，按目标写盘。
  - 写盘服务面向结构体输入，避免冗余 dict 协议。
  - 与 task/solver/hardware 三配置联动校验。

## 4. 参考
- `issues/done/ISSUE_UI_P0_WORKFLOW_FINAL_SHAPE_TASK_ONLY.md`
- `issues/done/ISSUE_UI_P1_WORKFLOW_REFACTOR_TASK_DRIVEN_PIPELINE.md`
