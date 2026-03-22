# 脉冲配置

脉冲配置文件用于描述门和读出相关的脉冲参数。它影响 lowering 结果、PulseIR 生成、时序图导出以及部分 reset / readout 行为，是“从逻辑门到控制脉冲”的关键配置层。

## 1. 支持格式

`pulse` 配置支持：

- `.json`
- `.yaml`
- `.yml`

文档默认使用 `YAML`。

## 2. 顶层结构

脉冲配置文件顶层结构必须为：

```yaml
pulse: {}
```

读取后，这个 `pulse` 段会被合并到运行态的设备配置中，最终参与：

- lowering
- pulse sequence 生成
- PulseIR 输出
- 时序图和 DXF 导出

## 3. 最小示例

默认模板大致如下：

```yaml
pulse:
  gate_duration_ns: 20.0
  xy_freq_Hz: 5000000000.0
  ro_freq_Hz: 6500000000.0
```

模板文件：

- `src/qsim/workflow/templates/pulses/single_qubit_default.yaml`

## 4. 常见参数分组

从 `src/qsim/pulse/catalog.py` 可以看出，当前代码会读取多类脉冲参数。为了更容易理解，可以把它们分成以下几组。

### 门时长与载频

- `gate_duration_ns`
- `xy_freq_Hz`
- `ro_freq_Hz`

这几项通常是最基础的起步参数。  
如果你只是想先让单比特门和读出脉冲顺利生成，通常先给这组字段就够了。

### 波形边缘与读出参数

- `rect_edge_ns`
- `measure_duration_ns`
- `readout_edge_ns`

这些字段影响读出脉冲或矩形包络相关的时间结构。

### reset 相关参数

- `reset_measure_duration_ns`
- `reset_measure_amp`
- `reset_deplete_duration_ns`
- `reset_deplete_amp`
- `reset_latency_duration_ns`
- `reset_pi_duration_ns`
- `reset_pi_amp`
- `reset_cond_on`

这些字段主要在 reset 相关 lowering 逻辑中发挥作用，适合在你明确要研究 reset 行为时再逐步补充。

## 5. 它在 workflow 里的位置

一次运行中，脉冲配置大致按下面顺序生效：

1. `task.input.pulse_config` 指向脉冲配置文件
2. `load_pulse_config_file()` 读取该文件
3. 读取结果被合并到 device 配置的 `pulse` 字段
4. `backend.lowering` 和 `pulse.sequence` 使用这些参数生成 `PulseIR`
5. `pulse.visualize` 根据 `PulseIR` 和脉冲元数据导出图像

因此，`pulse` 配置并不是孤立存在的，它实际处在“配置输入 -> lowering -> PulseIR -> 可视化”这条链上。

## 6. 推荐起步写法

如果你是第一次编写 `pulse.yaml`，建议从最小版本开始：

```yaml
pulse:
  gate_duration_ns: 20.0
  xy_freq_Hz: 5.0e9
  ro_freq_Hz: 6.5e9
```

然后根据需要逐步增加：

- 读出持续时间
- 波形边缘时间
- reset 相关参数

这种渐进式写法有两个优点：

- 更容易定位是哪一组参数影响了结果
- 更容易比较不同 pulse 设置对输出图和 trace 的影响

## 7. 什么时候应该单独拆出 `pulse.yaml`

如果你满足以下任一情况，建议明确使用独立的脉冲配置文件：

- 经常调整门时长
- 经常比较不同 readout 设置
- 想测试 reset 策略
- 想对比不同脉冲时序图

如果你几乎不改 pulse 参数，也可以先只使用默认模板。

## 8. `pulse` 和 `device` 的分工

最容易混淆的地方是：有些字段看起来都像“硬件参数”，但职责并不相同。

推荐的划分方式如下：

`device` 更适合放：

- 设备结构参数
- qubit 属性
- 噪声模型
- 系统级物理参数

`pulse` 更适合放：

- 门时间
- 脉冲载频
- 读出时间
- reset 脉冲细节

如果一个参数更接近“控制波形怎么打”，就更适合放在 `pulse`。

## 9. 常见错误

### 脉冲配置文件顶层不是 `pulse`

正确写法是：

```yaml
pulse:
  gate_duration_ns: 20.0
```

不是直接把字段裸写在文件顶层。

### 误以为 `pulse.yaml` 会单独运行

不会。  
`pulse` 配置始终是 task workflow 的一部分，需要通过 `task.yaml` 或命令行传给 `qsim run-task`。

### 一开始就把所有 reset 字段写满

不建议。  
更推荐先用最小脉冲配置把主链路跑通，再逐步增加复杂参数。
