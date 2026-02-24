# 后端与模型

## 模型层级

通过 `hardware.simulation_level` 选择：

- `qubit` -> `qubit_network`
- `nlevel` -> `transmon_nlevel`
- `cqed` -> `cqed_jc`

并包含自动回退逻辑（例如 `cqed` 且 `cavity_nmax<=0` 时回退到 `nlevel/qubit`）。

## Hamiltonian 构成

- 漂移项：`qubit_freqs_hz`、`anharmonicity_hz`、`cavity_freq_hz`
- 耦合项：`couplings`、`g_cavity_hz`
- 控制项：由 `PulseIR` 采样映射到 `controls`

## 脉冲形状

- `rect/dc`
- `gaussian`
- `drag`
- `readout`

默认门到脉冲映射：

- `x/sx/h` -> `XY*` Gaussian
- `z/rz` -> `Z*` DC
- `cx/cz` -> 双通道 DRAG
- `measure` -> `RO*` Readout
