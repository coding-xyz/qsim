# 求解器配置

求解器配置文件用于描述求解引擎、运行参数、模型层级和参考系设置。它决定“同一个任务和同一个设备参数，究竟以什么方式求解”，因此是实验对比中最常切换的一类配置。

## 1. 支持格式

`solver` 配置支持：

- `.json`
- `.yaml`
- `.yml`

文档默认使用 `YAML`。

## 2. 顶层结构

求解器配置文件顶层必须采用以下结构：

```yaml
backend: {}
run: {}
frame: {}
```

这三个部分分别负责：

- `backend`：模型级别和后端分析配置
- `run`：引擎与运行时选项
- `frame`：参考系与 RWA 设置

## 3. 最小示例

默认模板大致如下：

```yaml
backend:
  level: qubit
  analysis_pipeline: default
  truncation: {}
run:
  engine: qutip
  solver_mode: me
  sweep: []
  seed: 1234
  dt_s: 1.0e-9
  schedule_policy: serial
  reset_feedback_policy: parallel
frame:
  mode: rotating
  reference: pulse_carrier
  rwa: true
```

模板文件：

- `src/qsim/workflow/templates/solvers/qutip_default.yaml`
- `src/qsim/workflow/templates/solvers/julia_qoptics.yaml`
- `src/qsim/workflow/templates/solvers/julia_qtoolbox.yaml`

## 4. `backend` 段说明

`backend` 用于描述求解所需的模型层级与后端分析设置。

### `level`

表示模型层级。  
当前常见起步值是：

- `qubit`

它会进一步影响运行时 `simulation_level` 和 backend config 的构造方式。

### `analysis_pipeline`

表示分析流水线名称。  
如果你没有特别自定义分析路径，通常保持 `default` 即可。

### `truncation`

用于记录与截断或多能级模型有关的参数。  
如果当前任务只做比较基础的 qubit 级仿真，可以先保持为空映射。

## 5. `run` 段说明

`run` 是求解器配置里最核心的一段，它决定真正的运行方式。

当前常见字段包括：

- `engine`
- `solver_mode`
- `sweep`
- `seed`
- `dt_s`
- `t_end_s`
- `t_padding_s`
- `schedule_policy`
- `reset_feedback_policy`
- `compare_engines`
- `allow_mock_fallback`
- `mcwf_ntraj`
- `prior_backend`
- `decoder`
- `decoder_options`
- `qec_engine`

### `engine`

表示使用哪个求解引擎。  
当前支持：

- `qutip`
- `qoptics`
- `qtoolbox`

如果你只是第一次跑通流程，建议先从 `qutip` 开始。

### `solver_mode`

表示求解器模式，例如主方程等。  
在现有模板中，常见值是：

- `me`

### `seed`

用于控制随机性。  
如果你在做对比实验，建议显式固定这个值，便于复现。

### `dt_s`

时间步长，单位为秒。  
这个字段直接影响时间分辨率和仿真成本，因此通常需要根据任务规模谨慎调整。

### `t_end_s` 和 `t_padding_s`

这两个字段用于更细地控制仿真时间范围。  
如果没有特殊需求，可以先不写，沿用默认行为。

### `schedule_policy`

控制调度策略。  
默认模板中常见值是：

- `serial`

### `reset_feedback_policy`

控制 reset 反馈相关策略。  
默认模板中常见值是：

- `parallel`

### `compare_engines`

用于 cross-engine compare 任务。  
如果你希望对同一个模型比较多个引擎，这里应给出比较目标。

### `allow_mock_fallback`

在某些依赖不可用或引擎不可运行时，是否允许回退到 mock 路径。

### `mcwf_ntraj`

与 MCWF 相关的轨迹数设置。  
如果你的运行不涉及相关模式，可以先保持默认。

### `prior_backend`

用于量子纠错分析中 prior 的构建来源，例如：

- `auto`
- `stim`
- `cirq`
- `mock`

### `decoder`

指定使用哪个 decoder。  
当你的任务目标涉及：

- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`

这类 target 时，`decoder` 通常必须配置。

### `decoder_options`

为 decoder 提供更细的选项，例如 BP 的迭代次数、阻尼等。

### `qec_engine`

控制 QEC 分析使用的引擎来源，常见写法是 `auto`。

## 6. Julia 相关字段

当 `engine` 取值为：

- `qoptics`
- `qtoolbox`

时，还可以使用 Julia 相关字段：

- `julia_bin`
- `julia_depot_path`
- `julia_timeout_s`

如果当前 `engine` 是 `qutip`，这些 Julia 专属字段不应写入，否则校验会报错。

## 7. `frame` 段说明

`frame` 用于控制参考系和旋波近似。

当前支持字段：

- `mode`
- `reference`
- `rwa`
- `qubit_reference_freqs_Hz`

### `mode`

常见值是：

- `rotating`

### `reference`

用于指定参考频率的来源。  
模板中常见值为：

- `pulse_carrier`

### `rwa`

是否启用旋波近似。  
在多数基础任务中，默认值通常可以直接使用。

### `qubit_reference_freqs_Hz`

如果你需要显式指定每个 qubit 的参考频率，可以在这里给出。

## 8. 不同目标对 `run` 的要求

从执行计划规则来看，不同 target 对 `run` 字段的要求并不相同。

### 不要求 decoder 的目标

- `trace`

### 要求 `run.decoder` 的目标

- `logical_error`
- `sensitivity_report`
- `decoder_eval_report`
- `scaling_report`
- `error_budget_pauli_plus`

### 要求 `run.compare_engines` 的目标

- `cross_engine_compare`

因此，在写 solver 配置前，最好先确认你的 `task.target` 究竟是什么。

## 9. 推荐写法

第一次上手建议先使用比较朴素的配置：

```yaml
backend:
  level: qubit
  analysis_pipeline: default
  truncation: {}
run:
  engine: qutip
  solver_mode: me
  seed: 1234
  dt_s: 1.0e-9
  schedule_policy: serial
  reset_feedback_policy: parallel
frame:
  mode: rotating
  reference: pulse_carrier
  rwa: true
```

在此基础上，再逐步增加：

- `decoder`
- `decoder_options`
- `compare_engines`
- Julia 相关字段

## 10. 常见错误

### `engine=qutip` 却写了 Julia 字段

这是不允许的，校验阶段就会报错。

### 需要 QEC 结果却没有配置 `decoder`

如果目标涉及逻辑误差或解码分析，通常必须设置 `run.decoder`。

### 把噪声参数写进 solver 配置

噪声应放在 `device` 配置中，而不是 `solver`。

### 把输出参数写进 solver 配置

例如 `out_dir`、`export_plots` 一类内容属于 `task.output`，不属于 `solver`。
