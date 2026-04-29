# [DYN-P0] 重构 ModelSpec 为 engine-neutral Simulation IR，并按 solver mode 重整 QuTiP engine

## 0. 状态
- 状态：In Progress
- 负责人：待指派
- 更新时间：2026-04-28

## 1. 背景与目标
- 背景：
  - 当前 [src/qsim/common/schemas.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/common/schemas.py:222) 中的 `ModelSpec` 只有 `solver`、`dimension`、`t_end`、`dt` 和一个巨大的 `payload`。
  - [src/qsim/backend/model_build.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/model_build.py:311) 把 solver/device/pulse/noise/study/analyser 信息全部塞进 `payload`，包括 `model_type`、`controls`、`readout_controls`、`collapse_operators`、`noise_summary`、`frame`、`primary_step` 等。
  - QuTiP engine 在 [src/qsim/engines/qutip/runner.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip/runner.py:16) 又从这个大 dict 里二次解析 solver mode、frame、model type、readout protocol，导致 `use_homodyne_sme`、`use_heterodyne_sme`、`use_photon_counting_sme`、`use_monitored_sme` 等布尔分支堆积。
  - 上一个结构拆分 issue 已经把 QuTiP 文件按模块拆开，但还没有解决根因：从 `solver.yaml` 到仿真执行 IR 的 lowering 路径仍不明确。
- 目标：
  - 废弃 `ModelSpec.payload` 作为主数据通道，让 `ModelSpec` 自身成为结构化、engine-neutral 的 Simulation IR。
  - 将 `solver.yaml`、`device.yaml`、`pulse.yaml`、`analyser.yaml`、`study[]` lowering 到明确的 `ModelSpec` 字段，而不是一个无 schema 的 payload。
  - 明确区分 engine-neutral lowering 与 engine-specific lowering：`model_build.py` 只产出通用 IR，QuTiP / qoptics / qtoolbox 各自在 backend 内部转换为自己的运行 IR。
  - QuTiP engine 按 solver mode 建立清晰模块：`se.py`、`me.py`、`mcwf.py`、`sme.py`；每个 mode 只消费明确的 `QutipRunIR`。
  - Readout protocol 从布尔变量改成明确 `ReadoutSpec.protocol` / `ReadoutProtocolIR.kind` 分派，支持 `homodyne_sme`、`heterodyne_sme`、`photon_counting_sme`、`classical_readout`。
  - Rotating frame、operator、Hamiltonian、noise、readout 的 lowering 边界清晰，不再嵌在主运行函数里。
- 为什么现在做：
  - 当前 payload 式设计已经成为后续 QuTiP engine 简化、solver mode 拆分、多 engine parity 的主要阻塞。
  - 如果只继续拆 QuTiP 文件，不重做 `ModelSpec`，复杂度会在 `runner.py`、`sme.py`、`readout_protocols.py` 之间迁移，而不会消失。

## 2. 范围
- In Scope：
  - 重新设计 `ModelSpec`，移除主路径上的 `payload` 概念。
  - 在 `src/qsim/common/schemas.py` 或新的 schema 模块中增加结构化 dataclass：
    - `SolverSpec`
    - `TimeSpec`
    - `FrameSpec`
    - `SystemSpec`
    - `HamiltonianSpec`
    - `HamiltonianTerm`
    - `TimeDependentHamiltonianTerm`
    - `SignalSpec`
    - `NoiseSpec`
    - `ReadoutSpec`
    - `AnalysisRequestSpec`
    - `StudySpec` / `ModelMetadata`
  - 修改 `DefaultModelBuilder`，让它直接返回 `ModelSpec`。
  - 将 pulse samples lowering 成 `HamiltonianSpec.control_terms` / `HamiltonianSpec.readout_drive_terms` 中的 time-dependent `SignalSpec`。
  - 将 frame 解析集中到 `FrameSpec`，包括 resolved qubit reference frequencies 与 RWA 配置。
  - 将 noise lowering 成 `NoiseSpec.collapse_channels` / `NoiseSpec.stochastic_channels`。
  - 将 CQED readout lowering 成 `ReadoutSpec`，包括 protocol、chain、controls、classical/monitored readout options。
  - 修改 QuTiP engine，使其只读结构化 `ModelSpec`，再 lower 成 QuTiP-specific `QutipRunIR`。
  - 在 `src/qsim/engines/qutip/` 下建立 solver-mode 模块，例如：
    - `modes/se.py`
    - `modes/me.py`
    - `modes/mcwf.py`
    - `modes/sme.py`
  - 按职责拆分 QuTiP backend 内部 IR 和 builders：
    - `qutip/ir.py`
    - `qutip/model/operators.py`
    - `qutip/model/hamiltonian.py`
    - `qutip/model/collapse.py`
    - `qutip/model/frame.py`
    - `qutip/readout/homodyne.py`
    - `qutip/readout/heterodyne.py`
    - `qutip/readout/photon_counting.py`
    - `qutip/readout/classical.py`
  - 更新 qoptics / qtoolbox engine 以消费新的 `ModelSpec` 通用字段。
  - 更新 workflow persistence、docs、tests 中对 `model_spec.json` 的期望。
- Out of Scope：
  - 不新增新的物理模型。
  - 不新增新的 readout protocol。
  - 不重写 pulse compiler 本身；只改变 pulse samples 如何进入 `HamiltonianSpec`。
  - 不改变 `Trajectory` schema，除非发现必须为新 IR 补充 metadata。
  - 不长期保留 `payload` 双轨兼容。可以在同一个 issue 内使用临时迁移 helper，但最终 DoD 要求主路径无 legacy payload。

## 3. 输入与输出（I/O）
- 输入：
  - `task.yaml`
  - `solver.yaml`
  - `device.yaml`
  - `pulse.yaml`
  - `analyser.yaml`
  - QASM / CircuitIR / PulseIR / pulse samples
- 输出：
  - `ModelSpec`：engine-neutral Simulation IR。
  - Engine-specific `QutipRunIR` / Julia backend run IR。
  - 与当前等价的 `Trajectory` 输出。
  - 更新后的 `model_spec.json`，直接展示 solver/time/frame/system/hamiltonian/noise/readout 等字段。
- 相关 schema：
  - `ModelSpec` 不带单独版本号。
  - Breaking cleanup：旧 `ModelSpec.payload` 不作为新主路径保留。

## 4. 技术方案
- 方案概述：
  - 让 `ModelSpec` 自身成为 Simulation IR，而不是 `solver/dt/t_end + payload`。
  - `DefaultModelBuilder` 是唯一的通用模型 lowering 层，负责从 workflow/runtime artifacts 生成 engine-neutral `ModelSpec`。
  - Engine backend 只做 engine-specific lowering，例如 QuTiP backend 将 `ModelSpec` 转成 `QutipRunIR`、`Qobj` operators、QuTiP Hamiltonian list、collapse operators 和 solver options。
  - Solver mode runner 只处理自己的求解模式，不再由一个主函数同时决定 ME/MCWF/SME/readout/classical branches。
- 建议的 `ModelSpec` 顶层结构：

```python
@dataclass(slots=True)
class ModelSpec:
    engine_hint: str | None = None
    solver: SolverSpec
    time: TimeSpec
    frame: FrameSpec
    system: SystemSpec
    hamiltonian: HamiltonianSpec
    noise: NoiseSpec
    readout: ReadoutSpec | None = None
    analysis_request: AnalysisRequestSpec | None = None
    study: StudySpec | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

- `HamiltonianSpec` 必须能表示时序脉冲信号：

```python
@dataclass(slots=True)
class HamiltonianSpec:
    static_terms: list[HamiltonianTerm]
    coupling_terms: list[HamiltonianTerm]
    control_terms: list[TimeDependentHamiltonianTerm]
    readout_drive_terms: list[TimeDependentHamiltonianTerm]

@dataclass(slots=True)
class TimeDependentHamiltonianTerm:
    operator: OperatorRef
    coefficient: SignalSpec
    target: TargetRef | None = None
    frame: FrameBinding | None = None

@dataclass(slots=True)
class SignalSpec:
    kind: str  # sampled | analytic | piecewise
    unit: str
    times_s: list[float]
    values: list[float] | list[complex]
    interpolation: str = "linear"
    carrier: CarrierSpec | None = None
```

- 关键设计决策：
  - 不把 `payload["simulation_ir"]` 作为最终设计，因为如果 payload 只装一个 IR，它就只是多余包装。
  - 不长期保留旧 payload 字段，避免 `payload["model_type"]` 与 `ModelSpec.system.model_type` 等字段重复、分叉。
  - `model_build.py` 不出现 QuTiP `Qobj`、`mesolve`、`mcsolve`、`smesolve`、`sc_ops` 等概念。
  - `FrameSpec` 负责 engine-neutral reference-frame 语义；QuTiP backend 的 `frame.py` 只负责把该语义转成 QuTiP Hamiltonian 系数。
  - `ReadoutSpec.protocol` 是单一 source of truth，不再散落为 `use_homodyne_sme` 等多个布尔变量。
  - `SolverSpec.mode` 是 solver mode 的单一 source of truth，对应 backend 的 `modes/{mode}.py`。
- 可替换点 / 扩展点：
  - 其他 engine 可实现自己的 `lower_model_spec_to_backend_ir(model_spec)`。
  - 新 solver mode 通过新增 `modes/{mode}.py` 和 registry 接入。
  - 新 readout protocol 通过新增 readout protocol adapter 和 `ReadoutSpec.protocol` token 接入。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 盘点当前 `ModelSpec.payload` 所有使用点，分类为 solver/time/frame/system/hamiltonian/noise/readout/analysis/study/metadata。
2. 设计并实现 `ModelSpec` dataclass family，包含 JSON-safe serialization / restore helper。
3. 修改 `DefaultModelBuilder`，直接生成 `ModelSpec`，删除主路径上的大 payload 输出。
4. 将 `controls` / `readout_controls` lowering 到 `HamiltonianSpec.control_terms` / `readout_drive_terms`，使用 `SignalSpec` 表示 sampled pulse。
5. 将 collapse/stochastic noise lowering 到 `NoiseSpec`。
6. 将 model type、basis/truncation、components/connections lowering 到 `SystemSpec`。
7. 将 study step、trajectory request、readout protocol/options lowering 到 `StudySpec`、`AnalysisRequestSpec`、`ReadoutSpec`。
8. 修改 workflow persistence 和 `model_spec.json` 写出逻辑，确保 结构可读。
9. 为 QuTiP backend 新增 `qutip/ir.py`，实现 `lower_model_spec_to_qutip_ir(model_spec, run_options)`。
10. 为 QuTiP backend 建立 solver mode registry 和 `modes/se.py`、`modes/me.py`、`modes/mcwf.py`、`modes/sme.py`。
11. 将当前 `runner.py` 中的 solver dispatch 迁移到 mode runner。
12. 将 `sme.py` 中协议分支下沉到 readout protocol adapters：homodyne / heterodyne / photon-counting。
13. 将 rotating-frame 和 RWA 相关逻辑迁移到明确的 frame lowering helper。
14. 修改 qoptics / qtoolbox backend，消费 `ModelSpec` 通用字段。
15. 更新 tests 中所有手写 `ModelSpec(...)` 样例。
16. 更新 docs：`solver_config.md`、`overview.md`、API docs、必要时新增 `model_spec.md`。
17. 跑 targeted 和全量测试，记录任何 unrelated failure。

## 7. 验收标准（DoD）
- [x] `ModelSpec` 不再以 `payload` 作为主要模型数据通道。
- [x] `ModelSpec` 直接包含 solver/time/frame/system/hamiltonian/noise/readout/analysis/study/metadata。
- [x] `model_build.py` 不含 QuTiP-specific runtime 语义，只生成 engine-neutral IR。
- [x] Pulse sampled signals 能在 `HamiltonianSpec` 中以 `SignalSpec` 表示。
- [x] Rotating frame / RWA 信息集中在 `FrameSpec`，engine 只做 backend-specific lowering。
- [x] Readout protocol 使用 `ReadoutSpec.protocol` 单一字段分派，不再在主 runner 中维护多组 `use_*` 布尔变量。
- [x] QuTiP backend 存在 solver mode 模块：`se.py`、`me.py`、`mcwf.py`、`sme.py`。
- [x] QuTiP `runner.py` 不再承担 model parsing、frame parsing、readout protocol parsing、solver dispatch 的全部职责。
- [x] qoptics / qtoolbox tests 通过，说明新 `ModelSpec` 不是 QuTiP-only 设计。
- [x] 旧 payload 字段不再作为主路径使用；如果保留临时 helper，必须标注迁移用途并不进入 DoD 后的常规 engine 路径。
- [ ] `model_spec.json` 可读性明显提升，能直接看到 solver/time/frame/system/hamiltonian/noise/readout。
- [ ] `docstring` 已补全或更新。
- [ ] `docs/` 已补全或更新。
- [ ] `docs/src` 与 `docs/site` 已通过 `mkdocs build --clean` 同步。

## 8. 测试计划
- 单元测试：
  - `tests/test_model_build.py`
  - 新增 `ModelSpec` serialization / restore tests。
  - 新增 `HamiltonianSpec` sampled pulse lowering tests。
  - 新增 `ReadoutSpec.protocol` lowering tests。
- QuTiP targeted 测试：
  - `pytest -q tests/test_qutip_engine_general.py -p no:cacheprovider`
  - 覆盖 SE / ME / MCWF / homodyne SME / heterodyne SME / photon-counting SME / classical readout。
- Julia engine 回归：
  - `pytest -q tests/test_julia_engines.py -p no:cacheprovider`
- Workflow 回归：
  - `pytest -q tests/test_workflow_task_io.py tests/test_metric_registry.py -p no:cacheprovider`
- 全量测试：
  - `pytest -q -p no:cacheprovider`
  - 如果存在 unrelated failure，需在 issue 备注中记录具体失败项。
- 文档构建：
  - `mkdocs build --clean`

## 9. 风险与回滚
- 主要风险：
  - 这是 breaking schema refactor，影响面覆盖 workflow、model_build、engine、tests、docs。
  - 如果 dataclass 粒度过细，可能引入过度抽象，让 builder 更难读。
  - qoptics / qtoolbox 可能依赖旧 `ModelSpec.payload` 的隐式字段，需要同步迁移。
  - `model_spec.json` 的持久化结构变化可能影响已有 notebook / result summary / docs。
- 缓解策略：
  - 先做 payload 使用点盘点，再设计 schema。
  - 以 `model_build.py -> ModelSpec -> QuTiP IR` 为主线，小步验证。
  - 对每个 solver mode 单独跑 targeted tests。
  - 优先让 `ModelSpec` 字段名字接近物理语义，而不是接近某个 backend 的 API。
- 回滚策略：
  - 如果 schema 设计不稳定，先保留分支内修改，不合入主线。
  - 如果某个 engine 迁移风险过高，可先实现该 engine 的 adapter，再删除旧路径。
  - 如果全量迁移爆炸，回滚到上一个 QuTiP structural refactor 状态，并保留 schema 设计文档作为下一轮输入。

## 10. 依赖与阻塞
- 前置依赖：
  - `ISSUE_DYN_P1_QUTIP_ENGINE_STRUCTURAL_REFACTOR.md` 已完成，QuTiP backend 已有基本分包结构。
  - 当前 `solver.yaml` v3 study/time/frame/options 结构稳定。
- 外部依赖：
  - `qutip`
  - Julia backend tests 所需 Julia / package 环境。
- 潜在阻塞：
  - 当前全量测试存在既有 `measure_segments` 期望差异，可能影响“全绿”判断；需单独记录或另开 issue 修复。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：3-5 天
- 负责人：待指派

## 12. 执行记录
- 2026-04-28：
  - 移除了 issue 文案和文件名中的版本号口径，统一称为 `ModelSpec`。
  - `ModelSpec` 已改为结构化 engine-neutral Simulation IR：`solver/time/frame/system/hamiltonian/noise/readout/analysis_request/study/metadata`。
  - `DefaultModelBuilder` 直接 lowering 到结构化 `ModelSpec`，sampled pulse 进入 `HamiltonianSpec.control_terms` / `readout_drive_terms` 的 `SignalSpec`。
  - QuTiP / Julia backend 通过临时 runtime adapter 消费结构化 `ModelSpec`，不再读取 `ModelSpec.payload`。
  - workflow output、metric registry、result summary、相关测试用例已迁移到新字段。
  - 未完成项：QuTiP solver mode 模块化、readout protocol adapter 下沉、runner 继续瘦身、docs/mkdocs 同步。
  - 已验证：
    - `pytest -q tests\test_model_build.py tests\test_qutip_engine_general.py -p no:cacheprovider`
    - `pytest -q tests\test_metric_registry.py tests\test_readout_chain.py -p no:cacheprovider`
    - `pytest -q tests\test_result_summary.py -p no:cacheprovider --basetemp=.pytest_tmp_result_summary_fresh`
    - `pytest -q tests\test_julia_engines.py -p no:cacheprovider --basetemp=.pytest_tmp_julia_fresh`
  - 已知 unrelated failure：
    - `pytest -q tests\test_workflow_task_io.py tests\test_metric_registry.py -p no:cacheprovider --basetemp=.pytest_tmp_workflow_modelspec` 中 `test_v3_pulse_config_maps_multi_segment_measure_into_measure_segments` 仍因 `measure_segments` 额外包含 `rise_ns/fall_ns` 失败。
- 2026-04-28 继续执行：
  - 新增 `src/qsim/engines/qutip/modes/`：`se.py`、`me.py`、`mcwf.py`、`sme.py`，标准 solver dispatch 从 `runner.py` 移入 mode registry。
  - `runner.py` 中 monitored SME 与 hybrid classical readout 的执行 wrapper 已下沉到 solver mode 模块。
  - `use_homodyne_sme` / `use_heterodyne_sme` / `use_photon_counting_sme` / `use_monitored_sme` / `use_hybrid_classical_readout` 已收敛为单一 `readout_mode`。
  - 新增 `src/qsim/engines/qutip/model/hamiltonian.py`，集中处理 QuTiP Hamiltonian/operator/control/readout-drive lowering。
  - 新增 `src/qsim/engines/qutip/model/collapse.py`，集中处理 collapse operators 和 stochastic noise lowering。
  - `runner.py` 从约 780 行降到约 300 行，保留 orchestration、setup、trajectory config 与结果格式化。
  - 已验证：
    - `pytest -q tests\test_qutip_engine_general.py -p no:cacheprovider`
    - `pytest -q tests\test_model_build.py tests\test_readout_chain.py tests\test_metric_registry.py -p no:cacheprovider`
- 2026-04-28 合并重复 lowering 语义：
  - 新增 `src/qsim/common/channels.py`，统一 XY / Z / TC / RO 这类 sampled channel 的数值工具。
  - readout topology / chain / protocol lowering 已并入 `src/qsim/backend/model_spec_lowering.py`，作为 ModelSpec lowering pipeline 的 readout 分支，而不是单独暴露 `readout_lowering.py`。
  - QuTiP readout 和 analysis readout chain 不再各自重复解析 `components` / `connections` 中的 resonator、readout_line、readout_feedline、dispersive 参数。
  - `ModelSpec.readout.chain` 现在由 `DefaultModelBuilder` 生成，engine / analysis 可以优先消费这个已 lower 的 chain。
  - 新增 `control_dict_to_hamiltonian_term()`，`model_build.py` 和 migration helper 不再各自手写 control dict 到 `TimeDependentHamiltonianTerm` 的转换。
  - `model_build.py` 中 XY / DRAG / tunable coupling / readout drive 的 control record 构造合并为 `_sampled_control_record()`，避免四处重复维护 carrier/times/values/scale 字段。
  - 已验证：
    - `pytest -q tests\test_model_build.py tests\test_readout_chain.py tests\test_qutip_engine_general.py -p no:cacheprovider`
    - `pytest -q tests\test_model_build.py tests\test_qutip_engine_general.py tests\test_readout_chain.py tests\test_metric_registry.py -p no:cacheprovider`
- 2026-04-28 补齐 normalized Config 层：
  - 在 `src/qsim/backend/config.py` 新增 `DeviceConfig` / `NoiseConfig` / `SolverConfig` / `FrameConfig` / `StudyConfig` / `AnalysisConfig` / `ModelBuildConfig`。
  - 新增 `normalize_model_build_config()`，在 backend 边界把 raw YAML/runtime dict 统一成 typed normalized config。
  - `DefaultModelBuilder` 现在先构造 `ModelBuildConfig`，再进入 `model_spec_lowering.py`，不再直接把 raw `hw/noise/solver_run/frame/study/analyser` dict 传给 lowering 主路径。
  - `model_spec_lowering.py` 的主要入口已改为接受 normalized config 对象，同时保留 dict 兼容，方便现有测试和旧调用逐步迁移。
  - 新增测试覆盖 Config 入口的别名、类型和默认值规整。
  - 已验证：
    - `pytest -q tests\test_model_build.py tests\test_qutip_engine_general.py tests\test_readout_chain.py tests\test_metric_registry.py -p no:cacheprovider`
- 2026-04-28 命名边界清理：
  - `src/qsim/backend/lowering.py` 已重命名为 `src/qsim/backend/pulse_lowering.py`，表达 gate/schedule -> `PulseIR` 阶段。
  - `DefaultLowering` / `ILowering` 主名改为 `DefaultPulseLowering` / `IPulseLowering`，保留旧名作为兼容别名。
  - `src/qsim/backend/model_lowering.py` 已重命名为 `src/qsim/backend/model_spec_lowering.py`，表达 sampled channels + normalized config -> `ModelSpec` 阶段。
  - `ChannelLowering` / `FrameLowering` 改名为 `SampledChannelsIR` / `FrameResolution`，避免把 lowering 过程和 lowering 结果混在同一个名词里。
  - 新增 `src/qsim/backend/model_spec_common.py` 和 `src/qsim/backend/model_spec_noise.py`，把通用数值 helper 与 noise lowering 从 `model_spec_lowering.py` 中抽出，`model_spec_lowering.py` 从约 900 行降到约 800 行。
- 2026-04-28 Config / ModelSpec 层次继续收敛：
  - `DeviceConfig` 不再只是 dict wrapper，新增 typed `QubitConfig` / `ComponentConfig` / `ConnectionConfig` / `CouplingConfig`。
  - `NoiseConfig` 不再只是 dict wrapper，新增 typed `LocalNoiseConfig` / `StochasticNoiseConfig`。
  - `backend/model/noise.py` 现在优先消费 `NoiseConfig.local` / `NoiseConfig.stochastic` 和 `DeviceConfig` typed 字段，旧 dict `.get()` 只作为兼容分支保留。
  - `model_spec_lowering.py` 的 device 主路径改为通过 `DeviceConfig` typed 字段、`component_dicts`、`connection_dicts`、`coupling_dicts`、`qubit_dicts` 获取结构数据。
  - 新增 `src/qsim/backend/model/` 包：
    - `build.py`：ModelSpec orchestration
    - `lowering.py`：ModelSpec part builders / topology helpers
    - `noise.py`：NoiseSpec builder
    - `common.py`：ModelSpec lowering shared helpers
  - 根目录的 `model_build.py` / `model_spec_lowering.py` / `model_spec_noise.py` / `model_spec_common.py` 保留为兼容 wrapper，新代码应导入 `qsim.backend.model.*`。
  - 已验证：
    - `pytest -q tests\test_pulse_catalog.py tests\test_pulse_visualize.py tests\test_model_build.py tests\test_qutip_engine_general.py tests\test_readout_chain.py tests\test_metric_registry.py -p no:cacheprovider`

## 13. 参考
- 相关文件：
  - [src/qsim/common/schemas.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/common/schemas.py)
  - [src/qsim/backend/model_build.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/model_build.py)
  - [src/qsim/workflow/task_io.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/workflow/task_io.py)
  - [src/qsim/workflow/contracts.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/workflow/contracts.py)
  - [src/qsim/workflow/stages.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/workflow/stages.py)
  - [src/qsim/engines/qutip/runner.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip/runner.py)
  - [src/qsim/engines/qutip/sme.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip/sme.py)
  - [src/qsim/engines/qutip/readout_protocols.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip/readout_protocols.py)
- 相关 issue / PR：
  - `issues/done/ISSUE_DYN_P1_QUTIP_ENGINE_STRUCTURAL_REFACTOR.md`
  - `issues/done/ISSUE_DYN_P1_QUTIP_ENGINE_SME_REFACTOR_AND_PHOTON_COUNTING.md`
- 相关文档：
  - [docs/src/wiki/solver_config.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/solver_config.md)
  - [docs/src/wiki/overview.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/overview.md)
