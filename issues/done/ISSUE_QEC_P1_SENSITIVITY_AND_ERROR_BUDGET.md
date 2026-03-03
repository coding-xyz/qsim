# [QEC-P1] 升级误差预算与敏感度分析管线

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 背景与目标
- 背景：当前 `report` 的误差预算仍以轻量启发式为主，尚未形成 QEC 可解释的灵敏度分析闭环。
- 目标：构建参数扰动 -> 逻辑错误率变化的标准化分析流程，输出可复现实验报告。
- 为什么现在做：P0 已打通基础解码链路，P1 需要把“能跑”提升为“可分析、可决策”。

## 2. 范围
- In Scope：
  - 新增敏感度扫描配置（单参/双参）。
  - 输出逻辑错误率响应面、局部梯度与误差贡献排序。
  - 生成结构化 `sensitivity_report.json` 与图表产物。
- Out of Scope：
  - 不做大规模分布式扫描（P2 再做）。
  - 不引入 ML surrogate（后续）。

## 3. 输入与输出（I/O）
- 输入：
  - `logical_error.json`
  - `decoder_output.json`
  - 扫描参数配置（可来自 `backend.sweep`）
- 输出：
  - `sensitivity_report.json`
  - `error_budget_v2.json`
  - `figures/sensitivity_heatmap.png`（可选）
- schema/version：
  - `schema_version: 1.0`
  - `analysis_rev`, `pipeline_name`, `seed`

## 4. 技术方案
- 方案概述：
  - 在 `analysis` 增加 `sensitivity.py`（扫描/汇总）与 `error_budget_v2.py`。
  - 将分析 pass 通过 `AnalysisRegistry` 注册，沿用现有插件机制。
  - 支持最小二乘局部拟合或有限差分估计灵敏度。
- 关键设计决策：
  - 先做 deterministic 扫描路径，确保可重复。
  - 结果字段与图输出分离，报告 JSON 为主、图像为辅。
- 可替换点：
  - `SensitivityAnalyzer.run(grid, metrics) -> report`

## 5. 任务拆分
1. 设计扫描参数与报告 schema。
2. 实现扫描执行与聚合统计。
3. 接入 workflow 并写 manifest。
4. 增加图形输出（heatmap/bar）。

## 6. 验收标准（DoD）
- [ ] 给定固定 seed，重复运行报告一致。
- [ ] `sensitivity_report.json` 含主导误差项排序与局部灵敏度。
- [ ] `run_manifest.json` 记录新产物。
- [ ] 文档给出最小扫描示例。

## 7. 测试计划
- 单元测试：
  - 扫描网格生成、梯度估计、排序稳定性。
- 集成测试：
  - 最小工作流 + 小网格扫描（2x2/3x3）。
- 回归测试：
  - 不影响原始 `report.json` 兼容读取。

## 8. 风险与回滚
- 风险：参数空间定义不统一导致结果不可比。
- 缓解：报告中强制记录扫描维度、范围、步长。
- 回滚：保留旧 `error_budget` 输出，新增 `v2` 并行。

## 9. 依赖与阻塞
- 前置依赖：P0 schema/prior/decoder 基线完成。
- 外部依赖：`numpy`, `matplotlib`（可选）。
- 阻塞：逻辑错误指标口径需统一。

## 10. 估时与优先级
- 优先级：P1
- 工期：3-5 天
- 负责人：待指派

## 11. 参考
- `src/qsim/analysis/error_budget.py`
- `src/qsim/analysis/registry.py`
- `ISSUE_QEC_P0_DECODER_MWPM_BP.md`
