# [QEC-P0] 定义量子纠错数据模型与接口契约

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-02

## 1. 背景与目标
- 背景：当前 `qsim` 已有工作流主干（circuit -> lowering -> model -> engine -> analysis），但缺少量子纠错专用的数据模型与标准 I/O 契约，导致后续 Stim/Cirq 先验与解码器（MWPM/BP）无法稳定接入。
- 目标：补齐 QEC 领域对象的 schema 与接口，保证“可版本化、可替换、可复现”。
- 为什么现在做：这是后续解码器与敏感度分析开发的前置条件，越早固化越能减少返工。

## 2. 范围
- In Scope：
  - 新增 QEC 相关 schema（如 `SyndromeFrame`、`DecoderInput`、`DecoderOutput`、`LogicalErrorSummary`）。
  - 定义解码器标准接口（输入输出、元数据、错误码约定）。
  - 将新增产物纳入 `run_manifest.json` 引用体系。
- Out of Scope：
  - 不实现具体解码算法（MWPM/BP/TN）。
  - 不引入 Stim/Cirq 实际计算逻辑（下一张 issue 做）。

## 3. 输入与输出（I/O）
- 输入：
  - `trace.h5`（现有）
  - `model_spec.json`（现有）
  - syndrome 原始数据（新增，建议 JSON/NPZ）
- 输出：
  - `syndrome_frame.json`
  - `decoder_input.json`
  - `decoder_output.json`
  - `logical_error.json`
- 相关 schema/version（如适用）：
  - 全部包含 `schema_version`
  - 建议首版 `1.0`

## 4. 技术方案
- 方案概述：
  - 在 `src/qsim/common/schemas.py` 中新增 dataclass。
  - 在 `src/qsim/analysis/` 或新建 `src/qsim/decoder/` 定义接口协议（Protocol/ABC）。
  - 在 `src/qsim/ui/notebook.py` 的 `run_workflow` 中预留解码阶段挂载点（先空实现/透传）。
- 关键设计决策：
  - decoder 只依赖标准 `DecoderInput`，不直接读内部对象，降低耦合。
  - 输出必须带 `analysis_rev`/`decoder_rev` 等版本追踪字段。
- 可替换点/扩展点（接口、插件、引擎等）：
  - `Decoder.run(input, options) -> DecoderOutput`
  - 后续 MWPM/BP/TN 只需实现同一接口即可替换。

## 5. 任务拆分
1. 定义并评审 schema 字段（最小可用版）。
2. 实现序列化与基础校验（含版本字段与必填项）。
3. 接入 workflow 产物与 manifest。
4. 补充 README/wiki 中 QEC I/O 文档。

## 6. 验收标准（DoD）
- [ ] 新增 schema 可在本地序列化/反序列化成功。
- [ ] `run_workflow` 运行后可生成新增占位产物（即使解码逻辑未实现）。
- [ ] `run_manifest.json` 正确记录新增产物引用与哈希。
- [ ] 文档包含字段说明、样例 JSON、版本策略。

## 7. 测试计划
- 单元测试：
  - schema 构造、默认值、字段缺失异常。
- 集成测试：
  - 一次最小工作流运行，检查新增产物和 manifest 一致性。
- 回归测试：
  - 不影响现有 `tests/test_*` 流程与已有产物字段。
- 样例数据/命令：
  - 使用 `examples/bell.qasm` + `examples/backend.yaml` 跑最小样例。

## 8. 风险与回滚
- 主要风险：
  - schema 设计过早固化导致后续算法接入受限。
- 监控/告警点：
  - manifest 缺失新增产物、版本不一致。
- 回滚策略：
  - 保留旧字段兼容期；新增字段采用向后兼容默认值。

## 9. 依赖与阻塞
- 前置依赖：
  - 无（可独立启动）。
- 外部依赖（库/环境/数据）：
  - 无强依赖外部库。
- 潜在阻塞：
  - QEC 数据口径（syndrome/logical error 定义）需团队统一。

## 10. 估时与优先级
- 优先级：P0
- 预计工期：1-2 天
- 负责人：待指派

## 11. 参考
- 相关文件：
  - `src/qsim/common/schemas.py`
  - `src/qsim/ui/notebook.py`
  - `src/qsim/analysis/registry.py`
  - `workflow.agent.md`
- 相关 issue/PR：
  - 后续：Stim/Cirq 先验接入、MWPM/BP 解码器实现
- 相关文档：
  - `ISSUE_TEMPLATE.md`
