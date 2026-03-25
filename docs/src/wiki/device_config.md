# 设备配置

`device` 文件描述设备结构、组件参数和噪声模型。当前文档只说明推荐使用的组件化设备写法。

## 最小示例

```yaml
schema_version: "3.0"
device:
  components:
    - id: q0
      type: transmon
      representation: quantum
      role: coupled
      basis:
        kind: nlevel
        levels: 3
      ports:
        drive: drive_port
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

## 顶层结构

当前推荐维护以下键：

- `schema_version`
- `device.components`
- `device.connections`
- `device.parameters`
- `device.noise`

## components

`components` 是设备文件的核心。常见字段包括：

- `id`：组件唯一标识
- `type`：例如 `transmon`、`resonator`
- `representation`：当前模板常用 `quantum`
- `role`：组件在系统中的角色
- `basis.kind`：常见为 `nlevel`
- `basis.levels`：截断能级数
- `ports`：逻辑端口名
- `parameters`：频率、非谐性等物理参数
- `noise`：局域退相干参数

## connections

`connections` 用来表达组件间耦合关系。单比特模板可以先留空；多组件设备再补充连接项。

## 运行时会自动提取什么

当前加载器会从组件化结构中自动提取：

- 量子比特列表
- `qubit_freqs_Hz`
- `anharmonicity_Hz`
- `T1_s`、`T2_s`、`Tphi_s`
- `simulation_level`

## 实用建议

- 从 `templates/devices/single_qubit.yaml` 起步最稳妥
- 先把 `components` 写完整，再补 `connections`
- 频率、非谐性和退相干参数优先显式写在组件上
