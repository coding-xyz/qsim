# API - engines

Julia-backed dynamics engines use backend-specific runtimes:
- `src/qsim/engines/qoptics/qoptics_runtime.jl`
- `src/qsim/engines/qtoolbox/qtoolbox_runtime.jl`

Backend implementations are organized by package under `src/qsim/engines/`.
Legacy modules such as `qsim.engines.qutip_engine` remain as compatibility shims.
The QuTiP backend keeps the public `QuTiPEngine` facade in `qsim.engines.qutip`,
with internal helpers split across `operators`, `measurement`, `model`, `modes`,
`dynamics`, `runner`, and `serialization`.

## `qsim.engines.base`

::: qsim.engines.base

## `qsim.engines.qec_base`

::: qsim.engines.qec_base

## `qsim.engines.stim`

::: qsim.engines.stim

## `qsim.engines.cirq`

::: qsim.engines.cirq

## `qsim.engines.qutip`

::: qsim.engines.qutip

## `qsim.engines.qtoolbox`

::: qsim.engines.qtoolbox

## `qsim.engines.qoptics`

::: qsim.engines.qoptics
