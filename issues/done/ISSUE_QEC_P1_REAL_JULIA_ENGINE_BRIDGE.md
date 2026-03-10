# [QEC-P1] 将 Julia 引擎从 Mock 升级为真实桥接实现

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 背景与目标
- 背景：当前 `julia_qtoolbox`/`julia_qoptics` 为 mock 输出，无法用于真实物理仿真验证。
- 目标：落地至少一个真实 Julia 后端桥接（优先 QuantumToolbox.jl），保持 `Engine.run()` 接口不变。
- 为什么现在做：P1 需要提高结果可信度，为后续参数优化和实验对齐提供真实后端。

## 2. 范围
- In Scope：
  - 真实 Julia 调用链（进程调用或 PyJulia）。
  - `ModelSpec` 到 Julia 输入映射与返回解析。
  - 失败降级回退策略（回退 mock 或 qutip）。
- Out of Scope：
  - 不做跨平台打包自动安装。
  - 不做多节点分布式执行。

## 3. 输入与输出（I/O）
- 输入：
  - `model_spec.json`
  - un_options`
- 输出：
  - `trace.h5`（与现有结构兼容）
  - `engine_metadata`（记录 julia 版本、包版本、命令行）
- schema/version：
  - `Trace.schema_version` 不变
  - metadata 增加 `backend_runtime` 字段

## 4. 技术方案
- 方案概述：
  - 在 `src/qsim/engines/` 新增 `julia_bridge.py`，封装调用与错误处理。
  - `julia_qtoolbox.py` / `julia_qoptics.py` 切换到真实执行路径，mock 作为 fallback。
- 关键决策：
  - 首版采用“子进程 + JSON 文件交换”以降低环境耦合。
  - 调用失败时保留可追踪错误并可回退。
- 可替换点：
  - `IJuliaRunner.run(spec_path, out_path, opts) -> trace_payload`

## 5. 任务拆分
1. 定义 Python-Julia 交换协议（JSON schema）。
2. 实现 Julia 侧脚本模板与 Python bridge。
3. 接入两个 engine 类并提供 fallback。
4. 增加集成测试（环境可用时）与跳过策略。

## 6. 验收标准（DoD）
- [ ] 至少一个 Julia 后端在本地环境真实运行成功。
- [ ] `trace` 结构与现有可视化/分析兼容。
- [ ] 失败场景下有明确错误信息和回退行为。
- [ ] un_manifest.json` 记录 Julia 版本/依赖信息。

## 7. 测试计划
- 单元测试：
  - bridge 参数构造、错误码映射、fallback 路径。
- 集成测试：
  - 有 Julia 环境时跑 smoke case；无环境时 `skip` 且不中断。
- 回归测试：
  - 不影响 qutip 路径。

## 8. 风险与回滚
- 风险：Julia 运行环境差异导致不稳定。
- 缓解：明确版本锁定与运行前检查。
- 回滚：保留 mock 代码路径和引擎选择开关。

## 9. 依赖与阻塞
- 前置依赖：P0 工作流接口稳定。
- 外部依赖：Julia + QuantumToolbox.jl/QuantumOptics.jl。
- 阻塞：CI 环境缺少 Julia runtime。

## 10. 估时与优先级
- 优先级：P1
- 工期：4-7 天
- 负责人：待指派

## 11. 参考
- `src/qsim/engines/julia_qtoolbox.py`
- `src/qsim/engines/julia_qoptics.py`
- `src/qsim/engines/base.py`

