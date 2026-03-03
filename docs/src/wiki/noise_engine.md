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

`julia_qtoolbox` 与 `julia_qoptics` 当前是占位实现（mock）。
