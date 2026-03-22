# 量子纠错

本页说明 `qsim` 当前的量子纠错相关能力，包括离线分析流程、prior 与 decoder 的角色、不同 target 对应的执行阶段，以及典型输出文件的含义。它更适合当作 QEC 使用说明书来阅读。

## 1. 当前能力定位

`qsim` 当前提供的是离线量子纠错分析能力，而不是在线实时反馈控制。

这意味着它更适合：

- 对一次仿真结果做 syndrome / prior / decoder 分析
- 比较不同 decoder 配置
- 生成 logical error、sensitivity、Pauli+ 相关结果
- 做批量解码评估与结果归档

而不适合：

- 在线流式 syndrome 输入
- 实时控制回写
- 硬件闭环反馈

## 2. QEC 主流程

当任务目标需要量子纠错分析时，workflow 会沿着以下主链路运行：

1. `run_engine_stage`
2. `run_decode_stage`
3. `run_analysis_stage`

在这之后，还可能根据 feature 打开额外分支：

- `run_decoder_eval_plugin`
- `run_pauli_plus_plugin`

因此，QEC 在当前项目中不是独立入口，而是建立在已有仿真结果之上的后续分析流程。

## 3. 从 trace 到 logical error 的流程

可以把当前 QEC 链路理解为下面几个步骤：

1. 仿真得到 `trace`
2. 从 `trace` 中提取 syndrome frame
3. 根据 syndrome 构建 prior
4. 调用 decoder 得到解码结果
5. 汇总为 logical error
6. 根据需要继续做 sensitivity、Pauli+ 或 decoder eval

这个流程中每一步都会产出对应文件，因此比较适合逐步排查问题。

## 4. prior 是什么

prior 可以理解为“解码前的先验模型或先验信息来源”。  
当前实现位于：

- `src/qsim/qec/prior.py`

支持的 prior backend 包括：

- `stim`
- `cirq`
- `mock`
- `auto`

其中：

- `auto` 会在多个可用后端之间自动选择
- `mock` 适合依赖缺失时做占位或流程测试

## 5. decoder 是什么

decoder 负责利用 syndrome 和 prior 做离线解码分析。  
当前实现位于：

- `src/qsim/qec/decoder.py`

当前支持：

- `mwpm`
- `bp`
- `mock`

通常可以这样理解：

- `mwpm`：适合做匹配类解码
- `bp`：适合 belief propagation 风格实验
- `mock`：适合流程打通和占位测试

## 6. solver 配置里与 QEC 有关的字段

QEC 相关运行主要依赖 solver 配置中的以下字段：

- `run.prior_backend`
- `run.decoder`
- `run.decoder_options`
- `run.qec_engine`

其中最关键的是：

- `run.decoder`

如果任务目标需要进入 decode 或 analysis 阶段，而这里没有配置 decoder，执行计划会拒绝运行。

## 7. 不同 target 会跑到哪一步

当前常见 target 与阶段关系如下：

### `logical_error`

会运行到 decode 阶段，生成逻辑误差相关结果。

### `sensitivity_report`

会在 decode 之后继续进入 analysis 阶段。

### `decoder_eval_report`

会在 decode 基础上继续执行 decoder eval 插件。

### `scaling_report`

会在 analysis 基础上继续执行 Pauli+ 插件。

### `error_budget_pauli_plus`

同样依赖 Pauli+ 分析分支。

这些目标通常都要求：

- `solver.run.decoder` 已配置

## 8. 基础输出文件说明

当 QEC 主链路运行后，常见输出包括：

- `syndrome_frame.json`
- `prior_model.json`
- `prior_report.json`
- `prior_samples.npz`
- `decoder_input.json`
- `decoder_output.json`
- `decoder_report.json`
- `logical_error.json`

这些文件可以按下面方式理解。

### `syndrome_frame.json`

表示从 trace 中提取出来的 syndrome 信息。  
它是后续 prior 和 decoder 的直接输入基础。

### `prior_model.json`

表示本次运行构建出的 prior 模型。

### `prior_report.json`

表示 prior 构建过程的说明性结果，通常适合用于检查：

- 实际采用了哪个 prior backend
- 是否发生了 fallback

### `prior_samples.npz`

表示 prior 相关的采样数据。

### `decoder_input.json`

表示真正送进 decoder 的输入结构。  
如果你怀疑 decoder 行为异常，这通常是重点排查对象。

### `decoder_output.json`

表示 decoder 的输出结果。

### `decoder_report.json`

表示 decoder 运行过程的汇总报告，适合快速浏览。

### `logical_error.json`

表示最终的逻辑误差摘要，是最常被直接引用的 QEC 结果文件之一。

## 9. 分析与扩展输出

如果任务目标进一步包含分析分支，还会出现以下文件。

### sensitivity / error budget

- `sensitivity_report.json`
- `error_budget_v2.json`

适合用来查看：

- 参数敏感度
- 误差项排序
- 不同配置之间的趋势比较

### decoder eval

- `decoder_eval_report.json`
- `decoder_eval_table.csv`
- `batch_manifest.json`
- `resume_state.json`
- `failed_tasks.jsonl`

这组文件适合做：

- 多 decoder 比较
- 多 seed 重复评估
- 参数扫描
- 中断后续跑

### Pauli+ / scaling

- `scaling_report.json`
- `error_budget_pauli_plus.json`
- `component_ablation.csv`

这组文件主要服务于更深入的误差预算与缩放分析。

## 10. `decoder_eval` 适合什么时候用

当你满足以下任一需求时，建议打开 decoder eval：

- 比较 `mwpm` 和 `bp`
- 研究 decoder 参数设置
- 比较不同 seeds 下的表现
- 需要批量结果表格输出

如果你只是想先确认主链路是否能产生 logical error，先不要急着打开 `decoder_eval`。

## 11. `resume`、`retries` 和批量评估

decoder eval 相关 feature 中，有几项特别适合大规模实验：

- `eval_parallelism`
- `eval_retries`
- `eval_resume`

使用建议：

- 小规模测试时可以先保持默认
- 大批量扫描时再打开并行和续跑
- 如果担心中途中断，优先保留 `resume_state.json`

## 12. 推荐的上手顺序

如果你第一次使用 QEC 能力，建议按下面顺序逐步增加复杂度：

1. 先用 `trace` 跑通基础仿真
2. 再切到 `logical_error`
3. 确认 `decoder_output.json` 和 `logical_error.json` 能正常生成
4. 再增加 `sensitivity_report`
5. 最后再启用 `decoder_eval` 或 Pauli+ 分支

这样会更容易定位问题，也更符合当前项目的工作流设计。

## 13. 常见问题

### 为什么没有生成 `logical_error.json`

优先检查：

- `target` 是否包含 `logical_error` 或更高层的 QEC 目标
- `solver.run.decoder` 是否已配置

### 为什么 prior / decoder 文件为空或缺失

通常说明本次运行没有真正进入 decode 阶段，或者 target 不包含对应分支。

### 为什么 decoder eval 没有输出表格

优先检查：

- 是否启用了 `decoder_eval_report` 目标或 `decoder_eval` feature
- decode 阶段是否已经成功运行

### 当前能不能做在线实时解码

不能。  
当前项目的定位仍然是离线分析与可复现评估。
