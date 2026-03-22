# 设备配置

设备配置文件用于描述设备本身和噪声模型。它会影响编译、lowering、模型构建和求解阶段，是连接“物理对象”和“仿真任务”的关键一层。

## 1. 支持格式

`device` 配置支持：

- `.json`
- `.yaml`
- `.yml`

文档默认使用 `YAML`。

## 2. 顶层结构

设备配置文件顶层必须是一个映射，并且使用以下结构：

```yaml
device: {}
noise: {}
```

也就是说，`device` 和 `noise` 是两个并列段：

- `device`：设备本体参数
- `noise`：噪声模型参数

## 3. 最小示例

当前默认模板类似如下：

```yaml
device: {}
noise:
  model: markovian_lindblad
  T1_s: 5.0e-5
  T2_s: 3.0e-5
```

模板文件位置：

- `src/qsim/workflow/templates/device/transmon_default.yaml`
- `src/qsim/workflow/templates/device/low_noise_lab.yaml`

## 4. `device` 段的作用

`device` 段描述器件本身的参数，它们会进入 workflow 运行态的 `task.input.device`，并参与：

- 编译
- lowering
- 模型构建
- 部分调度与控制相关逻辑

在当前代码实现中，`device` 常见可承担以下内容：

- `simulation_level`
- qubit 频率
- 非谐性
- 耦合参数
- reset / readout 相关设备参数

### `simulation_level`

这个字段用于指定仿真层级。  
如果没有显式给出，运行时会尝试从 solver 的 backend level 中补出默认值。

### `qubits`

如果 `device` 里有 `qubits` 列表，代码会尝试把它规范化成统一字段集合。  
例如，它可以派生出：

- `qubit_freqs_Hz`
- `anharmonicity_Hz`
- `T1_s`
- `T2_s`
- `Tphi_s`
- `gamma1_Hz`
- `gamma_phi_Hz`
- `gamma_up_Hz`

这意味着，如果你的设备参数更适合按“每个 qubit 一个对象”的方式记录，也可以这样组织。

## 5. `noise` 段的作用

`noise` 段用于描述本次仿真采用的噪声模型。  
这些参数会进一步影响 backend config 归一化和求解器阶段的行为。

当前实现中，常见噪声模式包括：

- `markovian_lindblad`
- `sde`
- `tls`
- `hybrid`
- `deterministic`

如果 `model` 名称中包含 `lindblad`，内部会把它归到 Lindblad 路径。

## 6. 应该把哪些内容写在 `device`，哪些写在 `pulse`

可以按下面的原则区分：

写在 `device`：

- 设备固有参数
- qubit/cavity/耦合相关参数
- 噪声模型与退相干参数

写在 `pulse`：

- 门时长
- XY/RO 载频
- readout 脉冲参数
- reset 脉冲参数

如果一个参数更像“器件物理属性”，放在 `device`。  
如果一个参数更像“脉冲驱动策略”，放在 `pulse`。

## 7. 推荐写法

如果你只是想先跑通单比特或简单多比特仿真，建议从较简洁的设备配置开始：

```yaml
device:
  simulation_level: qubit
noise:
  model: markovian_lindblad
  T1_s: 5.0e-5
  T2_s: 3.0e-5
```

如果后续要增加更细的设备结构，再逐步加入：

- `qubits`
- `couplings`
- `anharmonicity_Hz`
- 更细的 reset / readout 设备参数

## 8. 常见错误

### 把脉冲参数写进 `device`

比如把 `gate_duration_ns`、`xy_freq_Hz` 一类参数全部写在 `device` 里。  
从职责划分上说，更推荐把这类字段放进 `pulse` 配置。

### 把任务相关字段写进 `device`

例如把 `target`、`out_dir`、`decoder` 之类内容写进设备文件。  
这些字段不属于设备配置。

### 使用旧命名 `hardware_config`

当前外部接口命名统一为 `device_config`。  
如果你在旧文件中看到 `hardware` 相关说法，应理解为历史命名，而当前文档和调用接口都以 `device` 为准。

## 9. 什么时候需要单独准备多个设备文件

以下情况建议分出多份 `device.yaml`：

- 想比较不同噪声水平
- 想比较不同器件参数
- 想分别保存“理想设备”和“实验设备”版本
- 想针对不同实验任务使用不同硬件假设

这样在任务切换时只需要改 `device_config` 路径，而不需要改动整份任务文件。
