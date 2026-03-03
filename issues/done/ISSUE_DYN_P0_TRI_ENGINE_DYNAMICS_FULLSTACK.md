# [DYN-P0] 打通三引擎全链路：参数化量子线路 -> 主方程/随机波函数仿真 -> 可视化产物

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 背景与目标
- 背景：当前 `julia_qtoolbox` / `julia_qoptics` 仍是 mock 输出，三引擎（QuTiP、QuantumOptics.jl、QuantumToolbox.jl）尚未在同一工作流中完成真实仿真与结果对齐。
- 目标：
  - 完成参数化量子线路（含参数绑定）到物理模型的统一映射。
  - 打通两类求解路径：主方程（ME）与随机波函数（MCWF）。
  - 在三大引擎上均可执行仿真并产出统一格式结果。
  - 产出三类可视化：量子电路图（Qiskit backend）、脉冲时序图（pulse/visualization）、仿真结果图（matplotlib backend）。
- 为什么现在做：这是后续误差预算、跨引擎一致性评估、参数扫描与实验对标的前置能力。

## 2. 范围
- In Scope：
  - Python <-> Julia 真桥接（QuantumOptics.jl + QuantumToolbox.jl），替换 mock 主路径。
  - 参数化线路输入（OpenQASM 参数表达式/绑定）到 `ModelSpec` 的映射。
  - 三引擎统一支持 `solver_mode = me | mcwf`。
  - 三引擎统一 trace/schema/metadata 输出。
  - 工作流中自动生成 circuit/pulse/result 三类图像产物。
- Out of Scope：
  - Julia 环境自动安装器与跨平台打包。
  - 多机分布式并行调度。

## 3. 输入与输出（I/O）
- 输入：
  - `qasm_text`（含参数定义）
  - `param_bindings`（单次或 sweep）
  - `backend_config`、`hardware`、`noise`
  - `engine`（`qutip|julia_qoptics|julia_qtoolbox`）
  - `solver_mode`（`me|mcwf`）
- 输出：
  - `trace.h5`（统一 schema）
  - `run_manifest.json`（记录引擎、Julia 包版本、solver、参数绑定）
  - `circuit_diagram.png`（Qiskit）
  - `pulse_timing.png` / `timing_diagram.dxf`
  - `trace.png`、`report.png`
  - `cross_engine_compare.json`（可选：跨引擎关键指标对比）
- schema/version：
  - 兼容现有 `Trace` 结构，metadata 增加 `engine_runtime`、`solver_mode`、`param_bindings`。

## 4. 技术方案
- 新增 Julia bridge 层（子进程 + JSON/H5 交换优先），统一调用协议与错误语义。
- 扩展模型映射层：参数化电路先绑定参数，再 lowering -> pulse -> model。
- 引擎接口统一：`Engine.run(model_spec, run_options)` 增强支持 `solver_mode`。
- 可视化统一落盘点放在 workflow 末端，失败不影响主仿真结果落盘（软失败 + manifest 标记）。

## 5. 任务拆分
1. 定义并实现 Python-Julia 交换协议（输入 schema、输出 trace schema、错误码）。
2. 实现 `julia_qoptics` 真执行路径（ME + MCWF）。
3. 实现 `julia_qtoolbox` 真执行路径（ME + MCWF）。
4. 扩展参数化电路绑定与模型映射（含参数 sweep）。
5. 三引擎结果对齐与归一化（时间轴、状态表示、metadata）。
6. 接入可视化产物自动导出（circuit/pulse/trace/report）。
7. 增加单测、集成测试、跨引擎一致性 smoke 测试。

## 6. 验收标准（DoD）
- [ ] 三引擎在同一参数化线路输入下均能完成 `me` 与 `mcwf` 仿真。
- [ ] 两个 Julia 引擎不再走 mock 默认路径（mock 仅保留显式 fallback）。
- [ ] 统一生成并落盘 `trace.h5` + `run_manifest.json`，且 metadata 完整。
- [ ] 成功导出 `circuit_diagram.png`、`pulse_timing.png`（或等价）、`trace.png`、`report.png`。
- [ ] CLI/Notebook 可通过参数切换引擎与求解模式，不破坏现有 qutip 路径。
- [ ] 关键集成测试在本地通过；无 Julia 环境时测试可 skip 且给出清晰原因。

## 7. 测试计划
- 单元测试：
  - 参数绑定解析与映射、solver_mode 分发、bridge 错误映射。
- 集成测试：
  - 参数化 Bell/2Q 电路在三引擎分别跑 `me` 与 `mcwf`，验证产物完整性。
- 回归测试：
  - 现有 qutip 与 workflow 相关测试保持通过。
- 样例命令：
  - `python -m qsim.ui.cli run --qasm ... --backend ... --engine qutip --solver-mode me`
  - `python -m qsim.ui.cli run --qasm ... --backend ... --engine julia_qoptics --solver-mode mcwf`

## 8. 风险与回滚
- 主要风险：Julia 运行时与包版本不一致导致接口不稳定；三引擎数值定义差异导致结果偏移。
- 缓解：固定最小版本矩阵、启动前自检、对齐可观测量而非逐点状态完全相等。
- 回滚：保留显式 `--allow-mock-fallback` 开关，默认关闭；桥接异常时可切回 qutip。

## 9. 依赖与阻塞
- 前置依赖：现有 workflow artifact 与 `ModelSpec` 接口稳定。
- 外部依赖：Julia、QuantumOptics.jl、QuantumToolbox.jl 可用且版本满足约束。
- 潜在阻塞：CI 缺 Julia runtime；Windows 路径/编码兼容问题。

## 10. 估时与优先级
- 优先级：P0
- 预计工期：7-10 天
- 负责人：待指派

## 11. 参考
- `src/qsim/engines/qutip_engine.py`
- `src/qsim/engines/julia_qoptics.py`
- `src/qsim/engines/julia_qtoolbox.py`
- `src/qsim/ui/notebook.py`
- `src/qsim/pulse/visualize.py`
- `issues/ISSUE_TEMPLATE.md`
