# 量子纠错

`qsim` 的 QEC 相关能力主要用于离线分析与结果汇总，包括：

- logical error
- decoder eval
- scaling
- error budget Pauli+
- component ablation

## 什么时候会进入这类流程

当 `task.target` 选择以下目标时，会进入对应分析阶段：

- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`
- `cross_engine_compare`

## 结果产物

这类任务常见输出包括：

- `logical_error.json`
- `decoder_eval_report.json`
- `scaling_report.json`
- `error_budget_pauli_plus.json`
- `component_ablation.csv`

## 使用建议

- 先把 `trace` 跑通，再增加 QEC 相关目标
- 先确认 `trace.h5`、`model_spec.json` 和 `settings_report.json` 已正常生成
- 做多目标任务时，优先保持 `task / solver / device / pulse` 四份配置结构稳定
