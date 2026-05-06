# 文件 IO

`qsim` 会把一次运行的重要输入、中间产物和最终结果写到 `task.output.out_dir`。这些产物用于复现、调试和后续分析。

## 常见输出

基础运行常见文件包括：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `model_spec.json`
- `trajectory.h5`
- `settings_report.json`
- `run_manifest.json`

## model_spec.json

`model_spec.json` 是 engine-neutral 模型快照。它不是后端私有 runtime，也不是一包无 schema 的 payload。主要结构包括：

- `solver`
- `time`
- `frame`
- `system`
- `hamiltonian`
- `noise`
- `readout`
- `analysis_request`
- `study`
- `metadata`

排查模型时，优先查看：

- `system.components`
- `system.connections`
- `hamiltonian.control_terms`
- `hamiltonian.readout_drive_terms`
- `noise.collapse_channels`
- `readout.protocol`
- `solver.mode`
- `solver.engine`

## trajectory.h5

`trajectory.h5` 保存 engine 输出的时间序列、状态摘要、测量记录和 metadata。分析器通常消费这个文件，而不是重新读取原始配置。

## settings_report.json

`settings_report.json` 面向人读，汇总本次运行的配置、模型、runtime 设置和参数映射。它适合放进实验记录或 notebook 附录。

## artifact_mode

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
