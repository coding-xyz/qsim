# [QEC-P2] Pauli+/Kraus 误差预算重构 + Stim/Cirq 引擎接口

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-02

## 1. 背景与目标
- 背景：当前 `error_budget_v2` 使用 proxy 线性组合（`logical_x/z` + observables），可用于回归排序，但不等价于论文中的组件级误差预算。
- 目标：按论文方法重构：`Kraus 噪声模型 -> Pauli+ 仿真 -> epsilon_d -> Lambda3/5 -> 分项预算`。
- 同步目标：建立 Stim/Cirq 引擎接口（风格对齐现有 QuTiP 引擎），支持后续替换真实后端而不改上层 workflow I/O。

## 2. 范围
- In Scope:
  - 定义组件级误差 schema（1Q/CZ/CZ-stray/Measure+Reset/Leakage/DD）
  - 新增 Pauli+ 分析链路与预算产物
  - 新增 Stim/Cirq 引擎接口与最小实现（可先 mock + fallback）
  - 接入 un_workflow` + un_manifest`
- Out of Scope:
  - 实时解码在线链路（streaming syndrome -> control feedback）
  - 分布式大规模调度系统

## 3. 论文对齐方法（实现口径）
1. 用 Kraus 通道描述门/测量/闲置噪声。
2. 通过 generalized twirling 近似映射到 Pauli+/GPC 可高效仿真的通道。
3. 在不同码距上得到逻辑误差率 `epsilon_d`。
4. 计算缩放指标：`Lambda3/5 = epsilon_3 / epsilon_5`。
5. 对组件做 ablation（关闭/减半）评估对 `1/Lambda` 或 `epsilon_d` 的贡献，形成误差预算。

## 4. 输入与输出（I/O）
- 输入：
  - `syndrome_frame.json`
  - `prior_model.json`
  - 码距配置（至少 `d=3,5`）
  - 组件误差参数（1Q/CZ/measure/leakage/dd/...）
- 输出：
  - `scaling_report.json`（`epsilon_3`, `epsilon_5`, `lambda_3_5`）
  - `error_budget_pauli_plus.json`
  - `component_ablation.csv`（可选）
  - 保留现有 `error_budget_v2.json`（兼容）

## 5. 引擎接口设计（Stim/Cirq，类 QuTiP）

### 5.1 抽象接口
- 建议新增：`src/qsim/engines/qec_base.py`
- 接口：
  - `class QECAnalysisEngine(Protocol):`
    - un_pauli_plus(model_spec, *, code_distance, shots, seed, options=None) -> dict`
    - 返回至少含：`epsilon_d`, `metadata`, `engine`, `engine_rev`

### 5.2 具体实现
- `src/qsim/engines/stim_qec_engine.py`
  - 首版可走 `stim` 可用性检测 + mock/fallback
- `src/qsim/engines/cirq_qec_engine.py`
  - 首版可走 `cirq` 可用性检测 + mock/fallback
- 与现有风格一致：
  - 提供 `engine` 名称、`metadata`、错误回退说明

### 5.3 选择与路由
- 在 workflow/analysis 层增加参数：
  - `qec_engine: "stim" | "cirq" | "auto" | "mock"`
- `auto` 路由建议：`stim -> cirq -> mock`

## 6. 代码改造点
1. `src/qsim/analysis/pauli_plus.py`
  - un_pauli_plus_sim(...)`
  - `build_scaling_report(...)`
2. `src/qsim/analysis/error_budget_pauli.py`
  - `build_component_budget(...)`
3. `src/qsim/ui/notebook.py`
  - 接入新分析产物写盘 + manifest outputs
4. `src/qsim/common/schemas.py`
  - 增加新产物 schema（可先 dict schema_version 过渡）
5. `src/qsim/engines/*_qec_engine.py`
  - Stim/Cirq 引擎实现

## 7. 任务拆分
1. 定义组件误差 schema 与配置读取
2. 建立 `QECAnalysisEngine` 抽象接口
3. 实现 `stim_qec_engine` / `cirq_qec_engine` 最小可运行版本
4. 实现 `epsilon_3/epsilon_5` 报告
5. 实现组件 ablation 预算
6. workflow 接入 + artifact + manifest
7. 文档更新（Wiki/API）

## 8. 验收标准（DoD）
- [ ] 固定 seed 下 `epsilon_3/epsilon_5` 可复现
- [ ] `error_budget_pauli_plus.json` 至少包含 5 类组件贡献
- [ ] `qec_engine=stim|cirq|auto|mock` 均可运行（不可用时有清晰 fallback）
- [ ] un_manifest.json` 正确登记新产物与引擎元数据
- [ ] 保留旧 `error_budget_v2.json`，向后兼容
- [ ] 测试覆盖：单元 + 集成 + 回归

## 9. 测试计划
- 单元测试：
  - `lambda_3_5` 计算
  - 组件 ablation 贡献计算
  - Stim/Cirq 引擎选择与 fallback
- 集成测试：
  - workflow 生成 `scaling_report.json` + `error_budget_pauli_plus.json`
- 回归测试：
  - 旧链路产物（`error_budget_v2.json`）保持不变

## 10. 风险与缓解
- 风险：首版 Stim/Cirq 引擎可能仍为近似/mock，数值与实验存在偏差
- 缓解：先冻结 I/O 与接口；后续仅替换引擎实现
- 风险：组件定义口径不一致导致不可比较
- 缓解：报告中强制记录组件定义、参数快照、引擎版本

## 11. 优先级与工期
- 优先级：P2
- 预计工期：
  - M1（接口+schema+mock）：2-3 天
  - M2（Stim/Cirq 最小实现+集成）：2-4 天
  - M3（预算/测试/文档收尾）：2-3 天

## 12. 参考
- `s41586-022-05434-1`（Nature）
- `41586_2022_5434_MOESM1_ESM`（Supplementary）
- 当前实现：`src/qsim/analysis/sensitivity.py`

