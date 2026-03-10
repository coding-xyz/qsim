# [QEC-P0] 接入 Stim/Cirq 噪声先验生成模块

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-03

## 1. 背景与目标
- 背景：当前项目已有通用仿真与分析流程，但 QEC 解码所需的 syndrome 图/超图先验概率尚无统一来源。
- 目标：新增基于 Stim/Cirq 的先验生成模块，产出标准化 `prior` 产物供后续 decoder 使用。
- 为什么现在做：它是 MWPM/BP 解码质量与可解释性的核心输入，属于 P0 前置能力。

## 2. 范围
- In Scope：
  - 新增 prior builder 接口与默认实现（Stim/Cirq）。
  - 将实验统计数据映射为边/超边概率、检测事件权重。
  - 产出可版本化 `prior` 文件并写入 manifest。
- Out of Scope：
  - 不实现完整解码逻辑（下一张 issue）。
  - 不做大规模性能优化（先保证正确性与可复现）。

## 3. 输入与输出（I/O）
- 输入：
  - 电路/轮次配置（来自 `circuit` 与 `backend`）
  - 实验统计数据（如检测事件频率、边界事件）
  - 可选噪声参数（T1/T2/串扰/泄露先验）
- 输出：
  - `prior_model.json`（先验结构与参数）
  - `prior_samples.npz`（可选，稀疏矩阵/采样缓存）
  - `prior_report.json`（构建日志、覆盖率、异常项）
- 相关 schema/version（如适用）：
  - `schema_version: 1.0`
  - 字段含 `builder_name`, `builder_rev`, `source_hash`

## 4. 技术方案
- 方案概述：
  - 新建 `src/qsim/qec/prior.py`（或 `src/qsim/decoder/prior.py`）定义 `IPriorBuilder`。
  - 增加 `StimPriorBuilder` 与 `CirqPriorBuilder`（先支持单一默认实现，另一个可占位）。
  - 在 workflow 中 prior 阶段写产物并注入 decoder 输入。
- 关键设计决策：
  - Prior 层与 Decoder 层解耦：decoder 只消费统一 `DecoderInput.prior`。
  - 对 Stim/Cirq 的依赖做可选导入，缺失时给出可读错误。
- 可替换点/扩展点（接口、插件、引擎等）：
  - `IPriorBuilder.build(ctx, data) -> PriorModel`
  - 可按设备/码型扩展 Surface / Repetition / LDPC 实现。

## 5. 任务拆分
1. 定义 prior schema（节点、边/超边、权重、边界、元信息）。
2. 实现 builder 接口与一个默认后端（Stim 或 Cirq）。
3. 对接 un_workflow` prior 阶段与产物落盘。
4. 增加失败回退策略（无依赖时提示安装，不中断主流程可选）。

## 6. 验收标准（DoD）
- [ ] 最小样例可生成 `prior_model.json` 且字段完整。
- [ ] un_manifest.json` 包含 prior 相关文件及哈希。
- [ ] prior 可被下游 decoder 输入结构直接读取。
- [ ] 缺少 Stim/Cirq 依赖时错误提示明确、可定位。

## 7. 测试计划
- 单元测试：
  - schema 校验、概率范围校验、边界事件映射测试。
- 集成测试：
  - 最小 workflow 运行，检查 prior 产物与 manifest。
- 回归测试：
  - 不影响非 QEC 路径（原有 run_workflow 输出保持兼容）。
- 样例数据/命令：
  - 使用固定 seed 和简化 syndrome 样例，验证重复运行一致性。

## 8. 风险与回滚
- 主要风险：
  - 不同库（Stim/Cirq）概率口径不一致导致结果偏差。
- 监控/告警点：
  - prior 稀疏度异常、概率和越界、缺失关键边界节点。
- 回滚策略：
  - 保留 `mock_prior` 后备路径，先保证 workflow 可运行。

## 9. 依赖与阻塞
- 前置依赖：
  - `QEC schema & 接口契约` issue 完成。
- 外部依赖（库/环境/数据）：
  - `stim`/`cirq`（至少一个）
  - 样例 syndrome 数据
- 潜在阻塞：
  - 实验数据格式不统一（需先约定字段）。

## 10. 估时与优先级
- 优先级：P0
- 预计工期：2-4 天
- 负责人：待指派

## 11. 参考
- 相关文件：
  - `ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md`
  - `src/qsim/ui/notebook.py`
  - `src/qsim/common/schemas.py`
- 相关 issue/PR：
  - 后续：`ISSUE_QEC_P0_DECODER_MWPM_BP.md`
- 相关文档：
  - `ISSUE_TEMPLATE.md`

