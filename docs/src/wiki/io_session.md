# 文件 IO

`qsim` 会把一次运行的重要输入、中间产物和最终结果写到 `task.output.out_dir`。

## 常见输出

基础运行常见文件包括：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `model_spec.json`
- `trace.h5`
- `settings_report.json`
- `run_manifest.json`

## `artifact_mode`

当前支持两种模式：

- `all`
- `targeted`

其中：

- `all` 尽量保留完整产物
- `targeted` 优先保留本次目标真正依赖的文件

## session 相关字段

`task.output` 里和 session 相关的字段包括：

- `session_dir`
- `session_auto_commit`
- `session_commit_kinds`

只有在 `session_dir` 提供时，session 提交逻辑才有意义。

## 建议

- 做长期实验归档时优先用 `artifact_mode: all`
- 做快速迭代时优先用 `artifact_mode: targeted`
- 如果你需要跨多次运行做结果追踪，建议同时保留 `run_manifest.json`
