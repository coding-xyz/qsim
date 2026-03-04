# IO 与会话

## `run_workflow` 产物

典型输出：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `pulse_samples.npz`
- `executable_model.json`
- `model_spec.json`
- `trace.h5`
- `observables.json`
- `report.json`
- `settings_report.json`
- `run_manifest.json`
- `timings.json`
- `timing_diagram.dxf`（可选）

## `trace.h5` 与状态语义

`trace.h5` 保存求解器输出的时间轴与状态采样：

- `times`
- `states`
- HDF5 attributes:
  - `engine`
  - `state_encoding`（若工作流已完成语义标注）
  - `num_qubits`（若可确定）
  - `model_dimension`（若可确定）

当前工作流会显式区分以下几类 `state_encoding`：

- `per_qubit_excited_probability`
  - 每一列表示一个量子比特的激发概率。
  - 这种表示可以安全用于逐项跨引擎比较。
- `basis_population_single_qubit`
  - 单比特基态/激发态人口分布，典型形式为 `[p0, p1]`。
  - 可以解释 `final_p0/final_p1`，但不能误当成“两比特逐比特概率”。
- `ambiguous_population_vector`
  - 向量本身是人口分布或等价代理，但当前无法安全映射到逐比特激发概率。
  - 对这类结果，`cross_engine_compare.json` 不会输出逐项 `mse/mae`。

## `observables.json` 与 `cross_engine_compare.json`

- `observables.json`
  - 只在语义明确时生成对应观测量。
  - 例如单比特 `basis_population_single_qubit` 会生成 `final_p0/final_p1`，但不会伪造 `final_q1_excited`。
- `cross_engine_compare.json`
  - 只有当两条 trace 都是 `per_qubit_excited_probability` 且维度兼容时，才会输出逐项误差。
  - 若语义不兼容，会返回 `comparable: false` 和原因说明，供 notebook 或下游报表显式展示。

## 会话存储

会话接口：

- `Session.open(path)`
- `Session.commit(kind, payload, ...)`
- `Session.get(rev_id)`

底层由 `ArtifactStore` 和 `SessionManifest` 负责版本化与索引。
