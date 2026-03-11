# IO 与会话

`run_task_files(task, solver, hardware)` 与 CLI `qsim run-task --task-config ... --solver-config ... --hardware-config ...` 的产物一致。

## 常见产物

- `circuit.json`
- `backend_config.json`
- `pulse_ir.json`
- `model_spec.json`
- `trace.h5`
- `logical_error.json`（按 target）
- `sensitivity_report.json`（按 target）
- `settings_report.json`
- `run_manifest.json`
- `timings.json`

启用图形导出时还会生成 `trace.png`、`report.png`、`pulse_timing.png`、`timing_diagram.dxf` 等。

## `trace.h5`

`trace.h5` 保存求解输出的时间轴与状态采样：

- dataset: `times`
- dataset: `states`
- attrs: `engine`, `state_encoding`, `num_qubits`, `model_dimension`

## Manifest

`run_manifest.json` 记录：

- 输入摘要（qasm 摘要、solver 配置来源）
- 产物映射（逻辑产物名 -> 相对路径）
- 依赖版本与指纹

## Session 自动提交

当 `task.output.session_auto_commit=true` 且设置 `task.output.session_dir` 时：

- 运行结束后自动把选定结果提交到 session
- 在 run 输出目录写 `session_commit_report.json`

可通过 `task.output.session_commit_kinds` 限制提交类别。
