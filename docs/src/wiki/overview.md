# Wiki 概览

主入口是 `qsim.ui.notebook.run_workflow(...)`，主流程如下：

1. 电路导入（QASM / Qiskit）
2. 归一化编译（`CompilePipeline`）
3. Lowering 到脉冲（`PulseIR`）
4. 构建物理模型（`ModelSpec`）
5. 数值求解（`Engine.run`）
6. 分析与产物落盘（analysis + qec）

建议优先查看以下产物：

1. `settings_report.json`
2. `model_spec.json`
3. `timings.json`
4. `trace.h5` / `observables.json` / `report.json`
5. `prior_report.json` / `decoder_report.json` / `logical_error.json`
6. `sensitivity_report.json` / `error_budget_v2.json` / `decoder_eval_report.json`
