# 任务配置

任务配置文件是整条 workflow 的入口文件。它决定本次运行的任务目标、输入电路、关联的其他配置文件、输出目录以及可选功能开关。对于使用者来说，`task.yaml` 是最先接触、也最常修改的一类配置。

## 1. 支持格式

`task` 配置支持：

- `.json`
- `.yaml`
- `.yml`

仓库文档默认使用 `YAML`。

## 2. 顶层结构

一个完整的任务配置通常长这样：

```yaml
schema_version: "1.0"
target:
  - logical_error
  - sensitivity_report
template: full
input:
  qasm_path: examples/bell.qasm
  solver_config: solvers/qutip_default.yaml
  device_config: device/transmon_default.yaml
  pulse_config: pulses/single_qubit_default.yaml
  param_bindings: {}
features:
  decoder_eval: false
  pauli_plus_analysis: false
output:
  out_dir: runs/demo_full
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: true
  export_dxf: false
  session_auto_commit: false
tags:
  - demo
```

当前允许的顶层键包括：

- `schema_version`
- `target`
- `targets`
- `input`
- `features`
- `output`
- `tags`
- `template`

如果写入未支持的键，加载阶段会直接报错。

## 3. `target` 和 `targets`

`target` 用来描述本次运行到底要得到什么结果。它既可以是单个字符串，也可以是字符串列表。

示例一，单目标：

```yaml
target: trace
```

示例二，多目标：

```yaml
target:
  - logical_error
  - sensitivity_report
```

当前常见目标包括：

- `trace`
- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`
- `cross_engine_compare`

使用建议：

- 首次验证链路时用 `trace`
- 需要解码结果时用 `logical_error`
- 需要误差分析时加上 `sensitivity_report`
- 需要批量 decoder 评估时用 `decoder_eval_report`

## 4. `template`

`template` 是执行计划的预设名称。代码中内置了若干模板，例如：

- `simulate`
- `simulate_qec`
- `full`
- `full_eval`

如果同时提供了 `template` 和显式的 `target`，实际执行将优先使用你明确写出的目标集合。  
在日常使用中，如果你已经明确写好了 `target`，可以把 `template` 当作辅助说明；如果只是想快速套一个预设流程，也可以只写 `template`。

## 5. `input`

`input` 段负责描述输入电路以及其余配置文件的位置。

当前支持字段：

- `qasm_text`
- `qasm_path`
- `solver_config`
- `device_config`
- `pulse_config`
- `param_bindings`

### `qasm_text` 和 `qasm_path`

这两个字段必须二选一：

- `qasm_text`：直接把 OpenQASM 文本写在配置中
- `qasm_path`：从外部文件读取 OpenQASM

通常更推荐 `qasm_path`，因为：

- 电路内容更长时更容易维护
- 适合版本管理
- 便于多个任务复用同一个电路文件

### `solver_config`

指定求解器配置文件路径。  
如果命令行或 Python 参数没有单独覆盖，那么这个字段是必填的。

### `device_config`

指定设备配置文件路径。  
和 `solver_config` 一样，如果调用时没有单独覆盖，那么它也是必填的。

### `pulse_config`

指定脉冲配置文件路径。  
这个字段是可选的，但对于大多数包含脉冲参数的实际任务，建议明确填写。

### `param_bindings`

用于给参数化电路提供参数绑定值。  
如果当前电路没有参数化输入，这个字段可以省略或写成空映射。

## 6. `features`

`features` 用于打开一些附加功能分支。它本身不是任务目标，而是针对已有目标的额外运行控制。

当前支持字段：

- `pauli_plus_analysis`
- `pauli_plus_code_distances`
- `pauli_plus_shots`
- `decoder_eval`
- `eval_decoders`
- `eval_seeds`
- `eval_option_grid`
- `eval_parallelism`
- `eval_retries`
- `eval_resume`

使用时要注意一点：并不是所有 `target` 都允许任意 feature。  
例如：

- `trace` 不接受额外 feature
- `decoder_eval_report` 相关 feature 只适合解码评估类目标
- `pauli_plus_analysis` 相关 feature 只适合 Pauli+ 分析类目标

如果 feature 与 target 不匹配，加载阶段会报错。

## 7. `output`

`output` 段负责控制结果写出方式。

当前支持字段：

- `out_dir`
- `persist_artifacts`
- `artifact_mode`
- `export_dxf`
- `export_plots`
- `session_dir`
- `session_auto_commit`
- `session_commit_kinds`

### `out_dir`

输出目录，必填。  
所有运行产物都会写到这里。

### `persist_artifacts`

是否把产物写入磁盘。  
通常建议保持为 `true`，便于追踪和复现。

### `artifact_mode`

当前支持：

- `all`
- `targeted`

含义可以理解为：

- `all`：尽可能写出完整产物
- `targeted`：优先写出本次目标真正相关的产物

如果你想做长期归档，`all` 更稳妥。  
如果你只想保留关键输出、减少文件数量，`targeted` 更适合。

### `export_plots`

控制是否导出图像，例如 pulse timing 图、trace 图、report 图。

### `export_dxf`

控制是否导出 DXF。  
如果不开这个功能，即使安装了 `ezdxf` 依赖，也不会自动生成 DXF 文件。

### `session_dir` 和 `session_auto_commit`

这两个字段配合使用：

- `session_dir`：指定 session 存储目录
- `session_auto_commit`：是否在运行结束后自动提交结果

只有当两者同时设置好时，session 自动提交才会发生。

### `session_commit_kinds`

用于限制提交到 session 的结果类别。  
如果不写，则使用 workflow 中的默认类别集合。

## 8. `tags`

`tags` 是附加标签列表，用于记录任务来源、用途或分组信息。  
它不会直接改变求解行为，但对后续整理任务和筛选结果很有帮助。

例如：

```yaml
tags:
  - demo
  - qutip
  - low-noise
```

## 9. 推荐写法

对于一般用户，推荐从下面这种简洁版本开始：

```yaml
target: trace
input:
  qasm_path: examples/bell.qasm
  solver_config: solvers/qutip_default.yaml
  device_config: device/transmon_default.yaml
  pulse_config: pulses/single_qubit_default.yaml
output:
  out_dir: runs/trace_demo
  persist_artifacts: true
  artifact_mode: targeted
  export_plots: true
  export_dxf: false
```

在这个基础上，再逐步增加：

- `features`
- `session_*`
- 多个 `target`
- `param_bindings`

## 10. 常见错误

### 同时写了 `qasm_text` 和 `qasm_path`

这是不允许的，二者必须二选一。

### 没有写 `out_dir`

这是必须项，缺失时任务无法写出结果。

### `trace` 目标却开启了解码分析 feature

这种组合会被校验拒绝，因为 feature 和 target 不匹配。

### 忘记写 `solver_config` 或 `device_config`

如果调用时没有通过命令行或 Python 参数覆盖，这两个字段必须在 `task` 配置中给出。

## 11. 运行时它会发生什么

当你执行：

```bash
qsim run-task --task-config task.yaml
```

内部会经历以下步骤：

1. 读取 `task.yaml`
2. 校验字段是否在支持列表中
3. 解析 `target` 和 `features`
4. 根据 `input` 段找到 `solver/device/pulse` 文件
5. 合成为一个统一的 `WorkflowTask`
6. 交给执行计划和主 pipeline 运行
