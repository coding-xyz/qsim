# 量子纠错

本文先介绍离线处理与误差分析的完整流程，再逐步说明每一步在代码中的实现位置。
状态说明：

- 当前支持：离线分析（产物落盘后评估、对比、回归）。
- 当前不支持：实时解码（在线流式 syndrome 输入与实时反馈控制）尚未上线。


## 1. 离线处理全流程

离线模式下，一次 `run_task(task)` 会生成可复现产物，按以下顺序执行：

1. 读取电路和后端配置，完成编译/Lowering/求解，得到 `trace`。
2. 从 `trace` 阈值化构造 `SyndromeFrame`（QEC 输入）。
3. 基于 syndrome 构建先验图 `PriorModel`，并记录 `prior_report`。
4. 运行 decoder（`mwpm`/`bp`/`mock`），得到 `DecoderOutput`。
5. 从 decoder 输出汇总 `LogicalErrorSummary` 和 `decoder_report`。
6. 在 analysis 侧生成敏感度报告与误差预算（P1）。
7. 可选执行 decoder 批评估（P1/P2）：并行、重试、续跑。
8. 将全部 JSON/CSV/H5 产物写盘，并写入 `run_manifest.json`。

这条链路的入口在：

- 用户/程序入口：`src/qsim/workflow/__init__.py::run_task`
- 执行主体：`src/qsim/workflow/pipeline.py::run_task`

## 2. 误差分析流程（逻辑层）

误差分析由三层组成：

1. 基础观测量层：`trace -> observables`
2. QEC 逻辑误差层：`decoder_output -> logical_error`
3. 聚合分析层：`observables + logical_error -> sensitivity/error_budget`

当前实现是可复现的代理模型（proxy），用于回归比较和方案排序，不等同于完整物理标定。

## 3. 逐步映射到代码实现

### Step A: 从 trace 生成 syndrome

- 代码：
  - `src/qsim/workflow/pipeline.py` 中 `SyndromeFrame(...)` 构造段
- 输入：
  - `trace.times`, `trace.states`
- 输出：
  - `syndrome_frame.json`

说明：当前使用阈值 `0.5` 将 state 样本二值化，作为 detector 事件。

### Step B: 构建 prior（Stim/Cirq/Mock/Auto）

- 代码：
  - `qsim.qec.prior.build_prior_and_report`
  - `qsim.qec.prior.StimPriorBuilder`
  - `qsim.qec.prior.CirqPriorBuilder`
- 输入：
  - `SyndromeFrame` + `context`
- 输出：
  - `prior_model.json`
  - `prior_report.json`

说明：

- `backend="auto"` 时按 `stim -> cirq -> mock` 回退。
- 外部依赖不可用时仍返回确定性 fallback prior，并在 metadata 写 `fallback_reason`。

### Step C: 解码与逻辑误差汇总

- 代码：
  - `qsim.qec.decoder.get_decoder`
  - `qsim.qec.decoder.MWPMDecoder.run`
  - `qsim.qec.decoder.BPDecoder.run`
  - `qsim.qec.decoder.build_decoder_report`
  - `qsim.qec.decoder.summarize_logical_error`
- 输入：
  - `DecoderInput(syndrome, prior, options)`
- 输出：
  - `decoder_output.json`
  - `decoder_report.json`
  - `logical_error.json`

说明：

- `MWPM` 当前是轻量 parity-pairing 近似实现。
- `BP` 当前是列级 belief 更新近似实现，可通过 `max_iter`、`damping` 调参。

### Step D: 敏感度与误差预算（P1-M4）

- 代码：
  - `qsim.analysis.sensitivity.build_sensitivity_report`
  - `qsim.analysis.sensitivity.build_error_budget_v2`
- 输入：
  - `Observables`
  - `LogicalErrorSummary`
- 输出：
  - `sensitivity_report.json`
  - `error_budget_v2.json`
  - `figures/sensitivity_heatmap.png`

说明：该层输出参数敏感度排序和误差项排序，主要用于相对比较与回归跟踪。

### Step D2: Pauli+/Kraus 对齐预算（P2）

- 代码：
  - `qsim.analysis.pauli_plus`
  - `qsim.analysis.error_budget_pauli`
  - `qsim.engines.stim_qec_engine`
  - `qsim.engines.cirq_qec_engine`
- 输入：
  - 组件误差模型（由当前 run 指标映射得到）
  - 码距列表（默认 `d=3,5`）
- 输出：
  - `scaling_report.json`（含 `epsilon_3`, `epsilon_5`, `lambda_3_5`）
  - `error_budget_pauli_plus.json`（baseline vs component-off ablation）
  - `component_ablation.csv`

说明：

- `qec_engine=auto` 时优先走 Stim，失败回退 Cirq。
- `scaling_report` 中 `native_runs_ratio` 用于标记本次是否主要使用原生后端。

### Step E: Decoder 批评估（P1-M5 + P2）

- 代码：
  - `qsim.qec.eval.run_decoder_eval`
  - `qsim.qec.eval.write_decoder_eval_csv`
  - `qsim.qec.eval.write_failed_tasks_jsonl`
- 输入：
  - `decoders`, `seeds`, `option_grid`
  - 运行策略：`parallelism`, `retries`, `resume`
- 输出：
  - `decoder_eval_report.json`
  - `decoder_eval_table.csv`
  - `figures/decoder_pareto.png`
  - `batch_manifest.json`
  - `resume_state.json`
  - `failed_tasks.jsonl`

说明：

- 并行默认 `ProcessPoolExecutor`，受限环境会降级串行并记录失败原因。
- `resume_state.json` 用于跳过已完成任务，实现断点续跑。

### Step F: 产物落盘与可复现索引

- 代码：
  - `qsim.common.schemas.write_json`
  - `qsim.common.schemas.RunManifest`
  - `src/qsim/workflow/pipeline.py` 的 artifact write + manifest write 段
- 输出：
  - `run_manifest.json`
  - `timings.json`
  - 全部中间与结果产物

说明：`run_manifest.json` 统一登记输入、输出、依赖版本与摘要信息，供离线复盘和比较使用。

## 4. 最小产物检查清单

基础链路（P0）：

- `syndrome_frame.json`
- `prior_model.json`
- `decoder_output.json`
- `logical_error.json`

分析链路（P1）：

- `sensitivity_report.json`
- `error_budget_v2.json`
- `figures/sensitivity_heatmap.png`
- `decoder_eval_report.json`
- `figures/decoder_pareto.png`

可靠性链路（P2）：

- `batch_manifest.json`
- `resume_state.json`
- `failed_tasks.jsonl`

## 5. 相关模块索引

- QEC 接口：`src/qsim/qec/interfaces.py`
- Prior：`src/qsim/qec/prior.py`
- Decoder：`src/qsim/qec/decoder.py`
- Eval：`src/qsim/qec/eval.py`
- Sensitivity：`src/qsim/analysis/sensitivity.py`
- Workflow 入口：`src/qsim/workflow/__init__.py`
- Workflow 执行编排：`src/qsim/workflow/pipeline.py`

