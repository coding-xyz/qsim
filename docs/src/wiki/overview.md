# Wiki 概览

## 1. 入口

Workflow 入口统一为两种调用方式：

- Python：`qsim.workflow.run_task_files(task_config=...)`
- CLI：`qsim run-task --task-config ...`

`task` 主配置内通过 `input.solver_config` / `input.hardware_config` 引用另外两个文件；
也支持在调用时传 `solver_config`/`hardware_config` 做覆盖。

核心原则：配置职责拆分为 `task / solver / hardware` 三个文件。

## 2. Top-Down 结构

`src/qsim/workflow/` 按分层组织：

1. 应用层（入口）
- `pipeline.py`
- 负责：加载/合成配置、生成执行计划、串联主链路与分支链路

2. 编排层（计划）
- `planner.py`
- 负责：`target -> stages/artifacts` 裁剪、基础依赖校验

3. 阶段层（主链路）
- `stages.py`
- 负责：`parse/compile/lower/model -> engine -> decode -> analysis`

4. 分支层（可选能力）
- `plugins.py`
- 负责：`decoder_eval`、`pauli_plus`、`cross_engine_compare`

5. 基础设施层
- `task_io.py`：三配置加载、模板合并、target/engine 字段校验
- `persistence.py`：结构化写盘与 manifest 输出
- `output.py`：图形与文件导出辅助
- `session_adapter.py`：结果提交 session
- `engines.py`：引擎选择与跨引擎比较辅助

## 3. 主链路与分支链路

主链路（始终执行至少 parse+engine）：

1. `parse_compile_lower_model`
2. `run_engine_stage`
3. `run_decode_stage`（按 target/plan 触发）
4. `run_analysis_stage`（按 target/plan 触发）

分支链路（按 target/features 触发）：

1. `run_decoder_eval_plugin`
2. `run_pauli_plus_plugin`
3. `run_cross_engine_compare_plugin`

收口：

1. `write_artifacts`
2. `export_visualizations`
3. `build_manifest`
4. `commit_result_to_session`（可选）

## 4. 依赖约束边界

1. `target` 决定：
- 可执行阶段
- 可开启分支
- `task.features` 支持键
- `targeted` 模式下可写产物

2. `engine` 决定：
- `solver.run` 可用参数集合（例如 julia 专属键）

3. `task/solver/hardware` 职责不交叉：
- `task` 不承载 engine/hardware 细节
- `solver` 不承载具体噪声场景
- `hardware` 不承载任务目标与输出策略

## 5. 相关阅读

- [Workflow 用法（三配置 + key 支持矩阵）](./workflow_task_config.md)
- [IO 与会话](./io_session.md)
- [后端与模型](./backend_model.md)
