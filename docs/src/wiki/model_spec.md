# ModelSpec IR

`ModelSpec` 是 qsim 当前的 engine-neutral simulation IR。它描述“要模拟的模型”，而不是某个后端的私有运行对象。

一次标准运行中，配置会先被标准化并 lower 成：

```text
CircuitIR -> PulseIR -> ExecutableModel -> ModelSpec -> engine runtime -> Trajectory
```

其中 `ModelSpec` 是 backend 和 engine 之间的边界：backend 负责把配置、设备、脉冲和噪声整理成结构化 IR；QuTiP、qoptics、qtoolbox 等 engine 再把这个 IR 转成自己的运行对象。

## 顶层结构

当前 `ModelSpec` 顶层字段是：

```text
ModelSpec
  circuit
  solver
  time
  frame
  system
  hamiltonian
  noise
  readout
  analysis_request
  study
  metadata
```

注意：`ModelSpec` 顶层不保存 `engine`。模型本身应该可被多个 engine 消费；真正选择运行后端时才使用 `solver.engine` 或 workflow 的 `run.engine`。

## solver / time / frame

`solver` 只描述数值求解请求：

```text
SolverSpec
  mode
  engine
  seed
  ntraj
  options
```

`engine` 是可选执行选择，通常来自 `solver.yaml` 的 `run.engine`。如果只是保存通用模型或做静态检查，它可以为空。

`time` 保存时间网格：

```text
TimeSpec
  dt_s
  t_end_s
  t_padding_s
```

`frame` 保存参考系和 RWA 语义：

```text
FrameSpec
  mode
  reference
  rwa
  qubit_reference_freqs_Hz
  qubit_reference_omega_rad_s
  pulse_carrier_reference_freqs_Hz
  pulse_carrier_reference_omega_rad_s
```

## system

`system` 直接保存硬件/模型结构，不再额外包一层 `graph`，也不保留重复的 `component_summary`。

```text
SystemSpec
  model_type
  simulation_level
  dimension
  components
  connections
  structure
  assumptions
```

`components` 的常见具体类型包括：

- `TransmonComponentSpec`
- `ResonatorComponentSpec`
- `ReadoutLineComponentSpec`

`connections` 的常见具体类型包括：

- `JCConnectionSpec`
- `DispersiveConnectionSpec`
- `ReadoutFeedlineConnectionSpec`
- `ZZConnectionSpec`

老式的 qubit/cavity/coupling summary 只作为构造入口的兼容数据使用；新的主结构以 `components` 和 `connections` 为准。

## hamiltonian

`HamiltonianSpec` 把静态项、耦合项、控制脉冲和读出 drive 分开：

```text
HamiltonianSpec
  static_terms
  coupling_terms
  control_terms
  readout_drive_terms
```

采样脉冲通过 `SignalSpec` 表达，包含 `times_s`、`values`、插值方式、scale 和可选 carrier。engine 不需要再从大 dict 里猜 control 字段含义。

## noise

`NoiseSpec` 保存已经 lower 好的噪声结构：

```text
NoiseSpec
  selected_model
  readout_error
  collapse_channels
  stochastic_channels
  per_qubit_rates
  supported
  unsupported
  warnings
```

Markovian collapse、1/f 和 OU 随机噪声都在这里显式表达。

## readout

`ReadoutSpec` 是读出协议的单一入口：

```text
ReadoutSpec
  protocol
  update_mode
  subsystem_model
  chain
  controls
  lines
  reset_events
```

QuTiP 的 homodyne、heterodyne、photon-counting SME 和 classical readout 都从 `readout.protocol` 分派，不再依赖一组分散的 `use_*` 布尔字段。

## 文件产物

运行时 `model_spec.json` 会直接展示上述结构。读它时建议先看：

1. `system.components` / `system.connections`
2. `hamiltonian.control_terms` / `hamiltonian.readout_drive_terms`
3. `noise.collapse_channels`
4. `readout.protocol` / `readout.chain`
5. `solver.mode` / `solver.engine`

这几个字段通常能解释一次仿真的物理模型、数值求解方式和读出路径。
