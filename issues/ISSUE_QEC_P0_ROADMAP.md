# QEC Roadmap (P0 -> P1)

## 1. 总览
- 目标：打通 `schema -> prior -> decoder -> analysis` 的可复现闭环。
- 当前状态：P0-M1 已完成（schema/接口/workflow 占位产物）。
- 执行原则：先稳定 I/O 契约，再迭代算法质量与真实后端。

## 2. 依赖关系
1. `ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md`（已落地 M1）
2. `ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md`（依赖 1）
3. `ISSUE_QEC_P0_DECODER_MWPM_BP.md`（依赖 1，主线建议在 2 后接入）
4. `ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md`（依赖 3）
5. `ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md`（依赖 3）
6. `ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md`（与 4/5 可并行）

## 3. 里程碑计划

### M1（已完成）接口冻结与占位闭环
- 完成项：
  - QEC schema：`SyndromeFrame/PriorModel/DecoderInput/DecoderOutput/LogicalErrorSummary`
  - 接口：`IPriorBuilder/IDecoder`
  - Workflow 产物：`syndrome_frame/prior_model/decoder_input/decoder_output/logical_error`
  - manifest 引用与测试覆盖

### M2（P0）先验模块落地
- 对应 issue：`ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md`
- 输出：
  - `prior_model.json`
  - `prior_report.json`
  - （可选）`prior_samples.npz`
- Go 条件：先验产物稳定生成；manifest 记录完整。

### M3（P0）解码器主链路
- 对应 issue：`ISSUE_QEC_P0_DECODER_MWPM_BP.md`
- 输出：
  - `decoder_output.json`
  - `logical_error.json`
  - `decoder_report.json`
- Go 条件：`mwpm` 可复现跑通；`bp` 至少可运行并输出结构化失败信息。

### M4（P1）分析升级（误差预算/敏感度）
- 对应 issue：`ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md`
- 输出：
  - `sensitivity_report.json`
  - `error_budget_v2.json`
  - （可选）敏感度热图
- Go 条件：固定 seed 可复现；主导误差项排序稳定。

### M5（P1）解码评估与参数扫描
- 对应 issue：`ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md`
- 输出：
  - `decoder_eval_report.json`
  - `decoder_eval_table.csv`
  - （可选）Pareto 图
- Go 条件：支持 MWPM/BP 对比；指标（精度/耗时/失败率）齐全。

### M6（P1）真实 Julia 引擎桥接
- 对应 issue：`ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md`
- 输出：
  - 至少一个真实 Julia 后端可运行
  - trace 与现有流程兼容
- Go 条件：真实路径可跑；失败时可回退且错误可定位。

## 4. 并行建议
- 线 A：M2 -> M3（QEC 主链）
- 线 B：M6（引擎桥接）
- 线 C：M4 + M5（分析与评估，依赖 M3）

## 5. 风险与缓解
1. schema 变更引发返工
- 缓解：字段冻结后仅追加，不破坏旧字段。

2. prior 口径不一致（Stim/Cirq）
- 缓解：`prior_report` 强制记录映射规则和 source hash。

3. BP 收敛不稳定
- 缓解：默认 `mwpm` 主路径，bp 失败降级并记录 warning。

4. Julia 环境不一致
- 缓解：版本锁定、运行前检查、保留 fallback。

## 6. MVP（P1 结束时）
- 输入：`circuit + backend + syndrome`
- 过程：`prior -> decoder(mwpm/bp) -> analysis/eval`
- 输出：
  - `prior_model.json`
  - `decoder_output.json`
  - `logical_error.json`
  - `sensitivity_report.json`
  - `decoder_eval_report.json`
  - `run_manifest.json`（含以上文件哈希）

## 7. 执行建议
1. 每个里程碑拆成小 PR：实现 + 测试 + 文档同时提交。
2. 每次合并都跑 manifest 回归，防止产物漂移。
3. 用 `scripts/cleanup_test_artifacts.ps1` 清理测试产物与锁文件目录。

## 8. 完整验收清单（当前状态）

说明：
- 状态定义：`完成` / `部分完成` / `未开始` / `按计划跳过`
- 统计时间：当前分支最新测试结果（`14 passed`）

### P0-M1（接口冻结与占位闭环）
- [x] schema 已定义：`SyndromeFrame/PriorModel/DecoderInput/DecoderOutput/LogicalErrorSummary`（完成）
- [x] QEC 接口已定义：`IPriorBuilder/IDecoder`（完成）
- [x] Workflow 产物已落地并写入 manifest（完成）
- [x] 最小集成测试通过（完成）

### P0-M2（Stim/Cirq Prior）
- [x] `build_prior_and_report` 支持 `auto|stim|cirq|mock`（完成）
- [x] Stim/Cirq 不可用时可回退且记录 `fallback_reason`（完成）
- [x] `prior_model.json` / `prior_report.json` 持久化（完成）
- [ ] `prior_samples.npz`（可选项，未实现）

### P0-M3（MWPM/BP Decoder）
- [x] `mwpm`/`bp` 解码器可运行并可配置（完成）
- [x] `decoder_output.json` / `logical_error.json` / `decoder_report.json` 持久化（完成）
- [x] `run_manifest.json` 引用完整（完成）
- [x] 回归测试覆盖 M2/M3 workflow（完成）

### P1-M4（敏感度与误差预算）
- [x] `sensitivity_report.json` 产物生成（完成）
- [x] `error_budget_v2.json` 产物生成（完成）
- [x] 固定 seed 下报告结构稳定（完成）
- [ ] 可视化热图（可选项，未实现）

### P1-M5（Decoder Eval & Sweep）
- [x] 产物：`decoder_eval_report.json` + `decoder_eval_table.csv`（完成）
- [x] 支持多 decoder / 多 seed / 参数网格（完成）
- [x] CLI 参数可控制 eval decoders/seeds（完成）
- [x] 报告包含 summary 与 pareto 字段（完成）

### P1-M6（真实 Julia 引擎桥接）
- [ ] 真实 Julia 后端链路（按计划跳过，另开 issue）

### P2（Scale + Retry + Resume）
- [x] 并行执行控制：`eval_parallelism`（完成）
- [x] 重试控制：`eval_retries`（完成）
- [x] 断点续跑：`eval_resume` + `resume_state.json`（完成）
- [x] 批任务清单：`batch_manifest.json`（完成）
- [x] 失败任务清单：`failed_tasks.jsonl`（完成）
- [x] Windows 并行受限时自动降级串行并记录失败原因（完成）

### 当前总体结论
- P0：主线验收通过（M1/M2/M3 完成；可选项 `prior_samples.npz` 未做）
- P1：M4/M5 完成，M6 按计划跳过
- P2：已实现首版可靠性增强并通过当前测试
