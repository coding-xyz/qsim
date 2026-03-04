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
