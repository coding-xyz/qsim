# 文件 IO

本页说明一次 workflow 运行会生成哪些文件、这些文件分别表示什么，以及 session 归档机制如何工作。对于需要检查结果目录、复盘运行过程或做后续自动处理的用户，这一页是结果文件说明书。

## 1. 输出目录的作用

每次运行都会把结果写入 `task.output.out_dir` 指定的目录。  
这个目录既保存最终结果，也保存中间产物、图像、汇总报告和 manifest，因此可以把它理解为一次完整运行的“结果快照”。

如果 `persist_artifacts` 为 `true`，大多数关键对象都会被写出到磁盘。

## 2. 常见输出文件总览

基础 workflow 常见会生成：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `pulse_samples.npz`
- `executable_model.json`
- `model_spec.json`
- `trace.h5`
- `settings_report.json`
- `run_manifest.json`
- `timings.json`

根据 target 和 feature 不同，还可能额外生成：

- `syndrome_frame.json`
- `prior_model.json`
- `prior_report.json`
- `prior_samples.npz`
- `decoder_input.json`
- `decoder_output.json`
- `decoder_report.json`
- `logical_error.json`
- `sensitivity_report.json`
- `error_budget_v2.json`
- `decoder_eval_report.json`
- `decoder_eval_table.csv`
- `batch_manifest.json`
- `resume_state.json`
- `failed_tasks.jsonl`
- `scaling_report.json`
- `error_budget_pauli_plus.json`
- `component_ablation.csv`

## 3. 基础产物分别表示什么

### `circuit.json`

表示导入并规范化后的电路信息。  
适合用来确认：

- 电路是否被正确读取
- 量子比特和操作是否符合预期

### `backend_config.json`

表示最终进入 workflow 主链路的 backend 配置。  
它适合用于确认：

- solver 与 noise 组合后到底形成了什么 backend 设置
- 某些字段是否被默认值补齐

### `normalized_circuit.json`

表示标准化之后的电路版本。  
如果原始输入和后续求解行为不一致，这个文件通常是排查入口之一。

### `compile_report.json`

用于记录编译阶段的结果和摘要。  
它适合查看：

- 编译过程中做了哪些处理
- 是否命中了特定 lowering / compile 路径

### `pulse_ir.json`

表示脉冲中间表示。  
如果你关心门是怎样被映射为脉冲的，这是最重要的输出之一。

### `pulse_samples.npz`

保存采样后的脉冲数据。  
常用于：

- 可视化
- 后续度量统计
- pulse 级调试

### `executable_model.json`

表示更靠近执行层的模型表示。  
它适合在编译与求解之间检查模型是否构造正确。

### `model_spec.json`

表示最终送入引擎前的模型规格。  
它可以帮助确认：

- 求解模式
- 模型维度
- 引擎实际接收到的结构信息

### `trace.h5`

保存求解器输出的时间轴和状态采样，是数值结果的核心文件之一。

### `settings_report.json`

汇总一次运行中关键设置的报告，通常适合快速总览本次实验条件。

### `timings.json`

记录各阶段耗时，适合分析：

- 哪个阶段最耗时
- 不同任务之间的性能差异

## 4. `trace.h5` 里有什么

`trace.h5` 是最重要的运行结果文件之一。  
常见内容包括：

- dataset: `times`
- dataset: `states`
- attrs: `engine`
- attrs: `state_encoding`
- attrs: `num_qubits`
- attrs: `model_dimension`

它的典型用途包括：

- 后续绘图
- 数值分析
- 跨引擎结果比较
- 结果复盘

## 5. `run_manifest.json` 的作用

`run_manifest.json` 用于给一次运行建立统一索引。  
可以把它理解为“本次运行的目录说明书”。

它通常会记录：

- 输出文件映射
- 依赖版本
- 依赖指纹
- backend 来源
- qasm 摘要

这个文件对以下工作尤其重要：

- 长期归档
- 结果比对
- 自动扫描一批运行目录

## 6. QEC 和分析相关输出

当任务目标涉及 decode 或 analysis 时，会出现更多专门文件。

### decode 相关

- `syndrome_frame.json`
- `prior_model.json`
- `prior_report.json`
- `prior_samples.npz`
- `decoder_input.json`
- `decoder_output.json`
- `decoder_report.json`
- `logical_error.json`

### analysis 相关

- `sensitivity_report.json`
- `error_budget_v2.json`
- `scaling_report.json`
- `error_budget_pauli_plus.json`
- `component_ablation.csv`

### decoder eval 相关

- `decoder_eval_report.json`
- `decoder_eval_table.csv`
- `batch_manifest.json`
- `resume_state.json`
- `failed_tasks.jsonl`

## 7. 图像文件

当 `export_plots` 或 `export_dxf` 打开时，结果目录中还可能出现：

- `pulse_timing.png`
- `trace.png`
- `report.png`
- `timing_diagram.dxf`

这些文件属于辅助检查和展示型输出，但在很多实验中同样非常重要。

## 8. session 自动提交是什么

除了把文件写进 `out_dir` 之外，workflow 还支持把部分结果自动提交到 session。

只有下面两个条件同时满足时，session 自动提交才会发生：

- `output.session_auto_commit: true`
- `output.session_dir` 已设置

对应逻辑在：

- `src/qsim/workflow/session_adapter.py`

## 9. 默认会提交哪些类别

默认会尝试提交的类别包括：

- `settings`
- `timings`
- `logical_error`
- `decoder_report`
- `sensitivity_report`
- `error_budget_v2`

如果某个结果在本次运行中不存在，那么对应类别会被跳过。

你也可以通过 `output.session_commit_kinds` 自定义提交类别集合。

## 10. session 目录里会发生什么

`src/qsim/session/session.py` 中的 `Session` 会负责：

- 在 `artifacts/` 下按 revision 存放 JSON 产物
- 在 `session_manifest.json` 中登记 revision 元数据
- 为每次提交记录输入、依赖、时间戳和标签

这意味着 session 更像是“结果版本库”，而不仅仅是普通文件夹。

## 11. 推荐的检查顺序

当一次运行结束后，建议按以下顺序查看结果目录：

1. 先看 `run_manifest.json`
2. 再看 `settings_report.json`
3. 再看 `timings.json`
4. 然后看 `trace.h5`
5. 如果有 QEC，继续看 `logical_error.json` 和 `decoder_report.json`
6. 如果有分析，继续看 `sensitivity_report.json`、`error_budget_v2.json`

这样可以先确认“任务是怎么跑的”，再去看“任务跑出了什么”。

## 12. 常见问题

### 为什么结果目录里文件很多

因为 workflow 默认会写出一整套中间产物和结果文件，这正是它可复现和可追踪的优势。

### 我只想保留关键结果怎么办

可以考虑：

- 使用 `artifact_mode: targeted`
- 关闭不需要的图像导出
- 只保留必要的 session 提交类别

### 为什么某些 QEC 文件没有生成

通常是因为本次 `target` 没有包含相应阶段，或者 `decoder`、feature 等条件没有满足。
