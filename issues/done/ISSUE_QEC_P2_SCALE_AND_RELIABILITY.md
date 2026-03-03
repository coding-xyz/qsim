# [QEC-P2] 并行扫描与可靠性增强（Scale + Retry + Repro）

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-02

## 1. 背景与目标
- 背景：P0/P1 已打通 prior/decoder/analysis/eval 产物链路，但当前执行仍以单机串行为主，长任务与批量扫描在稳定性和效率上存在瓶颈。
- 目标：建设可恢复、可并行、可审计的运行层，支持中等规模参数扫描与失败自动恢复。
- 为什么现在做：P1 输出已足够用于比较分析，P2 需要提升吞吐与稳定性，避免人工重跑。

## 2. 范围
- In Scope：
  - 引入本地并行执行器（优先 `ProcessPoolExecutor`，保留后续 Dask/Celery 扩展位）。
  - 实现任务级重试与断点续跑（resume）。
  - 增强可复现记录：任务输入签名、worker 元数据、失败原因分类。
  - 输出批处理汇总报告。
- Out of Scope：
  - 不做分布式集群调度（跨机）与队列系统部署。
  - 不做 UI 仪表盘（放到 P3）。

## 3. 输入与输出（I/O）
- 输入：
  - `decoder_eval` 配置（decoder 列表、seed 列表、参数网格）
  - `backend.sweep`（可选）
  - 运行策略参数（并行度、重试次数、超时）
- 输出：
  - `batch_manifest.json`（批任务级）
  - `decoder_eval_report.json`（增强字段）
  - `decoder_eval_table.csv`
  - `failed_tasks.jsonl`（失败任务明细）
  - `resume_state.json`（断点状态）
- schema/version：
  - `schema_version: 1.0`
  - `batch_id`, `task_id`, `attempt`, `worker_id`, `input_hash`

## 4. 技术方案
- 方案概述：
  - 新增 `src/qsim/runtime/executor.py`：任务拆分、并行执行、重试策略。
  - 新增 `src/qsim/runtime/resume.py`：状态落盘与恢复。
  - 在 `run_workflow(... decoder_eval=True)` 或单独 `eval` 入口接入批执行模式。
- 关键设计决策：
  - 任务最小粒度：`(decoder, seed, option_set)`。
  - 每个任务独立产生日志与结果，汇总层只做聚合，避免单点失败拖垮整批。
  - 失败分为可重试（超时/临时IO）与不可重试（输入错误）两类。
- 可替换点/扩展点：
  - `IExecutor.submit(tasks, policy) -> BatchResult`
  - 后续可替换为 Dask/Celery 后端而不改上层评估逻辑。

## 5. 任务拆分
1. 设计批任务 schema（task_id、状态机、重试元数据）。
2. 实现本地并行执行器与限流。
3. 实现失败重试与 `resume_state.json`。
4. 增加批处理汇总输出（`batch_manifest.json`、失败明细）。
5. 接入 CLI 参数（并行度、重试、resume 开关）。

## 6. 验收标准（DoD）
- [ ] 同一批任务在并行模式下可稳定完成并输出完整汇总。
- [ ] 人为注入失败后可自动重试并在可恢复场景成功续跑。
- [ ] 中断后可基于 `resume_state.json` 从未完成任务继续执行。
- [ ] `run_manifest/batch_manifest` 包含任务级输入签名与失败原因。

## 7. 测试计划
- 单元测试：
  - 任务分片、状态迁移、重试判定逻辑。
- 集成测试：
  - `2 decoder x 3 seeds x 3 options` 并行跑批，核对汇总一致性。
  - 注入一次可重试错误，验证重试成功。
  - 模拟中断后 resume，验证不重复执行已完成任务。
- 回归测试：
  - 关闭并行时保持现有串行行为不变。

## 8. 风险与回滚
- 主要风险：
  - 并行写文件冲突与锁问题（Windows 环境尤为明显）。
  - 重试机制导致重复写入或结果不一致。
- 缓解：
  - 任务隔离输出目录 + 原子写入（临时文件后 rename）。
  - 汇总前按 `task_id` 去重并校验 `input_hash`。
- 回滚策略：
  - 保留串行执行路径作为默认回退。

## 9. 依赖与阻塞
- 前置依赖：
  - P1-M5 已完成（decoder eval 产物链路可用）。
- 外部依赖：
  - 标准库可实现首版（无需新增强依赖）。
  - 可选后续依赖：`dask` / `celery`（暂不强制）。
- 潜在阻塞：
  - 现有目录权限/文件锁策略不统一（需统一约定输出目录规范）。

## 10. 估时与优先级
- 优先级：P2
- 预计工期：4-7 天
- 负责人：待指派

## 11. 参考
- `src/qsim/ui/notebook.py`
- `src/qsim/qec/eval.py`
- `scripts/cleanup_test_artifacts.ps1`
- `ISSUE_QEC_P0_ROADMAP.md`
