# 噪声与求解器

## 噪声模型

`noise.model` 支持：

- `markovian_lindblad`（默认）
- `one_over_f`
- `ou`（Ornstein-Uhlenbeck）

常见参数：

- `t1/t2/tphi/tup`（可按比特）
- `gamma1/gamma_phi/gamma_up`（可按比特）

关系式：

- `gamma1 = 1/T1`
- `gamma_up = 1/Tup`
- `1/T2 = (gamma1 + gamma_up)/2 + gamma_phi`

## 求解器

`QuTiPEngine` 支持：

- `se` -> `sesolve`
- `me` -> `mesolve`
- `mcwf` -> `mcsolve`

`julia_qtoolbox` 与 `julia_qoptics` 当前支持通过 Julia bridge 调用原生后端：

- `julia_qtoolbox` -> `QuantumToolbox.jl`
- `julia_qoptics` -> `QuantumOptics.jl`

注意：

- 三引擎都可以真实运行，但 `Trace.states` 的行语义不一定天然一致。
- 工作流层会补充 `trace.metadata.state_encoding`，并据此决定：
  - 是否可以安全生成逐比特观测量；
  - 是否可以安全做跨引擎逐项误差比较。
- 当结果被标记为 `ambiguous_population_vector` 时，应先做语义审查，而不是直接比较 `mse/mae`。

## Task1 single-qubit visual check

- Use `examples/noise_simulation_tests/task1_single_qubit_visual_compare.py`
  to read existing tri-engine artifacts and export semantically aligned `p1(t)`
  curves.
- The script maps:
  - `basis_population_single_qubit` -> `p1(t) = state[1]`
  - `per_qubit_excited_probability` (single qubit) -> `p1(t) = state[0]`
- This check is metric-level semantic comparison, not raw state-vector
  pointwise equivalence.

## Task1 native references

- QuTiP reference:
  - `examples/noise_simulation_tests/task1_qutip_native_reference.py`
- QuantumOptics.jl reference:
  - `examples/noise_simulation_tests/task1_quantumoptics_native_reference.jl`

These scripts are for call-path and trend verification against the same Task1
effective single-qubit model assumptions.
