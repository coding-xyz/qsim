# 求解器配置

`solver` 文件描述数值运行方式：使用哪个 engine、哪个 solver mode、什么时间网格、什么参考系。分析选项不再写在 solver 中，而是放进 `analyser` 配置。

## 当前模板

仓库中的主模板包括：

- `templates/solvers/qutip.yaml`
- `templates/solvers/qoptics.yaml`
- `templates/solvers/qtoolbox.yaml`

它们都采用 `schema_version: "3.0"`。

## 最小示例

```yaml
schema_version: "3.0"
backend:
  level: cqed
run:
  engine: qutip
  solver_mode: me
  dt_s: 1.0e-9
  t_end_s: 2.0e-6
  t_padding_s: 0.0
  seed: 12345
  ntraj: 64
frame:
  mode: rotating
  reference: carrier
  rwa: true
study:
  - name: default
    active_components: [q0]
    active_connections: []
    solver_mode: me
    time:
      dt_s: 1.0e-9
      t_end_s: 2.0e-6
      t_padding_s: 0.0
    frame:
      mode: rotating
      reference: carrier
      rwa: true
    options: {}
```

## 顶层结构

- `backend`：请求的模型层级和截断设置
- `run`：engine、solver mode、时间网格和随机种子
- `frame`：默认参考系
- `study`：可选的 step 列表，用来选择组件、连接和局部覆盖运行参数

## engine 与 ModelSpec

`run.engine` 决定实际运行后端：

- `qutip`
- `qoptics`
- `qtoolbox`

在 `ModelSpec` 中，engine 不在顶层，而是记录在 `solver.engine`。这是为了让 `ModelSpec` 保持模型描述能力：同一个模型可以被多个 engine 消费，只有执行时才需要选择后端。

## solver_mode

`run.solver_mode` 和 `study[].solver_mode` 会 lower 到 `SolverSpec.mode`。当前常见值：

- `se`：Schrodinger equation
- `me`：master equation
- `mcwf`：Monte Carlo wave function
- `sme`：stochastic master equation

QuTiP backend 内部按 mode 分派到 `qsim.engines.qutip.modes`。

## study

`study` 描述一组运行 step。常见字段包括：

- `name`
- `active_components`
- `active_connections`
- `solver_mode`
- `time.dt_s`
- `time.t_end_s`
- `time.t_padding_s`
- `frame.mode`
- `frame.reference`
- `frame.rwa`
- `options`

`active_components` 和 `active_connections` 会影响 `SystemSpec.components` / `SystemSpec.connections` 中最终进入模型的子系统。

## QuTiP CQED 读出协议

对 `cqed_jc` / `cqed_dispersive` 且包含 classical `readout_line` 的模型，QuTiP 可通过 `study[].options.readout_protocol` 选择 monitored readout：

- `homodyne_sme`
- `heterodyne_sme`
- `photon_counting_sme` / `photocurrent`
- `classical_readout`

这些值会 lower 到 `ReadoutSpec.protocol`，并由 engine 后端分派。

## 不再属于 solver 的内容

以下内容属于 `analyser.yaml`：

- `trajectory.states`
- `trajectory.save_times`
- `trajectory.save_final_state`
- `trajectory.save_jump_events`
- `trajectory.save_measurement_records`
- `metrics`
- `readout_model`
- `iq_discrimination`
- `report`

## 实用建议

- 从 `templates/solvers/qutip.yaml` 起步最稳妥
- 先只改 `run.engine`、`run.solver_mode`、`dt_s`、`t_end_s`
- 换 engine 时尽量保持 `device`、`pulse` 和 `study` 不变，方便横向对比
