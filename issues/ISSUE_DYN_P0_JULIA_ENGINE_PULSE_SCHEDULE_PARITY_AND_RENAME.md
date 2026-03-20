# [DYN-P0] 重构 Julia 动力学引擎：按 pulse schedule 构建真实时变哈密顿量与 jump operator，并与 QuTiP engine 对齐

## 0. 状态
- 状态：In Progress
- 负责人：待指派
- 更新时间：2026-03-20

## 1. 背景与目标
- 背景：
  - 当前 Julia 动力学路径虽然复用了统一的 `QASM -> compile -> lower -> model_build` 前处理，但旧的 Julia runtime 实现没有像 `qutip_engine.py` 一样完整消费 lowering 结果。
  - 现实现主要从 `payload["controls"]` 中提取一个简化的平均 `omega`，从 `payload["collapse_operators"]` 汇总总速率，再构造单比特有效模型 `H = 0.5 * delta * sz + 0.5 * omega * sx`；没有正确解析时变 drive、`z` 控制、多比特耦合、frame/reference、以及完整 jump operator 语义。
  - 当前 Python 侧 `julia_bridge.py` / `julia_qoptics.py` / `julia_qtoolbox.py` 的命名和职责也偏“桥接脚本包装器”，与 `qutip_engine.py` 这种直接表达“引擎实现”的结构不一致，可读性和后续维护性较差。
- 目标：
  - 让 QuantumOptics.jl / QuantumToolbox.jl 两个 Julia 引擎与 `qutip_engine.py` 在模型解释层保持一致，基于 `ModelSpec.payload` 中的完整 lowering 产物构造真实哈密顿量与 jump operator。
  - 明确引擎实现边界，移除当前 `julia_bridge.py`、`julia_qoptics.py`、`julia_qtoolbox.py` 这套命名，替换为 `qoptics_engine.py`、`qtoolbox_engine.py`，整体形态与 `qutip_engine.py` 保持一致。
  - 保证 workflow 侧仅根据 `qoptics` / `qtoolbox` 这类明确 engine 名称选择 Julia 后端，不再保留兼容别名。
- 为什么现在做：
  - 当前 Julia 路径会给出“看起来可运行、但物理上只吃了简化摘要”的结果，容易误导 cross-engine compare、参数扫描与实验对齐。
  - 这是 Julia 引擎从“桥接可用”走向“物理模型正确”的关键修正，优先级应高于继续扩展新功能。

## 2. 范围
- In Scope：
  - 重写 Julia 动力学引擎实现，使其完整解析 `ModelSpec.payload` 中的 `controls`、`couplings`、`collapse_operators`、frame/reference/RWA 信息。
  - 在 Julia 侧按 pulse schedule 构建时变哈密顿量，而不是退化为单一平均幅度模型。
  - 在 Julia 侧按 qubit / nlevel / cqed 模型层级分别构建系统算符、漂移项、驱动项与 jump operator。
  - 移除 `qutip_engine.py` 中的 mock run / fallback 逻辑；对 Julia 动力学引擎同样禁止 mock 或静默降级，调用失败必须直接报错。
  - 重构 Python 侧引擎文件命名与结构：新增 `qoptics_engine.py`、`qtoolbox_engine.py`，直接删除 `julia_bridge.py`、`julia_qoptics.py`、`julia_qtoolbox.py`。
  - 更新 workflow 选择与 canonical engine name 逻辑，只保留新命名分支。
  - 补齐单元测试、集成测试、回归测试、文档与迁移说明。
- Out of Scope：
  - 不在本 issue 中实现 Julia 环境自动安装器。
  - 不在本 issue 中引入多节点/分布式执行。
  - 不追求三引擎逐点状态完全相等；验收以模型语义一致与可观测量对齐为主。

## 3. 输入与输出（I/O）
- 输入：
  - `CircuitIR` 经 compile/lower/model_build 后生成的 `ModelSpec`
  - `ModelSpec.payload.controls`
  - `ModelSpec.payload.couplings`
  - `ModelSpec.payload.collapse_operators`
  - `ModelSpec.payload.frame`
  - `run_options`（`seed`、`ntraj`、solver mode、超时/运行时选项）
- 输出：
  - 与 `Trace` schema 兼容的 Julia 求解结果
  - 明确记录引擎实现细节的 metadata：
    - `solver`
    - `solver_impl`
    - `julia_backend`
    - `julia_backend_version`
    - `dynamic_model`
    - `native_solver`
  - 迁移后的 engine 选择说明
- schema/version：
  - 继续兼容 `Trace` 现有 schema
  - 保持 `ModelSpec` 作为跨引擎统一输入契约，不为 Julia 单独降级/分叉 schema

## 4. 技术方案
- 方案概述：
  - 保留统一前处理链：`QASM -> normalize -> lowering -> pulse_samples -> ModelSpec`。
  - 重写 Julia 引擎实现，使其像 `qutip_engine.py` 一样直接面向 `ModelSpec.payload` 工作，而不是只消费简化摘要字段。
  - Julia 侧需要支持从 `controls` 中恢复时间序列驱动项，至少覆盖：
    - `axis = x | y | z`
    - `times` / `values`
    - `scale`
    - `carrier_omega_rad_s`
    - `drive_delta_rad_s`
    - `carrier_phase_rad`
    - `frame.mode` / `frame.reference` / `frame.rwa`
  - Julia 侧需要支持从 `couplings` 中恢复两比特耦合项，至少覆盖 `xx+yy`、`xx`、`zz`。
  - Julia 侧需要支持从 `collapse_operators` 中按目标比特、噪声类型逐项构建 jump operator，而不是只汇总总速率。
  - Python 文件结构从“bridge wrapper”切换为“engine implementation first”：
    - `src/qsim/engines/qoptics_engine.py`
    - `src/qsim/engines/qtoolbox_engine.py`
    - 与 `src/qsim/engines/qutip_engine.py` 保持同层级、同语义
- 关键决策：
  - 决策 1：`ModelSpec` 仍然是三引擎共享契约，Julia 引擎向 `qutip_engine.py` 对齐，而不是单独定义一个“简化 Julia payload”。
  - 决策 2：engine 文件命名以求解器/后端为中心，不再以“julia bridge”作为主抽象，避免把架构重点放在跨语言调用而非物理引擎实现。
  - 决策 3：直接移除旧 engine 名称与桥接包装文件，不保留 `julia_qoptics`、`julia_qtoolbox`、`julia_bridge` 等兼容入口。
  - 决策 4：若 Julia 包本身对某类时变项表达有限，应优先在引擎层显式暴露“不支持”的错误，而不是悄悄退化成平均参数模型。
  - 决策 5：动态引擎路径不再提供 mock fallback；依赖缺失、输入不支持、或求解失败时均直接报错。
- 可替换点 / 扩展点：
  - `select_engine()` / `canonical_engine_name()` 的 engine 注册表
  - Julia 运行时调用层（是否继续子进程调用，可独立于 engine 物理模型构建层演进）
  - 共用的 `ModelSpec -> engine-native operators` 映射辅助工具

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、`docstring`、`docs` 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 梳理 `qutip_engine.py` 当前支持的 `ModelSpec.payload` 语义，并形成 Julia 对齐清单。
2. 设计并实现 `qoptics_engine.py` 与 `qtoolbox_engine.py` 的新结构，替换现有 Julia 包装文件。
3. 在 Julia 侧实现基于 pulse schedule 的时变哈密顿量构造，覆盖 `x/y/z` 控制、frame/reference、RWA 相关逻辑。
4. 在 Julia 侧实现按目标与类型逐项构建 jump operator，覆盖 relaxation / excitation / dephasing。
5. 接入多比特耦合项与不同模型层级（`qubit_network`、`transmon_nlevel`、`cqed_jc`）。
6. 更新 workflow engine 注册、模板与运行时 metadata，移除旧别名分支。
7. 移除动态引擎 mock/fallback 相关逻辑与测试假设，改为显式错误语义。
8. 补齐测试、文档、迁移说明，并删除或废弃旧桥接式入口。

## 7. 验收标准（DoD）
- [ ] Julia 引擎不再通过“平均 `omega` + 汇总速率”近似替代 lowering 结果。
- [ ] Julia 引擎能完整解析 `controls` 时间序列，并构造对应时变哈密顿量。
- [ ] Julia 引擎能完整解析 `collapse_operators`，逐项生成正确 jump operator。
- [ ] Julia 引擎支持多比特耦合项，且不再默认退化为单比特有效模型。
- [ ] `qoptics_engine.py`、`qtoolbox_engine.py` 替代现有 `julia_bridge.py` / `julia_qoptics.py` / `julia_qtoolbox.py` 成为主实现入口。
- [ ] workflow 仅接受 `qoptics` / `qtoolbox` 等新 engine 名称，不再保留旧兼容入口。
- [ ] `qutip_engine.py` 不再包含 mock run；依赖缺失、输入非法或求解失败时直接报错。
- [ ] Julia 动力学引擎不再包含 mock/fallback；运行失败时直接报错。
- [ ] cross-engine compare 在代表性 case 上不再出现“输入相同但 Julia 实际只吃摘要字段”的结构性偏差。
- [ ] `docstring` 已补全或更新。
- [ ] `docs/` 已补全或更新。
- [ ] `docs/src` 与 `docs/site` 已通过构建同步且内容一致。

## 8. 测试计划
- 单元测试：
  - `ModelSpec.payload.controls` 到 Julia 时变驱动项映射测试。
  - `collapse_operators` 到 jump operator 映射测试。
  - engine name canonicalization 测试。
  - 不支持输入时的错误语义测试，确保不会静默退化。
- 集成测试：
  - 单比特 `x` / `z` 驱动在 QuTiP、QuantumOptics.jl、QuantumToolbox.jl 上输出一致的主观测量趋势。
  - 含耦合项的双比特 case 在三引擎上都能运行，并保留正确维度与 metadata。
  - `me` 与 `mcwf` 两种 solver mode 在两个 Julia 引擎上均可运行。
- 回归测试：
  - 现有 `qutip` 路径行为不变。
  - workflow 模板、CLI、cross-engine compare 仍可正常工作。
- 样例命令（如适用）：
  - `pytest -q`
  - `pytest -q tests/test_workflow_dynamics.py`
  - `pytest -q tests/test_trace_semantics.py`

## 9. 风险与回滚
- 主要风险：
  - QuantumOptics.jl / QuantumToolbox.jl 对某些时变驱动表达与 QuTiP 接口不完全同构，实现复杂度高。
  - engine 重命名会影响模板、脚本和已有配置。
  - 不同引擎的 frame/RWA 语义存在数值差异，容易导致“实现正确但结果不完全相同”的争议。
- 缓解策略：
  - 先建立与 `qutip_engine.py` 一一对应的 payload 语义清单，再逐项实现。
  - 直接移除旧 engine 名称与旧模块入口，避免双轨维护。
  - 将“显式报错”作为优先策略，避免静默近似。
- 回滚策略：
  - 分阶段落地，保留旧入口到最后移除。
  - 若新实现短期内不稳定，可通过 feature flag 或旧 alias 暂时切回旧路径，但必须显式标记为 legacy/approximate。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 `ModelSpec` / lowering / workflow 接口保持稳定。
  - `qutip_engine.py` 当前语义可作为对齐基准。
- 外部依赖（库 / 环境 / 数据）：
  - Julia runtime
  - QuantumOptics.jl
  - QuantumToolbox.jl
- 潜在阻塞：
  - Julia 包对时间依赖哈密顿量与算符构造的 API 差异。
  - Windows 路径、编码、子进程环境与 Julia depot 配置问题。

## 11. 估时与优先级
- 优先级：P0
- 预计工期：5-8 天
- 负责人：待指派

## 12. 参考
- `src/qsim/engines/qutip_engine.py`
- `src/qsim/engines/qoptics_engine.py`
- `src/qsim/engines/qtoolbox_engine.py`
- `src/qsim/engines/julia_runtime.py`
- `src/qsim/engines/qoptics_runtime.jl`
- `src/qsim/engines/qtoolbox_runtime.jl`
- `src/qsim/workflow/engines.py`
- `src/qsim/backend/lowering.py`
- `src/qsim/backend/model_build.py`
- `issues/ISSUE_TEMPLATE.md`
