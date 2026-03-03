# [QEC-P1] 解码器评估、参数扫描与对比报告

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 背景与目标
- 背景：P0 已提供解码器接口与基础产物，但缺少系统化评估机制，不便于算法选择与回归比较。
- 目标：建立 MWPM/BP（及后续算法）的统一评估与参数扫描框架，输出对比报告。
- 为什么现在做：P1 阶段需要可量化比较，支撑“选哪个解码器、用什么参数”。

## 2. 范围
- In Scope：
  - 支持 `decoder + hyperparams + seed` 的网格扫描。
  - 输出关键指标：logical error、运行时、收敛率、失败率。
  - 生成排行榜与 Pareto 视图（精度-速度）。
- Out of Scope：
  - 不做在线自动调参（Bayes/EA）；
  - 不做分布式执行（P2）。

## 3. 输入与输出（I/O）
- 输入：
  - `decoder_input.json`
  - 扫描配置（算法列表、参数网格、seed 列表）
- 输出：
  - `decoder_eval_report.json`
  - `decoder_eval_table.csv`
  - `figures/decoder_pareto.png`（可选）
- schema/version：
  - `schema_version: 1.0`
  - `eval_rev`, `benchmark_set`, `timestamp`

## 4. 技术方案
- 方案概述：
  - 新增 `decoder/eval.py` 统一执行评测任务。
  - 使用固定数据集 + 固定 seed 提供可复现 benchmark。
  - 报告层与执行层分离，便于扩展新算法。
- 关键决策：
  - 先支持串行执行，接口保留并行扩展位。
  - 输出表格优先，图形为可选增强。
- 可替换点：
  - `DecoderEvaluator.run(config) -> EvalReport`

## 5. 任务拆分
1. 设计评估配置 schema。
2. 实现运行器与指标聚合。
3. 输出 JSON/CSV 与可选图。
4. 接入 CLI 参数（如 `qsim eval-decoder ...`）。

## 6. 验收标准（DoD）
- [ ] 同一输入与 seed 下评估结果稳定复现。
- [ ] 至少支持 MWPM 与 BP 两种算法对比。
- [ ] 生成报告包含精度、耗时、收敛/失败统计。
- [ ] 结果被 manifest 正确引用。

## 7. 测试计划
- 单元测试：
  - 指标聚合逻辑、排序逻辑、CSV 导出。
- 集成测试：
  - 小网格评估（2 算法 x 2 参数 x 2 seed）。
- 回归测试：
  - 与已有 workflow 不冲突，未开启评估时不增加耗时。

## 8. 风险与回滚
- 风险：评估配置爆炸导致运行时间不可控。
- 缓解：配置增加预算限制（最大任务数/最大时长）。
- 回滚：默认关闭评估功能，仅按需运行。

## 9. 依赖与阻塞
- 前置依赖：P0 解码器实现与稳定 I/O。
- 外部依赖：可选 `pandas/matplotlib`。
- 阻塞：基准数据集定义未统一。

## 10. 估时与优先级
- 优先级：P1
- 工期：3-5 天
- 负责人：待指派

## 11. 参考
- `ISSUE_QEC_P0_DECODER_MWPM_BP.md`
- `src/qsim/qec/interfaces.py`
- `src/qsim/ui/cli.py`
