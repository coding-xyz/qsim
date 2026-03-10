# [QEC-P0] 实现 MWPM/BP 解码器插件层并接入工作流

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-02

## 1. 背景与目标
- 背景：项目已有分析插件机制与统一产物体系，但缺少真正的 QEC 解码执行层。
- 目标：实现 decoder 插件架构，并提供 MWPM 与 BP 两个可切换实现（至少一个可用、另一个可占位/基础版）。
- 为什么现在做：先验模型（prior）有了以后，解码层是得到逻辑错误率与纠错性能指标的关键闭环。

## 2. 范围
- In Scope：
  - 定义 `IDecoder` 接口与注册机制。
  - 实现 `MWPMDecoder`、`BPDecoder`（基础可运行版本）。
  - 将 decoder 阶段接入 un_workflow`，落盘标准结果。
- Out of Scope：
  - 不做神经网络/张量网络解码（后续扩展）。
  - 不做多机分布式性能优化（先单机可复现）。

## 3. 输入与输出（I/O）
- 输入：
  - `decoder_input.json`（含 syndrome、prior、配置）
  - 可选 `prior_model.json`
  - 运行参数（seed、迭代次数、收敛阈值等）
- 输出：
  - `decoder_output.json`（修正建议、置信度、耗时）
  - `logical_error.json`（logical X/Z 或等价统计）
  - `decoder_report.json`（算法参数、收敛信息、失败样本统计）
- 相关 schema/version（如适用）：
  - `schema_version: 1.0`
  - `decoder_name`, `decoder_rev`, `input_hash`

## 4. 技术方案
- 方案概述：
  - 新建 `src/qsim/decoder/` 模块：`base.py`, egistry.py`, `mwpm.py`, `bp.py`。
  - `DecoderRegistry` 与现有 `AnalysisRegistry` 风格一致，支持版本化注册。
  - 在 un_workflow` 中新增 `decode_run` 阶段，并将结果写入 manifest。
- 关键设计决策：
  - Decoder 输入输出全走 schema，不直连内部对象，便于替换算法。
  - 解码失败要结构化输出（`status`, eason`, `failed_samples`）。
- 可替换点/扩展点（接口、插件、引擎等）：
  - `IDecoder.run(decoder_input, options) -> DecoderOutput`
  - 后续可扩展 `TensorNetworkDecoder` / `NeuralDecoder`。

## 5. 任务拆分
1. 建立 decoder 基础接口与 registry。
2. 实现 MWPM 基础解码器（优先）。
3. 实现 BP 基础解码器（可先简版）。
4. 接入 workflow：输入准备、执行、落盘、manifest。
5. 补充 CLI/Notebook 选择参数（如 `--decoder mwpm|bp`）。

## 6. 验收标准（DoD）
- [ ] `mwpm` 可在最小样例上跑通并输出标准 `decoder_output.json`。
- [ ] `bp` 至少具备基础可运行路径（即使精度暂不最优）。
- [ ] `logical_error.json` 可稳定生成，字段齐全。
- [ ] un_manifest.json` 包含 decoder 产物、哈希与 decoder 元数据。

## 7. 测试计划
- 单元测试：
  - registry 注册/查找、schema 校验、异常输入处理。
- 集成测试：
  - un_workflow` 含 decoder 全流程跑通（mwpm 与 bp 各一条）。
- 回归测试：
  - 固定 seed 下结果可重复；不影响无 decoder 的原有流程。
- 样例数据/命令：
  - 最小 syndrome 数据 + prior，比较两种 decoder 输出结构一致性。

## 8. 风险与回滚
- 主要风险：
  - BP 在部分图结构不收敛；MWPM 依赖图构建口径与 prior 一致性。
- 监控/告警点：
  - 收敛失败率、输出空结果、logical error 异常跳变。
- 回滚策略：
  - 默认回退到 `mwpm`，`bp` 失败不阻断主流程（记录 warning）。

## 9. 依赖与阻塞
- 前置依赖：
  - `QEC schema & 接口契约`
  - `Stim/Cirq prior` 模块（至少 mock prior 可用）
- 外部依赖（库/环境/数据）：
  - 图算法库（可选 `networkx`）
  - 样例 syndrome/prior 数据
- 潜在阻塞：
  - 解码输入格式和 prior 口径未统一。

## 10. 估时与优先级
- 优先级：P0
- 预计工期：3-6 天
- 负责人：待指派

## 11. 参考
- 相关文件：
  - `ISSUE_QEC_P0_SCHEMA_AND_INTERFACES.md`
  - `ISSUE_QEC_P0_STIM_CIRQ_PRIOR.md`
  - `src/qsim/ui/notebook.py`
  - `src/qsim/analysis/registry.py`
- 相关 issue/PR：
  - 后续：敏感度分析与误差预算升级
- 相关文档：
  - `ISSUE_TEMPLATE.md`

