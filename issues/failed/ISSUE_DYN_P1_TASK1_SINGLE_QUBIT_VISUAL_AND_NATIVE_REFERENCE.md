## Archive Status
- Final status: Failed
- Archived at: 2026-03-10
- Reason: Results are incorrect; request switched to manual code audit.

# [DYN-P1] Task1 单比特：补齐可视化结果与原生引擎对照代码
## 0. 状态
- 状态：Failed
- 负责人：Codex
- 更新时间：2026-03-09

## 1. 背景与目标
- 背景：
- `examples/noise_simulation_tests/required_tasks_tri_engine.ipynb` 在 Task1（`task1_single_qubit_baseline`）执行后没有产出可用可视化，日志出现 “skipped plot because no case is pointwise-comparable across engines”。
- 现有结果表中 Task1 三引擎状态编码混合（`basis_population_single_qubit` 与 `per_qubit_excited_probability`），导致当前绘图条件过严，用户看不到对比图。
- 目前缺少“可直接复制运行”的原生引擎参考代码，无法快速核对 `QuantumOptics.jl` / `QuTiP` 是否被正确调用。
- 目标：
- 为 Task1 产出可读的观测量动力学曲线（至少包含激发态概率随时间变化）。
- 明确给出 Task1 的原生 `QuantumOptics.jl`、`QuTiP` 对照代码，并与当前工作流参数保持一致。
- 输出可以直接用于“我的 engine 是否被正确调用”的人工核验。

## 2. 范围
- In Scope：
- Task1（单比特）在三引擎下的观测量可视化补齐。
- Task1 对应的原生 `QuantumOptics.jl`、`QuTiP` 参考脚本或代码块。
- 对比口径文档化：哪些指标可跨编码比较，哪些不应直接逐项比较。
- Out of Scope：
- Task2~Task7 的统一改造。
- 新物理模型与新噪声模型扩展。

## 3. 输入与输出（I/O）
- 输入：
- `examples/noise_simulation_tests/required_tasks_tri_engine/task1_single_qubit_baseline.json`
- Task1 各引擎运行产物（`trace.h5` / `observables.json` / summary CSV）
- 当前 tri-engine notebook 展示逻辑
- 输出：
- Task1 的观测量图（至少 `p1(t)` 动力学曲线，按 case 和 engine 区分）
- Task1 的原生 `QuantumOptics.jl` 与 `QuTiP` 对照代码（可直接运行或最小改动运行）
- 一份 Task1 对照结论表（final_p1、mean_excited、关键差异说明）
- 相关 schema / version（如适用）：
- 复用现有 `trace` / `observables` / summary schema，不新增 schema

## 4. 技术方案
- 方案概述：
- 在 Task1 维度增加“语义可比观测量”的绘图通道，不再仅依赖 `pointwise-comparable`。
- 动力学曲线统一映射到 `p1(t)`：对 `basis_population_single_qubit` 取 `state[1]`，对 `per_qubit_excited_probability` 取 `state[0]`。
- 提供与当前引擎调用路径一致的原生代码片段，包含哈密顿量、塌缩算符、求解器调用与观测量提取。
- 关键设计决策：
- 保留现有严格的 `pointwise-comparable` 判定用于“状态向量逐点比较”。
- 新增“观测量语义比较”仅用于 Task1 可视化，不混淆为状态编码完全一致。
- 原生对照代码明确标注“用于调用核验与趋势比对”，不宣称与全工作流逐样本严格一致。
- 可替换点 / 扩展点（接口、插件、引擎等）：
- 后续可扩展到 Task2~Task7，形成统一的“metric-level comparable”绘图层。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 同步检查并补全相关 `docstring`。
3. 同步更新 `docs/` 下对应文档内容。
4. 若 `docs/site/` 为构建产物，则优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 提交前确认 issue 中的“文档更新”和“docstring 更新”条目已勾选。

## 6. 任务拆分
1. 复现 Task1 当前“无图”现象并固化最小复现步骤。
2. 定义 Task1 的 `p1(t)` 语义映射并实现可视化输出。
3. 补充原生 `QuantumOptics.jl` 对照代码。
4. 补充原生 `QuTiP` 对照代码。
5. 产出 Task1 三引擎对照表与差异说明。
6. 更新 `examples/noise_simulation_tests/README.md` 里的 Task1 使用说明。

## 7. 验收标准（DoD）
- [x] Task1 在 notebook 或等价脚本中可生成至少一张 `p1(t)` 动力学对比图。
- [x] 输出中包含 baseline / detuned 两个 case。
- [x] 提供 `QuantumOptics.jl` 原生参考代码，包含求解器与观测量提取。
- [x] 提供 `QuTiP` 原生参考代码，包含求解器与观测量提取。
- [x] 对照结果可用于人工判断“engine 是否被正确调用”。
- [x] 相关 `docstring` 已新增或更新。
- [x] `docs/` 下对应文档已新增或更新。

## 8. 测试计划
- 单元测试：
- 增加/更新 Task1 语义映射函数测试（`basis_population_single_qubit` 与 `per_qubit_excited_probability` -> `p1(t)`）。
- 集成测试：
- 执行 Task1 三引擎流程并检查图像文件、summary 文件存在与字段完整性。
- 回归测试：
- 确认现有 `pointwise-comparable` 相关逻辑不被破坏。
- 样例数据 / 命令：
- 使用 `task1_single_qubit_baseline.json` 的 baseline 与 detuned。

## 9. 风险与回滚
- 主要风险：
- 将“观测量可比”误解为“状态编码逐点可比”。
- 不同引擎原生实现细节不同，导致曲线幅值存在系统性偏差。
- 监控 / 告警点：
- 图中缺失某一引擎曲线。
- summary 中 `final_p1_obs` 与 `p1(t_end)` 显著不一致。
- 回滚策略：
- 保留原有严格绘图路径，新增逻辑用开关或独立函数隔离；必要时可快速回退到旧展示逻辑。

## 10. 依赖与阻塞
- 前置依赖：
- Task1 现有运行工件可访问。
- 外部依赖（库 / 环境 / 数据）：
- `QuTiP` 可用。
- Julia + `QuantumOptics.jl` 可用（用于原生代码实跑核验）。
- 潜在阻塞：
- 本地 Julia 包环境不完整时，原生对照代码只能先给模板、不能实跑。

## 11. 估时与优先级
- 优先级：P1
- 预计工期：0.5 ~ 1 天
- 负责人：Codex

## 12. 参考
- [examples/noise_simulation_tests/required_tasks_tri_engine.ipynb](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/required_tasks_tri_engine.ipynb)
- [examples/noise_simulation_tests/required_tasks_tri_engine/task1_single_qubit_baseline.json](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/required_tasks_tri_engine/task1_single_qubit_baseline.json)
- [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py)
- [scripts/julia_engine_bridge.jl](/d:/超导量子计算机噪声抑制/qsim/scripts/julia_engine_bridge.jl)

## 13. 验收记录
- 代码：
  - 新增 [task1_single_qubit_visual_compare.py](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task1_single_qubit_visual_compare.py)
  - 新增 [task1_qutip_native_reference.py](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task1_qutip_native_reference.py)
  - 新增 [task1_quantumoptics_native_reference.jl](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task1_quantumoptics_native_reference.jl)
  - 更新 [trace_semantics.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/analysis/trace_semantics.py)
  - 更新 [test_trace_semantics.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_trace_semantics.py)
- 文档：
  - 更新 [README.md](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/README.md)
  - 更新 [noise_engine.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/noise_engine.md)
- 产物（脚本运行生成）：
  - [task1_single_qubit_baseline_visual_compare_summary.csv](/d:/超导量子计算机噪声抑制/qsim/task1_outputs/task1_single_qubit_baseline_visual_compare_summary.csv)
  - [task1_p1_dynamics_long.csv](/d:/超导量子计算机噪声抑制/qsim/task1_outputs/task1_p1_dynamics_long.csv)
  - [task1_baseline_p1_dynamics.png](/d:/超导量子计算机噪声抑制/qsim/task1_outputs/task1_baseline_p1_dynamics.png)
  - [task1_detuned_p1_dynamics.png](/d:/超导量子计算机噪声抑制/qsim/task1_outputs/task1_detuned_p1_dynamics.png)
  - [task1_final_p1_bar.png](/d:/超导量子计算机噪声抑制/qsim/task1_outputs/task1_final_p1_bar.png)
- 测试：
  - 运行：`pytest -q -p no:cacheprovider --basetemp .pytest_tmp tests/test_trace_semantics.py`
  - 结果：`8 passed`



