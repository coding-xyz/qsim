# [DYN-P1] 按 backend 分包 engines，并拆分 qutip_engine.py 长方法

## 0. 状态
- 状态：Done
- 负责人：Codex
- 更新时间：2026-04-27
- 进展备注：
  - 已完成 backend 分包：`qutip/`、`qoptics/`、`qtoolbox/`、`stim/`、`cirq/`。
  - 已保留旧 `*_engine.py` 兼容 shim，并新增推荐 import 路径。
  - 已将 QuTiP serialization、operator builders、readout helper、readout protocol runner、SME runner、top-level runner 拆出到 `qutip/serialization.py`、`qutip/operators.py`、`qutip/readout.py`、`qutip/readout_protocols.py`、`qutip/sme.py`、`qutip/runner.py`。
  - `qutip_engine.py` 已变成 3 行兼容 shim；`qutip/engine.py` 现在只保留 `QuTiPEngine` facade 与通用数值 helper，约 174 行。
  - `run()` 已迁移为 `qutip/runner.py` 中约 49 行的流程编排：prepare -> build -> dispatch -> package。
  - 当前最长单个 helper 低于 300 行；SME / hybrid / classical readout 已按协议模块分层，payload 打包和入口调度拆出独立 helper。
  - 验证：`tests/test_qutip_engine_general.py` 15 passed；`tests/test_qutip_engine_general.py tests/test_julia_engines.py` 31 passed；import smoke 通过；`mkdocs build --clean` 通过；全量 `pytest -q -p no:cacheprovider` 为 `140 passed, 1 failed`，失败项仍为既有 pulse config `measure_segments` 字段期望差异。

## 1. 背景与目标
- 背景：
  - [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py) 已膨胀到约 119KB，单个 `QuTiPEngine` 类里混合了模型解析、算符构建、Hamiltonian 构建、collapse/noise、CQED readout、SME/MCWF 求解、classical readout、measurement/state 序列化和 `Trajectory` 包装。
  - 当前最长方法包括：
    - `run()`：约 545 行。
    - `_run_cavity_classical_readout()`：约 334 行。
    - `_run_hybrid_cqed_mcwf()`：约 270 行。
    - `_run_homodyne_cqed_sme()` / `_run_heterodyne_cqed_sme()` / `_run_photon_counting_cqed_sme()`：各约 198-202 行。
  - 现在即使已经有 `_run_cqed_sme(protocol=...)` 这样的入口，主文件仍然难以阅读：读者很难快速判断“入口编排、物理模型构建、读出协议、QuTiP 适配、结果格式化”分别在哪里。
- 目标：
  - 将 `src/qsim/engines/` 从平铺文件整理为按 backend 分包的结构，让每个 engine 相关实现都放在自己的目录里。
  - 让 `qutip_engine.py` 从“巨型实现文件”变成清晰的 QuTiP engine 兼容入口 / 门面；真实实现迁移到 `src/qsim/engines/qutip/` 包下。
  - 将 `run()` 缩短到可读的流程编排函数，目标是不超过 120-160 行。
  - 将超过 200 行的 helper 拆成若干职责明确的小函数或私有模块。
  - 明确 QuTiP engine 的内部边界：模型上下文、算符包、Hamiltonian 构造、读出协议、solver dispatch、结果序列化。
  - 同步为 `qoptics`、`qtoolbox`、`stim` 建立独立 engine 包，后续各 backend 的 runtime / adapter / helper 不再堆在 `engines/` 根目录。
  - 保持现有 public behavior、payload schema、trajectory schema 和测试语义不变。
- 为什么现在做：
  - 当前文件长度已经阻碍后续维护，尤其是继续扩展 CQED/readout/noise 时会越来越难定位修改点。
  - 这类结构问题必须单独治理，不能混在新增物理功能的 issue 里，否则每次都只会“顺手加一段”，文件继续变长。

## 2. 范围
- In Scope：
  - 在 `src/qsim/engines/` 下建立 backend 子包：
    - `qutip/`
    - `qoptics/`
    - `qtoolbox/`
    - `stim/`
    - 可选：`cirq/` 或 `qec/`，用于收纳 `cirq_qec_engine.py` 及 QEC base/helper。
  - 保留旧模块名作为兼容 shim，例如 `qutip_engine.py` 只 re-export `qsim.engines.qutip.QuTiPEngine`，避免一次性破坏外部 import。
  - 在 `src/qsim/engines/qutip/` 下新增内部模块，例如：
    - `engine.py`
    - `context.py`
    - `operators.py`
    - `hamiltonian.py`
    - `readout.py`
    - `sme.py`
    - `serialization.py`
  - 可以引入轻量 dataclass / NamedTuple，例如 `QutipRunContext`、`OperatorBundle`、`ReadoutContext`、`TrajectoryRequest`。
  - 拆分 `run()`、`_run_cavity_classical_readout()`、`_run_hybrid_cqed_mcwf()`、SME runner、readout formatter。
  - 补充面向内部 helper 的简短 docstring，说明职责边界。
  - 更新 `src/qsim/engines/__init__.py`、`src/qsim/workflow/engines.py`、测试和 docs API 引用到新包路径。
- Out of Scope：
  - 不新增新的物理模型。
  - 不改变现有 solver 参数含义。
  - 不重写 numerical formula。
  - 不改变 `ModelSpec` / `Trajectory` 的 public schema。
  - 不在本 issue 中修复 unrelated workflow / pulse config 测试失败。

## 3. 输入与输出（I/O）
- 输入：
  - 现有 `ModelSpec`、`run_options`、payload 中的 `model_type`、`controls`、`readout_controls`、`collapse_operators`、`noise_summary`、`analyser.trajectory`。
  - 现有 QuTiP dependency 和 QuTiP 5.x 行为。
- 输出：
  - 行为等价的 `Trajectory`。
  - 更清晰的内部模块 / helper 分层。
  - 更短的 `run()` 和更短的 readout / solver helper。
  - 不破坏现有测试与文档链接。
- 相关 schema / version：
  - 不变。

## 4. 技术方案
- 方案概述：
  - 第零阶段建立包目录与兼容 shim：先让 `qsim.engines.qutip`、`qsim.engines.qoptics`、`qsim.engines.qtoolbox`、`qsim.engines.stim` 都能导出原有 engine 类；旧的 `*_engine.py` 文件暂时保留为薄 re-export。
  - 第一阶段只做“等价搬运”：把纯 helper 和 formatter 从 `qutip_engine.py` 拆到 `engines/qutip/`，不改行为。
  - 第二阶段拆 `run()`：让它只负责高层流程，具体工作交给 `_prepare_context()`、`_build_operators()`、`_build_hamiltonian()`、`_build_collapse_ops()`、`_dispatch_solver()`、`_build_trajectory()`。
  - 第三阶段拆长 runner：将 classical readout、hybrid MCWF、SME runner 内部的“参数解析、QuTiP 调用、expectation 提取、payload 构造”拆开。
  - 第四阶段收敛重复的 readout payload formatter，避免 homodyne / heterodyne / photon-counting 分支各自拼大字典。
  - 第五阶段更新 docs API 页面，从旧平铺模块转向新 backend 包路径，并注明旧模块仍兼容。
- 建议的目标结构：
  - `src/qsim/engines/qutip/__init__.py`：导出 `QuTiPEngine`。
  - `src/qsim/engines/qutip/engine.py`：保留 `QuTiPEngine`、`run()` 编排、少量 adapter。
  - `src/qsim/engines/qutip/context.py`：run context、trajectory request、solver/readout selection。
  - `src/qsim/engines/qutip/operators.py`：qubit / nlevel / cqed 算符构造。
  - `src/qsim/engines/qutip/hamiltonian.py`：static Hamiltonian、couplings、controls、stochastic noise term 构造。
  - `src/qsim/engines/qutip/readout.py`：readout chain inference、classical readout、input-output、readout payload formatter。
  - `src/qsim/engines/qutip/sme.py`：homodyne / heterodyne / photon-counting monitored solver dispatch。
  - `src/qsim/engines/qutip/serialization.py`：Qobj、expectation、measurement、complex series、quantum trajectory serialization。
  - `src/qsim/engines/qoptics/`：收纳 `QOpticsEngine` 与 `qoptics_runtime.jl` 相关 helper。
  - `src/qsim/engines/qtoolbox/`：收纳 `QToolboxEngine` 与 `qtoolbox_runtime.jl` 相关 helper。
  - `src/qsim/engines/stim/`：收纳 `StimQECAnalysisEngine`。
  - 旧路径 `src/qsim/engines/qutip_engine.py`、`qoptics_engine.py`、`qtoolbox_engine.py`、`stim_qec_engine.py` 保留为兼容层，内容尽量只有 import/re-export。
- 关键设计决策：
  - 优先按职责边界拆分，不为了“抽象”而制造继承层级。
  - backend 目录是稳定组织边界；包内 helper 可根据是否 public 决定是否使用前导下划线。
  - 保留 `QuTiPEngine` 的外部导入路径不变：`from qsim.engines.qutip_engine import QuTiPEngine`。
  - 同时新增推荐导入路径：`from qsim.engines.qutip import QuTiPEngine`。
  - 每次拆分后先跑 targeted tests，避免大搬迁后难定位回归。
- 可替换点 / 扩展点：
  - 如果担心一次性拆文件风险过高，可以先在同文件内拆小函数，再第二步搬到私有模块。
  - 如果 dataclass 引入过多，可以先用 plain dict/context helper，但必须保证字段命名集中定义。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 每次提交前检查并更新相关 `docstring`。
3. 每次提交前更新 `docs/` 下对应文档。
4. `docs/site/` 视为构建产物，优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 文档变更后执行 `mkdocs build --clean`，确保 `docs/src` 与 `docs/site` 同步。
6. 仅当代码、测试、docstring、docs 同步完成后，issue 才可标记完成。

## 6. 任务拆分
1. 建立现状基线：记录 `qutip_engine.py` 方法长度、主要职责、现有测试覆盖。
2. 建立 backend 包目录：`qutip/`、`qoptics/`、`qtoolbox/`、`stim/`，并添加 `__init__.py`。
3. 将 `QOpticsEngine`、`QToolboxEngine`、`StimQECAnalysisEngine` 搬到各自包内，旧 `*_engine.py` 改成 re-export shim。
4. 将 `QuTiPEngine` 搬到 `qutip/engine.py`，旧 `qutip_engine.py` 改成 re-export shim。
5. 更新 `engines/__init__.py`、`workflow/engines.py`、测试 import 和 docs API 引用。
6. 抽取 QuTiP 序列化和 measurement helper 到 `qutip/serialization.py`，保持 `Trajectory` 输出不变。
7. 抽取 QuTiP 算符构建 helper 到 `qutip/operators.py`。
8. 抽取 run context / trajectory request 到 `qutip/context.py`：统一解析 `payload`、`run_options`、`solver`、`frame`、`readout_protocol`。
9. 拆分 Hamiltonian 构造到 `qutip/hamiltonian.py`：static model、couplings、controls、readout drive、stochastic noise 分成独立 helper。
10. 拆分 collapse ops 构造：cavity loss、relaxation、dephasing、excitation 明确分层。
11. 拆分 monitored readout solver 到 `qutip/sme.py`：QuTiP 调用与 payload formatter 分开。
12. 拆分 `_run_cavity_classical_readout()`：参数解析、轨迹积分、reset/feedback、payload 组装分离。
13. 拆分 `_run_hybrid_cqed_mcwf()`：trajectory loop、line state update、snapshot/measurement aggregation 分离。
14. 将 `run()` 改成 120-160 行左右的流程编排，并为每一步 helper 留清楚名字。
15. 更新 docs / issue 说明，记录新的内部结构和推荐 import 路径。
16. 跑 targeted 和全量测试，记录任何 unrelated failure。

## 7. 验收标准（DoD）
- [x] `src/qsim/engines/` 下存在 `qutip/`、`qoptics/`、`qtoolbox/`、`stim/` backend 包。
- [x] 旧 import 路径保持可用，例如 `qsim.engines.qutip_engine.QuTiPEngine`。
- [x] 新推荐 import 路径可用，例如 `qsim.engines.qutip.QuTiPEngine`。
- [x] `qutip_engine.py` 文件大小明显下降，或至少主类可读性显著提升。
- [x] `run()` 缩短到 120-160 行左右，并呈现清晰阶段：prepare -> build -> dispatch -> package。
- [x] 不再存在 300 行以上的单个 helper。
- [x] 200 行以上 helper 至少拆出内部小函数，并能从函数名看出职责。
- [x] `QuTiPEngine` 外部导入路径不变。
- [x] homodyne、heterodyne、photon-counting、hybrid MCWF、classical readout 行为不回退。
- [x] 新增私有模块有清楚职责，不产生循环 import。
- [x] 相关 `docstring` 已新增或更新。
- [x] `docs/` 已补充内部结构说明或维护说明。
- [x] `mkdocs build --clean` 通过。

## 8. 测试计划
- 单元 / targeted 测试：
  - `pytest -q tests/test_qutip_engine_general.py -p no:cacheprovider`
  - 覆盖 homodyne / heterodyne / photon-counting / hybrid / classical readout。
- 回归测试：
  - `pytest -q -p no:cacheprovider`
  - 如果全量测试有 unrelated failure，需在 issue 验证备注中记录具体失败项。
- 静态检查：
  - 使用 `python -c "import ast, pathlib; ast.parse(...)"` 或等价方式确认拆分后语法有效。
  - 检查 `rg -n "from qsim.engines.qutip_engine import QuTiPEngine"` 相关入口不受影响。
  - 新增 import smoke test：
    - `python -c "from qsim.engines.qutip import QuTiPEngine; from qsim.engines.qoptics import QOpticsEngine; from qsim.engines.qtoolbox import QToolboxEngine; from qsim.engines.stim import StimQECAnalysisEngine"`
- 文档构建：
  - `mkdocs build --clean`

## 9. 风险与回滚
- 主要风险：
  - 文件拆分可能引入循环 import。
  - 搬运过程中可能改变闭包捕获、QuTiP time-dependent coefficient 或 options 传递方式。
  - Readout payload 字段很容易因为 formatter 拆分发生小差异，影响 notebook/result summary。
- 缓解策略：
  - 小步提交：先搬纯函数，再搬有状态逻辑。
  - 每拆一层跑 `tests/test_qutip_engine_general.py`。
  - 对 payload 字段使用 snapshot-like asserts 或现有测试保持字段形状。
- 回滚策略：
  - 如果模块拆分风险过高，保留同文件拆分成果，暂不搬文件。
  - 如果某个 runner 拆分引入行为回归，先恢复该 runner，保留其他低风险 helper 拆分。

## 10. 依赖与阻塞
- 前置依赖：
  - 当前 QuTiP engine 的 readout 测试应能通过。
  - 明确本地 QuTiP 版本，尤其是 photon-counting 路径依赖 QuTiP 5.x `mcsolve` 行为。
- 外部依赖：
  - `qutip`
  - `numpy`
  - `pytest`
  - `mkdocs`
- 潜在阻塞：
  - 现有全量测试中 unrelated pulse config failure 可能影响“全绿”判断，需要单独记录或另开 issue。

## 11. 估时与优先级
- 优先级：P1
- 预计工期：2-4 天
- 负责人：待指派

## 12. 参考
- 相关文件：
  - [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py)
  - [tests/test_qutip_engine_general.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_qutip_engine_general.py)
  - [src/qsim/ui/notebook.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/notebook.py)
  - [src/qsim/ui/result_summary.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/result_summary.py)
- 相关 issue / PR：
  - `issues/done/ISSUE_DYN_P1_QUTIP_ENGINE_SME_REFACTOR_AND_PHOTON_COUNTING.md`
- 相关文档：
  - [docs/src/wiki/solver_config.md](/d:/超导量子计算机噪声抑制/qsim/docs/src/wiki/solver_config.md)
