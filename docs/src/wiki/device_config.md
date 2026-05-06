# 设备配置

`device` 文件描述硬件组件、组件间连接和噪声参数。当前推荐把设备写成 `components + connections`，这会直接 lower 到 `SystemSpec.components` 和 `SystemSpec.connections`。

## 最小单比特示例

```yaml
schema_version: "3.0"
device:
  components:
    - id: q0
      type: transmon
      representation: quantum
      basis:
        kind: nlevel
        levels: 3
      parameters:
        freq_Hz: 5.0e9
        anharmonicity_Hz: -2.0e8
      noise:
        T1_s: 120.0e-6
        T2_s: 90.0e-6
  connections: []
  parameters: {}
  noise: {}
```

## CQED 读出示例

```yaml
schema_version: "3.0"
device:
  components:
    - id: q0
      type: transmon
      representation: quantum
      basis: {kind: nlevel, levels: 3}
      parameters:
        freq_Hz: 5.0e9
        anharmonicity_Hz: -2.0e8

    - id: r0
      type: resonator
      representation: quantum
      basis: {kind: fock, nmax: 8}
      parameters:
        freq_Hz: 6.8e9
        kappa_int_Hz: 0.2e6
        kappa_ext_Hz: 7.0e6
        chi_Hz: -1.2e6

    - id: ro0
      type: readout_line
      representation: classical
      parameters:
        eta_chain: 0.45
        gain_dB: 20.0
        added_noise_photons: 8.0
        center_freq_Hz: 6.8e9
        bandwidth_Hz: 25.0e6

  connections:
    - id: q0_r0
      type: dispersive
      a: q0
      b: r0
      parameters:
        chi_Hz: -1.2e6
        g_Hz: 80.0e6

    - id: r0_ro0
      type: readout_feedline
      a: r0
      b: ro0
      parameters:
        kappa_ext_Hz: 7.0e6
        eta_chain: 0.45
        bandwidth_Hz: 25.0e6
```

## components

常见组件类型：

- `transmon`
- `resonator` / `cavity`
- `readout_line`

通用字段：

- `id`：组件唯一标识
- `type`：组件类型
- `representation`：`quantum`、`classical` 或 `disabled`
- `description`：可选说明
- `basis`：截断基信息，例如 `levels` 或 `nmax`
- `parameters`：频率、耦合、读出链参数等
- `noise`：局域噪声参数

lowering 后，组件会变成：

- `TransmonComponentSpec`
- `ResonatorComponentSpec`
- `ReadoutLineComponentSpec`

## connections

常见连接类型：

- `jc`
- `dispersive`
- `readout_feedline`
- `zz`

通用字段：

- `id`
- `type`
- `a`
- `b`
- `via`
- `parameters`

lowering 后，连接会变成：

- `JCConnectionSpec`
- `DispersiveConnectionSpec`
- `ReadoutFeedlineConnectionSpec`
- `ZZConnectionSpec`

## 与 ModelSpec 的关系

设备配置中的 `components` 和 `connections` 是 `SystemSpec` 的主要来源。当前 `SystemSpec` 不保留额外 `graph` 层，也不保留重复的 `component_summary`。

```text
SystemSpec
  components
  connections
  structure
  assumptions
```

`structure` 记录 study 选择后的模型结构摘要，例如 qubit/cavity/feedline 的表示方式和耦合类型。

## 实用建议

- 从 `templates/devices/single_qubit.yaml` 或已有 CQED 模板复制起步
- 优先把硬件事实写在组件和连接上
- 不要为了统计数量手写 summary；需要数量时由代码从 `components` 推导
- `representation: disabled` 可用于暂时排除组件
