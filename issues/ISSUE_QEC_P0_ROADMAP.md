# QEC Roadmap (P0 -> P2)

## 0. 状态
- 状态：In Progress
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 总览
- 目标：打通 `schema -> prior -> decoder -> analysis -> eval -> dynamics` 的可复现闭环。
- 执行规则：所有 issue 中列出的项目全部按必选处理，不保留可选项。
- 完成标准：功能 issue 只有在代码、产物、测试和文档都完成后，才允许移入 `issues/done/`。

## 2. 当前状态
1. 已完成：
   - `P0-M1` Schema 与接口统一
   - `P0-M2` Stim/Cirq prior
   - `P0-M3` MWPM/BP decoder 主链路
   - `P1-M4` Sensitivity / Error Budget
   - `P1-M5` Decoder Eval / Sweep
   - `P1-M6` Julia real engine bridge
   - `DYN-P0` 三引擎全链路 dynamics fullstack
   - `P2` Pauli+ 组件误差预算
   - `P2` Scale / Retry / Resume
   - `PULSE-P1` XY/Z 与 XYZ 并线切换
2. 进行中：
   - `P0` Roadmap 管理与持续验收维护

## 3. 依赖关系
1. [ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md](./done/ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md)
2. [ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md](./done/ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md)
3. [ISSUE_QEC_P0_DECODER_MWPM_BP.md](./done/ISSUE_QEC_P0_DECODER_MWPM_BP.md)
4. [ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md](./done/ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md)
5. [ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md](./done/ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md)
6. [ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md](./done/ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md)
7. [ISSUE_DYN_P0_TRI_ENGINE_DYNAMICS_FULLSTACK.md](./done/ISSUE_DYN_P0_TRI_ENGINE_DYNAMICS_FULLSTACK.md)
8. [ISSUE_QEC_P2_PAULI_PLUS_ERROR_BUDGET.md](./done/ISSUE_QEC_P2_PAULI_PLUS_ERROR_BUDGET.md)
9. [ISSUE_QEC_P2_SCALE_AND_RELIABILITY.md](./done/ISSUE_QEC_P2_SCALE_AND_RELIABILITY.md)
10. [ISSUE_PULSE_P1_CHANNEL_LAYOUT_SPLIT_OR_MERGED.md](./done/ISSUE_PULSE_P1_CHANNEL_LAYOUT_SPLIT_OR_MERGED.md)

## 4. 里程碑
### M1: Schema / Interface
- 对应 issue：
  [ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md](./done/ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md)
- 结论：Done

### M2: Prior Builder
- 对应 issue：
  [ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md](./done/ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md)
- 必需产物：
  `prior_model.json`、`prior_report.json`、`prior_samples.npz`
- 结论：Done

### M3: Decoder Mainline
- 对应 issue：
  [ISSUE_QEC_P0_DECODER_MWPM_BP.md](./done/ISSUE_QEC_P0_DECODER_MWPM_BP.md)
- 结论：Done

### M4: Sensitivity / Error Budget
- 对应 issue：
  [ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md](./done/ISSUE_QEC_P1_SENSITIVITY_AND_ERROR_BUDGET.md)
- 必需产物：
  `sensitivity_report.json`、`error_budget_v2.json`、`figures/sensitivity_heatmap.png`
- 结论：Done

### M5: Decoder Eval / Sweep
- 对应 issue：
  [ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md](./done/ISSUE_QEC_P1_DECODER_EVAL_AND_SWEEP.md)
- 必需产物：
  `decoder_eval_report.json`、`decoder_eval_table.csv`、`figures/decoder_pareto.png`
- 结论：Done

### M6: Julia Real Engine Bridge
- 对应 issue：
  [ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md](./done/ISSUE_QEC_P1_REAL_JULIA_ENGINE_BRIDGE.md)
- 必需目标：
  至少一个 Julia 后端本地真实跑通，且 manifest 记录 Julia 运行时依赖信息
- 结论：Done

### M7: Dynamics Fullstack
- 对应 issue：
  [ISSUE_DYN_P0_TRI_ENGINE_DYNAMICS_FULLSTACK.md](./done/ISSUE_DYN_P0_TRI_ENGINE_DYNAMICS_FULLSTACK.md)
- 必需目标：
  三引擎 `qutip / julia_qoptics / julia_qtoolbox` 在同一参数化线路上均可完成 `me` 与 `mcwf` 运行，并导出 `trace.h5`、`run_manifest.json`、`circuit_diagram.png`、`pulse_timing.png`、`timing_diagram.dxf`、`trace.png`、`report.png`
- 结论：Done

## 5. 已验收结论
- 当前所有功能性 issue 均已完成并移入 `issues/done/`。
- 当前仍保留在 `issues/` 根目录下的仅有 roadmap 与模板文件。
- 后续新增工作项应继续使用同一规则：先建 issue，完成后验收，再移入 `issues/done/`。

## 6. 测试基线
- 已验证：
  `pytest -q -p no:cacheprovider tests/test_qec_workflow.py tests/test_julia_engines.py tests/test_pulse_visualize.py`
- 针对 DYN-P0 的本地验收烟测：
  使用同一参数化 QASM 输入，分别在 `qutip`、`julia_qoptics`、`julia_qtoolbox` 上执行 `me` 与 `mcwf`，并开启 artifact 导出，结果通过。

## 7. 后续约束
1. 新 issue 默认放在 `issues/` 根目录。
2. 只有在“代码 + 测试 + 产物 + 文档”全部完成后，才允许移入 `issues/done/`。
3. roadmap 继续作为唯一总览文件维护状态，不单独视为已完成功能项。
