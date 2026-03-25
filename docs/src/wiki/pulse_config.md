# 脉冲配置

`pulse` 文件定义控制通道、载频、波形模板和逻辑操作到脉冲步骤的映射。当前文档只说明推荐使用的结构化 pulse 写法。

## 最小示例

```yaml
schema_version: "3.0"
pulse:
  channels:
    - name: XY_q0
      kind: drive
      target: q0
      port: drive_port
  carriers:
    XY_q0:
      freq_Hz: 5.0e9
      phase_rad: 0.0
  waveforms:
    x90_drag:
      shape: drag
      duration_ns: 20.0
      sigma_ns: 4.0
      beta: 0.35
  operations:
    x:
      - channel: XY_q0
        waveform: x90_drag
        scale: 2.0
    sx:
      - channel: XY_q0
        waveform: x90_drag
        scale: 1.0
  schedule:
    policy: serial
  acquisition: {}
```

## 顶层结构

当前推荐维护以下键：

- `schema_version`
- `pulse.channels`
- `pulse.carriers`
- `pulse.waveforms`
- `pulse.operations`
- `pulse.schedule`
- `pulse.acquisition`

## channels 与 carriers

- `channels` 定义控制或读出通道
- `kind` 决定通道类别，例如 `drive`、`readout_drive`
- `target` 指向设备中的组件 ID
- `port` 对应设备端口名
- `carriers` 为每个通道提供载频与初相

## waveforms 与 operations

- `waveforms` 定义可复用波形模板
- `operations` 把逻辑门映射到通道和波形
- `x`、`sx` 通常至少要明确给出
- 有读出需求时，建议显式配置 `measure`

## 运行时会提取哪些关键参数

当前运行时会从结构化 pulse 中提取：

- `xy_freq_Hz`
- `ro_freq_Hz`
- `gate_duration_ns`
- `measure_duration_ns`
- `schedule_policy`

## 实用建议

- 从 `templates/pulses/single_qubit.yaml` 起步最稳妥
- 先保证 `x` 和 `sx` 路径完整可解析
- 需要读出时，再补 `readout_drive`、`measure` 和 `acquisition`
