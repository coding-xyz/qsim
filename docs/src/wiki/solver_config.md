# 求解器配置

`solver` 文件只决定数值引擎、时间步长、参考系和数值运行参数。所有派生分析都已经迁移到独立的 `analyser` 配置。

## 当前模板

仓库中的主模板包括：

- `templates/solvers/qutip.yaml`
- `templates/solvers/qoptics.yaml`
- `templates/solvers/qtoolbox.yaml`

它们都采用同一套结构化组织方式。

## 最小示例

```yaml
schema_version: "3.0"
backend:
  level: full
run:
  engine: qutip
  solver_mode: me
  dt_s: 1.0e-9
  t_end_s: 50.0e-6
  t_padding_s: 0.0
frame:
  mode: rotating
  reference: carrier
  rwa: true
study:
  - name: control_dynamics
    active_components: [q0]
    active_connections: []
    solver_mode: me
    time:
      dt_s: 1.0e-9
      t_end_s: 50.0e-6
      t_padding_s: 0.0
    frame:
      mode: rotating
      reference: carrier
      rwa: true
    options: {}
```

## 顶层结构

当前推荐维护以下键：

- `schema_version`
- `backend`
- `run`
- `frame`
- `study`

## engine

`engine` 决定使用哪一个求解后端。当前模板中常见的是：

- `qutip`
- `qoptics`
- `qtoolbox`

## study

`study` 描述一次求解实验的主要数值设置。常见字段包括：

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

## QuTiP CQED 读出协议

对 `cqed_jc` / `cqed_dispersive` 且包含 classical `readout_line` 的模型，QuTiP engine 可通过 `study[].options.readout_protocol` 或等价的任务 payload 字段选择 monitored readout 协议：

- `homodyne_sme`：扩散型 stochastic master equation，只监测一个输出正交分量，`measurements.records` 中包含 `homodyne_current`。
- `heterodyne_sme`：扩散型 stochastic master equation，同时监测 I/Q 两个正交分量，`measurements.records` 中包含 `heterodyne_I`、`heterodyne_Q` 和复数形式的 `heterodyne_current`。
- `photon_counting_sme` / `photocurrent`：跳跃型 photon-counting 轨迹，记录离散 photon detection increment，`measurements.records` 中包含 `photon_counts`、`count_rate` 和 `jump_times`。

`photon_counting_sme` 不输出 IQ 电压或 homodyne current；它的核心观测量是每个时间 bin 的计数增量。固定 `run.seed` 和 `run.ntraj` 时，计数轨迹应可复现。

## 不再属于 solver 的内容

以下内容不再写在 `solver.yaml` 中，而是统一写到 `analyser.yaml`：

- `trajectory.states`
- `trajectory.save_times`
- `trajectory.save_final_state`
- `trajectory.save_jump_events`
- `trajectory.save_measurement_records`
- `metrics`
- `readout_model`
- `iq_discrimination`
- `report`

`solver` 的职责是生成 raw `trajectory`，`analyser` 的职责是从 `trajectory` 生成 population、IQ、report 等所有派生结果。

## 实用建议

- 从 `templates/solvers/qutip.yaml` 起步最稳妥
- 先只改 `engine`、`dt_s`、`t_end_s`
- 换引擎时尽量保持 `study` 结构不变，方便横向对比


