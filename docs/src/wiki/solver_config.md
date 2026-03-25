# 求解器配置

`solver` 文件决定数值引擎、时间步长、参考系和分析输出。当前文档只说明推荐使用的结构化 `solver` 写法。

## 当前模板

仓库中的主模板包括：

- `templates/solvers/qutip.yaml`
- `templates/solvers/qoptics.yaml`
- `templates/solvers/qtoolbox.yaml`

它们都采用同一套结构化组织方式。

## 最小示例

```yaml
schema_version: "3.0"
solver:
  engine: qutip
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
  analysis:
    trace:
      states: density_matrix
      save_times: all
      save_final_state: true
      save_jump_events: false
      save_measurement_records: false
    metrics:
      - population
      - mean_excited
      - variance
  schedule:
    policy: serial
```

## 顶层结构

当前推荐维护以下键：

- `schema_version`
- `solver.engine`
- `solver.study`
- `solver.analysis`
- `solver.schedule`

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

## analysis

`analysis` 决定输出哪些结果。当前模板常见的是：

- `trace.states`
- `trace.save_times`
- `trace.save_final_state`
- `trace.save_jump_events`
- `trace.save_measurement_records`
- `metrics`

## schedule

`schedule.policy` 控制 study 的执行策略。当前模板通常使用：

- `serial`

## 实用建议

- 从 `templates/solvers/qutip.yaml` 起步最稳妥
- 先只改 `engine`、`dt_s`、`t_end_s` 和 `analysis`
- 换引擎时尽量保持 `study` 结构不变，方便横向对比
