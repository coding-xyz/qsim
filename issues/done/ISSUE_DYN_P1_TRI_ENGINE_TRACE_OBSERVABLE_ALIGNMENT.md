# [DYN-P1] 统一三引擎 trace / observables 语义，避免 Julia 结果被误解释为多比特观测量
## 0. 状态
- 状态：Done
- 负责人：Codex
- 更新时间：2026-03-04

## 1. 背景与目标
- 背景：
  - equired_tasks.txt` 要求同一批动力学任务在 `qutip`、`quantumtoolbox.jl`、`quantumoptics.jl` 三个 backend 上做横向对比。
  - 2026-03-03 的本地探针显示，三引擎虽然都能真实运行，但 `trace.states` 的行语义并未对齐：
    - `qutip` 单比特常返回长度为 1 的激发概率向量，例如 `[p1]`。
    - `qutip` 两比特常返回长度为 2 的逐比特激发概率，例如 `[p1(q0), p1(q1)]`。
    - `julia_qtoolbox` / `julia_qoptics` 在单比特场景返回长度为 2 的态分布向量，且两个 Julia backend 的基态/激发态顺序不一致。
  - 当前 [observables.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/analysis/observables.py) 把 `len(final) > 1` 直接解释成“多比特逐比特终态”，会让单比特 Julia 结果错误地产生 `final_q1_excited` 等字段。
- 目标：
  - 定义统一的 trace 行语义契约。
  - 在进入 `observables`、`cross_engine_compare`、notebook 横向分析之前完成引擎输出归一化。
  - 明确 basis population、per-qubit excited probability、statevector surrogate 这几类表示的边界，避免混用。

## 2. 范围
- In Scope：
  - 明确三引擎 `Trace.states` 的 canonical schema。
  - 在引擎适配层或分析入口增加归一化步骤。
  - 修正 `observables` 对 Julia 结果的误解释。
  - 修正跨引擎对比产物对 state dimension / state meaning 的假设。
- Out of Scope：
  - 新物理模型开发。
  - Julia runtime 或包安装流程优化。

## 3. 输入与输出（I/O）
- 输入：
  - `Trace` 对象，来自 `qutip`、`julia_qtoolbox`、`julia_qoptics`。
  - 典型场景：1Q 基准、2Q Bell、含 Lindblad / 1/f / OU 噪声的动力学流程。
- 输出：
  - 对齐后的 `Trace.states` 语义说明。
  - 修正后的 `observables.json`、`cross_engine_compare.json`、notebook 汇总表。
  - 必要时补充 `trace.metadata.state_encoding` 或等价字段。

## 4. 技术方案
- 方案概述：
  - 引入独立的 trace 语义辅助模块，对 trace 补充显式 `state_encoding`。
  - 对 `observables` 仅在语义明确时生成对应指标。
  - 对 `cross_engine_compare` 仅在语义同构时输出逐项误差。
- 关键设计决策：
  - 不对多比特 Julia 输出做无依据强行投影；遇到无法安全解释的情况，标记为 `ambiguous_population_vector`。
  - `cross_engine_compare` 用显式 `comparable: false` + eason` 代替静默错误比较。
- 可替换点 / 扩展点：
  - 后续如要做更强 canonicalization，可在 `trace_semantics.py` 上继续扩展。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 同步检查并补全相关 `docstring`。
3. 同步更新 `docs/` 下对应文档内容。
4. 若 `docs/site/` 为构建产物，则优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 提交前确认 issue 中的“文档更新”和“docstring 更新”条目已勾选。

## 6. 任务拆分
1. 复现实测差异，列出 1Q / 2Q / 噪声场景下三引擎输出的 shape 与语义。
2. 设计 canonical trace 表示和 metadata 字段。
3. 修正 `observables` 计算逻辑。
4. 修正 `cross_engine_compare` 的配对误差逻辑。
5. 增加 notebook / 集成测试覆盖，确保三引擎横向表格不再误导。

## 7. 验收标准（DoD）
- [x] 单比特 Julia 结果不再出现伪造的 `final_q1_excited`
- [x] 两比特与单比特场景都能明确区分“逐比特概率”与“basis population”
- [x] `cross_engine_compare.json` 只在表示同构时输出逐项误差
- [x] notebook 横向对比表能给出一致、可解释的指标
- [x] 相关 `docstring` 已新增或更新
- [x] `docs/` 下对应文档已新增或更新

## 8. 测试计划
- 单元测试：
  - `observables` 对不同 state encoding 的分支处理。
  - canonicalization helper 对 1Q / 2Q 输入的转换。
- 集成测试：
  - un_workflow(..., engine=...)` 在三引擎下产出的 summary 字段对齐。
  - `cross_engine_compare.json` 在语义不一致时给出明确提示而非静默比较。
- 回归测试：
  - 现有 QuTiP 工作流与 QEC 流程不回退。

## 9. 风险与回滚
- 主要风险：
  - 现有 notebook 或下游报表依赖旧的、隐含的 state shape 假设。
- 监控 / 告警点：
  - `observables.json` 字段数量突变。
  - `cross_engine_compare` 基线误差异常降低或升高。
- 回滚策略：
  - 保留旧字段但显式标记 deprecated，逐步迁移 notebook 与报表。

## 10. 依赖与阻塞
- 前置依赖：
  - 三引擎最小样例可稳定复现当前差异。
- 外部依赖（库 / 环境 / 数据）：
  - 本地 Julia runtime、QuantumToolbox.jl、QuantumOptics.jl。
- 潜在阻塞：
  - 不同引擎天然输出对象不同，无法一刀切地压成同一种数组而不损失语义。

## 11. 估时与优先级
- 优先级：P1
- 实际工期：1 天
- 负责人：Codex

## 12. 验收记录
- 代码：
  - 新增 [trace_semantics.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/analysis/trace_semantics.py)
  - 更新 [observables.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/analysis/observables.py)
  - 更新 [notebook.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/notebook.py)
- 测试：
  - 新增 [test_trace_semantics.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_trace_semantics.py)
  - 更新 [test_workflow_dynamics.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_workflow_dynamics.py)
  - 运行：`pytest -q -p no:cacheprovider tests/test_trace_semantics.py tests/test_workflow_dynamics.py`
  - 结果：`11 passed`
- 文档：
  - 更新 [io_session.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/io_session.md)
  - 更新 [noise_engine.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/noise_engine.md)
  - 更新 [examples/noise_simulation_tests/README.md](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/README.md)
- 产物：
  - notebook 已重跑：[required_tasks_tri_engine.ipynb](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/required_tasks_tri_engine.ipynb)
  - 新汇总：[all_tasks_summary.csv](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/runs/required_tasks_tri_engine/_summaries/all_tasks_summary.csv)

## 13. 参考
- [src/qsim/analysis/observables.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/analysis/observables.py)
- [src/qsim/ui/notebook.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/notebook.py)
- [src/qsim/engines/julia_qtoolbox.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/julia_qtoolbox.py)
- [src/qsim/engines/julia_qoptics.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/julia_qoptics.py)
- [required_tasks.txt](/d:/超导量子计算机噪声抑制/qsim/required_tasks.txt)

