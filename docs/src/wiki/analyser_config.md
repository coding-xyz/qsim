# 分析器配置

`analyser` 文件只负责消费 solver 生成的 raw `trajectory`，并输出所有派生分析结果。

## 最小示例

```yaml
schema_version: "1.0"
trajectory:
  states: density_matrix
  save_times: all
  save_final_state: true
  save_jump_events: false
  save_measurement_records: false
metrics:
  - population
  - mean_excited
  - variance
```

## 顶层结构

当前支持的顶层键包括：

- `schema_version`
- `trajectory`
- `metrics`
- `readout_model`
- `iq_discrimination`
- `noise_analysis`
- `report`

## trajectory

`trajectory` 段决定 solver 需要保留哪些原始时序数据。常见字段包括：

- `states`
- `save_times`
- `save_final_state`
- `save_jump_events`
- `save_measurement_records`

这里描述的是 raw `trajectory` 的保留策略，不是分析结论本身。

## metrics

`metrics` 指定 analyser 要计算的派生量。当前常见的是：

- `population`
- `mean_excited`
- `variance`

## readout_model

`readout_model` 用于描述读出链分析需要的物理通道和导出信号，例如：

- 腔场驱动通道
- 本振通道
- 输入输出关系
- 派生信号列表

## iq_discrimination

`iq_discrimination` 控制 IQ 聚类和判别，例如：

- 是否启用
- 判别方法
- shots 数
- 特征列表
- 输出项

## report

`report` 用于控制报告生成相关开关和输出细节。

## 实用建议

- 从 `templates/analysers/default.yaml` 起步最稳妥
- 先只开 `trajectory + metrics`
- 读出链场景再逐步增加 `readout_model` 和 `iq_discrimination`
- 所有 population / IQ / report 都应放在 `analyser.yaml`，不要回写到 `solver.yaml`
