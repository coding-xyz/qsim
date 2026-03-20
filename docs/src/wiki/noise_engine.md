# 噪声与求解器

## 噪声模型

`noise.model` 当前支持：
- `markovian_lindblad`
- `one_over_f`
- `ou`

常见参数：
- `t1`
- `t2`
- `tphi`
- `tup`
- `gamma1`
- `gamma_phi`
- `gamma_up`

关系式：
- `gamma1 = 1 / T1`
- `gamma_up = 1 / Tup`
- `1 / T2 = (gamma1 + gamma_up) / 2 + gamma_phi`

## 动力学求解器

`QuTiPEngine` 直接在 Python 侧调用 QuTiP：
- `se` -> `sesolve`
- `me` -> `mesolve`
- `mcwf` -> `mcsolve`

Julia 引擎使用按后端拆分的原生 runtime：
- `qoptics` -> `src/qsim/engines/qoptics_runtime.jl` -> `QuantumOptics.jl`
- `qtoolbox` -> `src/qsim/engines/qtoolbox_runtime.jl` -> `QuantumToolbox.jl`

这两个 Julia runtime 都直接消费 workflow lowering 之后生成的 `ModelSpec.payload`，重点包括：
- `controls`
- `couplings`
- `collapse_operators`
- `noise_summary.stochastic`

也就是说，Julia 后端现在和 `qutip_engine.py` 一样，按 pulse schedule / control 序列构造时变哈密顿量，并从 `collapse_operators` 构造 jump operators，而不是再走一个单独的“bridge mock 模型”。

## 结果语义

三套动力学引擎统一返回：
- `Trace.metadata.state_encoding = per_qubit_excited_probability`

这让 workflow 可以安全地做：
- 逐比特可观测量提取
- cross-engine compare
- 后续 error budget / sensitivity 分析

如果底层求解失败，当前策略是直接报错，不再提供 mock fallback。

## Task1 可视化检查

- `examples/noise_simulation_tests/task1_single_qubit_visual_compare.py`

这个脚本用于读取已有的 tri-engine artifacts，并导出语义对齐后的 `p1(t)` 曲线，属于指标层面对齐检查，不是原始状态向量的逐点等价比较。

## Task1 原生参考

- QuTiP: `examples/noise_simulation_tests/task1_qutip_native_reference.py`
- QuantumOptics.jl: `examples/noise_simulation_tests/task1_quantumoptics_native_reference.jl`

这些脚本用于在同一组 Task1 假设下做调用链与趋势核对。

