# 任务配置

`task` 文件是一次 workflow 运行的入口。它决定这次任务的目标、输入电路、引用哪些 `solver/device/pulse` 文件，以及结果写到哪里。

## 当前推荐写法

`task` 层目前仍推荐使用扁平结构，而不是嵌套 `task:`。

推荐示例：

```yaml
schema_version: "3.0"
target: trajectory
input:
  qasm_text: |
    OPENQASM 3;
    include "stdgates.inc";
    qubit[1] q;
    bit[1] c;
    x q[0];
    measure q[0] -> c[0];
  solver_config: ../../../templates/solvers/qutip.yaml
  device_config: ../../../templates/devices/single_qubit.yaml
  pulse_config: ../../../templates/pulses/single_qubit.yaml
  param_bindings: {}
features: {}
output:
  out_dir: ../runs/task1_single_qubit
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: false
  export_dxf: false
tags: [task1]
```

## 支持的顶层键

当前加载器接受的顶层键包括：

- `schema_version`
- `target`
- `targets`
- `input`
- `features`
- `output`
- `tags`
- `template`
- `task`

其中真正推荐日常使用的是：

- `target` 或 `targets`
- `input`
- `features`
- `output`
- `tags`

## 关于嵌套 `task:`

加载器当前会识别顶层 `task:`，但它只覆盖一个受限子集，不适合作为复杂任务的主入口。因此当前最稳妥的建议仍然是：

> `task` 文件继续使用扁平写法。


