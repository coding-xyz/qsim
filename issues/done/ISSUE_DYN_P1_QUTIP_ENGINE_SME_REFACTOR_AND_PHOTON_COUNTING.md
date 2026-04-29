# [DYN-P1] 梳理 QuTiP engine 结构并统一 CQED SME 读出协议

## 0. 状态
- 状态：Done
- 负责人：Codex
- 更新时间：2026-04-27
- 验证备注：`tests/test_qutip_engine_general.py`、新增 photon-counting 用例和 `mkdocs build --clean` 均通过；全量 `pytest -q -p no:cacheprovider` 为 `140 passed, 1 failed`，失败项为既有 pulse config `measure_segments` 字段期望差异，和本 issue 的 QuTiP/readout 改动无关。

## 1. 背景与目标
- 背景：
  - [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py) 目前同时承担模型解析、算符构造、Hamiltonian 组装、collapse/noise 构造、读出链仿真、SME/MCWF 特殊求解、结果序列化和 `Trajectory` 包装。
  - `run()` 方法过长，homodyne / heterodyne CQED SME 的实现重复度高，后续继续扩展 readout protocol 会进一步放大维护成本。
  - 当前已有 `homodyne_sme` 与 `heterodyne_sme`，但还缺少 photon-counting / photocurrent 这一类常用的跳跃型连续测量轨迹。
- 目标：
  - 将 `QuTiPEngine.run()` 收敛为清晰的编排入口，让模型构建、读出协议、solver dispatch、序列化各自有边界。
  - 合并 `_run_homodyne_cqed_sme` 与 `_run_heterodyne_cqed_sme` 为统一的 `_run_cqed_sme(protocol=...)` 入口。
  - 在统一入口中扩展 `photon_counting_sme` / `photocurrent` 协议，输出 photon detection record、count rate、readout observable 和兼容的 `Trajectory` payload。
  - 保持现有 `homodyne_sme`、`heterodyne_sme` 和 classical readout 行为不回退。
- 为什么现在做：
  - `qutip_engine.py` 已经进入“功能不断增长但边界不清”的阶段，继续追加新 readout protocol 前应先建立扩展点。
  - photon-counting 与 homodyne / heterodyne 属于不同测量展开：前者是离散跳跃/计数记录，后两者是扩散型 Wiener 噪声记录，统一抽象能避免把物理语义混在同一字段里。

## 2. 范围
- In Scope：
  - 仅聚焦 [qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py) 及其必要测试、文档。
  - 抽取 run context、operator bundle、readout context、trajectory request 等轻量内部结构。
  - 将 homodyne / heterodyne SME 的公共流程收敛到 `_run_cqed_sme`。
  - 扩展 `_resolve_readout_protocol`，支持 `photon_counting_sme`、`photon-counting`、`photocurrent` 等别名。
  - 为 photon-counting 增加输出 schema：`photon_counts`、`count_rate`、`jump_times` 或等价字段。
- Out of Scope：
  - 不改变 `ModelSpec` 的核心 schema，除非现有 `payload.primary_step.options.readout_protocol` 无法表达。
  - 不重写 QuTiP solver 本身。
  - 不把 `readout_line` 升级为完整量子传输线 Hilbert 空间。
  - 不在本 issue 中重构 Julia engine。

## 3. 输入与输出（I/O）
- 输入：
  - `ModelSpec.payload.model_type in {"cqed_jc", "cqed_dispersive"}`。
  - `readout_controls`、`readout_line`、`readout_feedline`、`primary_step.options.readout_protocol`。
  - `run_options.ntraj`、`run_options.seed`、`run_options.qutip_options`。
- 输出：
  - 与当前一致的 `Trajectory.times`、`wave_function` / `density_matrix`、`metadata`。
  - `classical.readout` 对 homodyne、heterodyne、photon-counting 三类协议均有明确字段。
  - `measurements.records` 中保留每条 trajectory 的原始测量记录。
  - `metadata.readout_protocol`、`metadata.measurement_model`、`metadata.solver_impl` 明确区分 `homodyne_sme`、`heterodyne_sme`、`photon_counting_sme`。
- 相关 schema / version：
  - 延续 readout payload 的 `schema_version: "1.0"`。
  - 若新增 `photon_counts` payload，需在文档中定义字段语义与单位。

## 4. 技术方案
- 方案概述：
  - 第一步做等价重排：将 `run()` 中的输入解析、模型算符构造、Hamiltonian/collapse 构造、solver dispatch、Trajectory 包装拆成私有 helper。
  - 第二步做 SME 收敛：新增 `_run_cqed_sme(protocol, ...)`，内部共享 QuTiP `smesolve` / `mcsolve` 参数准备、expectation 提取、readout payload 构造。
  - 第三步接入 photon-counting：优先按当前 QuTiP 5.x 能力调研选择实现路径；若 `smesolve` 不直接提供 jump 型 photocurrent API，则用 `mcsolve` 的 `photocurrent` / collapse event 输出作为 photon-counting trajectory 来源，并在 metadata 中标记 solver path。
- 关键设计决策：
  - homodyne：扩散型连续测量，记录单个输出正交分量，measurement 形如实值电流。
  - heterodyne：扩散型连续测量，同时记录两个正交分量，measurement 形如 IQ 复电流。
  - photon-counting / photocurrent：跳跃型连续测量，记录离散 photon detection / count increment；轨迹在无计数区间连续演化，在计数事件处发生 jump。
  - 不把 photon-counting 输出伪装成 IQ voltage；它应有独立的 `photon_counts`、`count_rate`、`jump_times` 语义。
  - 若 QuTiP 版本差异导致 API 不同，封装在一个兼容 helper 中，避免主流程出现版本分支噪声。
- 可替换点 / 扩展点：
  - `_run_cqed_sme(protocol=...)` 后续可继续加入 inefficient detection、feedback control 或多通道 monitored operators。
  - readout payload formatter 可独立为 `_format_cqed_readout_payload(...)`，避免每种协议重复拼大字典。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 盘点 `qutip_engine.py` 的现有职责边界，列出必须保持不变的 public behavior。
2. 抽取 run context / operator bundle / trajectory request，不改变数值行为。
3. 抽取 Hamiltonian、control、collapse、noise 构造 helper。
4. 抽取通用 metadata 和 `Trajectory` 构造 helper，消除特殊 solver 分支里的重复 return 块。
5. 合并 `_run_homodyne_cqed_sme` 与 `_run_heterodyne_cqed_sme` 为 `_run_cqed_sme(protocol=...)`。
6. 新增 photon-counting / photocurrent 协议解析、solver 适配和 readout payload 格式。
7. 增加 photon-counting 单通道 cavity readout 测试，覆盖 count record、seed reproducibility、metadata。
8. 更新 docs / docstring，说明三类连续测量协议的差异和字段语义。

## 7. 验收标准（DoD）
- [x] `QuTiPEngine.run()` 明显变薄，主流程只负责编排 monitored CQED readout 入口，不再分别内嵌 homodyne / heterodyne 分支。
- [x] `homodyne_sme` 与 `heterodyne_sme` 通过统一 `_run_cqed_sme(protocol=...)` 路径运行。
- [x] `readout_protocol: photon_counting_sme` 或 `photocurrent` 可运行 CQED readout 示例。
- [x] photon-counting 输出包含离散计数记录，不被序列化为 IQ/homodyne 电流。
- [x] 现有 `tests/test_qutip_engine_general.py` 中 homodyne、heterodyne、hybrid、classical readout 测试不回退。
- [x] 新增 photon-counting 测试覆盖 deterministic seed、measurement record shape、metadata。
- [x] `docstring` 已补全或更新。
- [x] `docs/` 已补全或更新。
- [x] `mkdocs build --clean` 通过。

## 8. 测试计划
- 单元测试：
  - `_resolve_readout_protocol` 对 `photon_counting_sme`、`photon-counting`、`photocurrent` 的别名解析。
  - photon-counting payload formatter 对空计数、单次计数、多 trajectory 的输出 shape。
  - `_run_cqed_sme(protocol=...)` 对 homodyne / heterodyne 的 protocol dispatch。
- 集成测试：
  - 最小 `cqed_dispersive + readout_line(classical)` 示例运行 photon-counting readout。
  - 固定 seed 下 photon-counting record 可复现。
  - `Trajectory.classical.readout` 与 `Trajectory.measurements.records` 可被 result summary / notebook 读取。
- 回归测试：
  - `pytest -q tests/test_qutip_engine_general.py -p no:cacheprovider`
  - `pytest -q -p no:cacheprovider`
- 样例命令：
  - `pytest -q tests/test_qutip_engine_general.py -p no:cacheprovider`

## 9. 风险与回滚
- 主要风险：
  - QuTiP 4.x 与 5.x 对 photocurrent / photon-counting 的 API 差异较大。
  - photon-counting 是跳跃型记录，若复用 homodyne/heterodyne 的 measurement shape，容易造成后续分析误读。
  - 大文件拆分可能引入行为变化，尤其是 CQED readout metadata 和 state storage。
- 缓解策略：
  - 先做等价重排，再做新协议；每一步跑 targeted regression。
  - 将 QuTiP 版本差异封装在单个 helper 中，并在 metadata 记录实际 solver path。
  - 为 readout payload 增加 protocol-specific 字段，避免隐式复用。
- 回滚策略：
  - 若 photon-counting 接入受 QuTiP 版本阻塞，保留 `_run_cqed_sme` 收敛成果，将 photon-counting 标记为 `unsupported` 并给出明确错误。
  - 若重构引发回归，优先回滚 helper 抽取，不改变原有 solver 分支。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 CQED readout 测试必须可本地运行。
  - 明确当前项目支持的 QuTiP 主版本范围。
- 外部依赖：
  - `qutip.smesolve` / `SMESolver` 的 homodyne、heterodyne measurement API。
  - `qutip.mcsolve` 或旧版 `photocurrent_mesolve` 的 photon detection / photocurrent 输出能力。
- 潜在阻塞：
  - 如果项目必须同时支持 QuTiP 4.x 和 5.x，photon-counting adapter 需要双路径。
  - 如果当前环境没有 QuTiP，新增测试需要 `pytest.importorskip("qutip")`。

## 11. 估时与优先级
- 优先级：P1
- 预计工期：3-5 天
- 负责人：待指派

## 12. 参考
- 相关文件：
  - [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py)
  - [tests/test_qutip_engine_general.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_qutip_engine_general.py)
  - [src/qsim/ui/result_summary.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/result_summary.py)
  - [src/qsim/ui/notebook.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/notebook.py)
- 相关 issue / PR：
  - `issues/failed/ISSUE_DYN_P0_QUANTUM_CLASSICAL_READOUT_CHAIN_AND_TASK2_SPAM.md`
- 相关文档：
  - QuTiP 5.3 Stochastic Solver: https://qutip.readthedocs.io/en/latest/guide/dynamics/dynamics-stochastic.html
  - QuTiP 4.7 Photocurrent Solver: https://qutip.readthedocs.io/en/qutip-4.7.x/guide/dynamics/dynamics-photocurrent.html
  - QuTiP 5.x Monte Carlo Photocurrent note: https://qutip.readthedocs.io/en/stable/guide/dynamics/dynamics-monte.html
