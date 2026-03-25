# qsim

`qsim` 是一个面向量子电路仿真、脉冲建模和离线分析的 workflow-first 工具。它把一次运行拆成清晰的配置文件、标准化的中间产物和可复现的输出目录，方便做参数对比、结果归档和后续分析。

## 当前配置体系

仓库当前对外推荐的组织方式是四类配置文件：

- `task`
- `solver`
- `device`
- `pulse`

当前推荐在配置文件中统一写 `schema_version: "3.0"`。

具体说明直接看对应页面：

- [任务配置](wiki/workflow_task_config.md)
- [设备配置](wiki/device_config.md)
- [脉冲配置](wiki/pulse_config.md)
- [求解器配置](wiki/solver_config.md)

## 快速开始

仓库里已经有一套最小可运行示例，可以直接启动：

```bash
qsim run-task --task-config examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml
```

这份任务会引用以下三个示例配置：

- `templates/solvers/qutip.yaml`
- `templates/devices/single_qubit.yaml`
- `templates/pulses/single_qubit.yaml`

如果你想自己起步，通常只需要复制四份文件并改路径：

- `examples/noise_simulation_tests/required_tasks/task1_single_qubit.yaml`
- `templates/solvers/qutip.yaml`
- `templates/devices/single_qubit.yaml`
- `templates/pulses/single_qubit.yaml`

## 推荐阅读顺序

1. [概览](wiki/overview.md)
2. [基本用法](wiki/basic_usage.md)
3. [任务配置](wiki/workflow_task_config.md)
4. [设备配置](wiki/device_config.md)
5. [脉冲配置](wiki/pulse_config.md)
6. [求解器配置](wiki/solver_config.md)
7. [可视化](wiki/visualization.md)
8. [量子纠错](wiki/qec_analysis.md)
9. [文件 IO](wiki/io_session.md)

## 文档维护

- 文档源文件位于 `docs/src/`
- 生成站点位于 `docs/site/`
- 本地预览使用 `mkdocs serve`
- 重新构建使用 `mkdocs build --clean`

请不要手改 `docs/site/` 下的生成内容。
