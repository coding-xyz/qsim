# [PULSE-P1] 可视化支持 XY/Z 分线与 XYZ 并线切换

## 0. 状态
- 状态：Done
- 负责人：待指派
- 更新时间：2026-03-02

## 1. 背景与目标
- 背景：当前 `src/qsim/pulse/visualize.py` 的 timing layout 按物理通道逐行绘制，`XY_i` 和 `Z_i` 默认分成两行显示。
- 现状问题：
  - 在多比特脉冲图中，分线显示会显著增加图高度。
  - 某些查看场景下，用户更希望按“每个 qubit 一行”观察控制脉冲，即将 `XY_i` 与 `Z_i` 叠加在一个显示行中。
  - 当前实现没有显式开关来控制“分线”还是“并线”。
- 目标：
  - 为 pulse timing visualization 增加一个显示层开关 `XYZ_line_combine`，允许用户选择：
    - `False`：`XY_i` / `Z_i` 分线显示
    - `True`：`XY_i` / `Z_i` 并线显示为 `XYZ_i`
  - 保持默认行为不变，确保现有调用方无感知。
- 为什么现在做：这是一个纯显示层能力增强，改动范围可控，能直接改善 pulse 图在 notebook / artifact 输出中的可读性与紧凑性。

## 2. 范围
- In Scope：
  - 为 `plot_pulses(...)` 增加 `XYZ_line_combine` 开关参数。
  - timing layout 模式下支持 `XY_i + Z_i -> XYZ_i` 的并线显示。
  - DXF 导出跟随相同布局策略。
  - pulse metadata 保留原始来源通道名，不因显示合并而丢失语义。
  - 对缺失 `XY_i` 或缺失 `Z_i` 的情况做兼容。
- Out of Scope：
  - 修改 PulseIR schema。
  - 修改 lowering / compiler / backend 对通道的物理语义定义。
  - 引入新的真实硬件通道类型 `XYZ_i`。

## 3. 输入与输出（I/O）
- 输入：
  - `pulse_ir: PulseIR`
  - `plot_pulses(..., timing_layout=True, XYZ_line_combine=True | False)`
- 输出：
  - matplotlib timing figure
  - 可选 `pulse_timing.png`
  - 可选 `timing_diagram.dxf`
  - 可选 `pulse_metadata.json`
- schema/version：
  - 不修改 `PulseIR` 结构。
  - `pulse_metadata` schema 保持兼容，仍记录原始 `channel` 字段值，如 `XY_0`、`Z_0`。

## 4. 技术方案
- 方案概述：
  - 在 `plot_pulses()` 新增参数：
    - `XYZ_line_combine: bool = False`
  - 在 timing layout 渲染路径中，根据 `XYZ_line_combine` 构造“显示行”而不是直接逐个 `pulse_ir.channels` 绘制。
- 关键设计决策：
  - 该能力只应是显示层变换，不应修改输入 `PulseIR`。
  - `XYZ_line_combine=False` 保持当前行为，作为默认值保证兼容性。
  - `XYZ_line_combine=True` 时，仅对符合 `XY_i` / `Z_i` 命名规则的通道进行配对合并。
  - O_i`、`TC_i` 及其他未知命名通道继续单独显示。
- 可替换点/扩展点：
  - 可在 `src/qsim/pulse/visualize.py` 内新增内部 helper，例如：
    - `_build_display_rows(...)`
    - `_group_xy_z_channels(...)`
  - 如果后续需要，还可扩展为更多布局模式，如 `qubit`、`physical`、`compact`。

## 5. 任务拆分
1. 梳理 timing layout 当前逐行绘制逻辑，抽离“显示行构建”步骤。
2. 为 `plot_pulses()` 增加 `XYZ_line_combine` 参数及文档说明。
3. 实现 `False` / `True` 两种显示行策略。
4. 让 matplotlib timing 渲染与 DXF 导出共用同一套布局决策。
5. 确保 metadata 输出仍保留原始通道语义。
6. 增加单元测试与回归测试。

## 6. 验收标准（DoD）
- [ ] 默认不传 `XYZ_line_combine` 时，行为与当前完全一致。
- [ ] `XYZ_line_combine=False` 时，`XY_i` / `Z_i` 继续分线显示。
- [ ] `XYZ_line_combine=True` 时，`XY_i` / `Z_i` 合并为一个显示行，标签为 `XYZ_i`。
- [ ] 缺失一侧通道时不报错，仍能正常渲染。
- [ ] O_i`、`TC_i`、其他非 XY/Z 通道不受影响。
- [ ] DXF 导出与 matplotlib 输出使用一致布局。
- [ ] metadata 输出仍保留原始 `XY_i` / `Z_i` 通道名。
- [ ] 现有 notebook / workflow 调用不需要修改即可继续工作。

## 7. 测试计划
- 单元测试：
  - `XYZ_line_combine=False` 时显示行构造正确。
  - `XYZ_line_combine=True` 时 `XY_i` / `Z_i` 正确配对。
  - 仅有 `XY_i` 或仅有 `Z_i` 时兼容。
- 集成测试：
  - 对一个包含 `XY_0`、`Z_0`、O_0` 的 `PulseIR` 生成 timing figure，验证布局结果。
  - 在启用 DXF 导出时验证不报错且输出成功。
- 回归测试：
  - 现有 `plot_pulses(..., timing_layout=True)` 路径保持兼容。
- 样例调用：
  - `plot_pulses(pulse_ir, timing_layout=True, XYZ_line_combine=False)`
  - `plot_pulses(pulse_ir, timing_layout=True, XYZ_line_combine=True)`

## 8. 风险与回滚
- 主要风险：
  - 当前 `_plot_pulses_timing()` 内部逻辑直接依赖 `pulse_ir.channels` 顺序，改造时可能影响标签、metadata 编号、行高计算。
  - DXF 导出若隐式依赖 matplotlib 图元结构，合并显示后可能出现布局不一致。
- 缓解：
  - 将“显示行”抽象清晰，避免在多个位置重复分支。
  - 先保证 `XYZ_line_combine=False` 路径输出不变，再增加 `XYZ_line_combine=True` 路径测试。
- 回滚：
  - 若并线模式稳定性不足，可仅保留参数接口并暂时隐藏该模式，或将其 behind feature flag。

## 9. 依赖与阻塞
- 前置依赖：
  - `src/qsim/pulse/visualize.py` 当前 timing layout 逻辑稳定。
- 外部依赖：
  - 无新增外部依赖。
- 潜在阻塞：
  - 若现有测试覆盖不足，需要补最小化 `PulseIR` 构造样例。
  - 若 DXF 导出路径与 matplotlib 图元提取耦合较深，可能需要额外整理。

## 10. 估时与优先级
- 优先级：P1
- 预计工期：0.5 - 1 天
- 负责人：待指派

## 11. 参考
- `src/qsim/pulse/visualize.py`
- `src/qsim/ui/notebook.py`
- `issues/ISSUE_TEMPLATE.md`
- `issues/ISSUE_DYN_P0_TRI_ENGINE_DYNAMICS_FULLSTACK.md`

