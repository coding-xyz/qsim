# [DYN-P0] 打通量子-经典耦合读出链：input-output / IQ 判别 / task2 SPAM 有效跑通

## 0. 状态
- 状态：Failed
- 负责人：待指派
- 更新时间：2026-03-30
- 备注：被 `ISSUE_UI_P0_MODEL_OBJECT_API_AND_SOLVER_ANALYSER_SPLIT.md` 覆盖，当前不再单独推进。

## 1. 背景与目标
- 背景：
  - 当前 `task2` 已能以 `cqed_jc` 形式运行 `1 transmon (3 levels) + 1 resonator` 的量子动力学，并可输出密度矩阵、population、mean_excited、variance。
  - 但 `readout_line` 目前仅作为设备元数据存在，未进入任何真实演化或后处理链路。
  - [examples/noise_simulation_tests/task2/solver.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/solver.yaml) 中已写入 `cavity_equation`、`output_equation`、`iq_discrimination`、`noise_analysis` 等字段，但当前代码并未消费这些字段，属于占位配置。
  - 现状导致 `task2` 只能“跑完量子部分”，不能完成用户真正需要的“量子-经典耦合读出、读出线信号生成、IQ 判别、SPAM/噪声分析”。
- 目标：
  - 在现有 `qubit + cavity` 量子动力学基础上，增加与 `readout_line` 对应的经典读出链建模。
  - 显式支持 input-output 关系，至少能从腔场生成 `a_out(t)` 或等效读出电压。
  - 基于读出链输出生成 `I(t)`、`Q(t)`、积分 IQ 样本、分类结果和读出误差指标。
  - 确保 `task2` 能有效跑通并产出可解释的 SPAM/readout 分析结果，而非仅有占位字段。
- 为什么现在做：
  - 这是用户当前明确提出的核心需求。
  - 这是后续更复杂的读出保真度、误差预算、状态制备验证和实验对标的前置能力。

## 2. 范围
- In Scope：
  - 为 `task2` 引入量子-经典耦合读出链的最小可用实现。
  - 支持 `transmon (3 levels) + single cavity mode + classical readout line`。
  - 支持由 `pulse.acquisition` 和 `solver.analysis.readout_model` 驱动的读出后处理。
  - 支持单比特校准态 `|1>`、`|+>`、`|->` 的 IQ 样本生成与分类分析。
  - 为 notebook / workflow 持久化增加与读出链相关的产物。
- Out of Scope：
  - 多模谐振腔、分布式传输线或全 Maxwell 级别仿真。
  - 完整实验室测控栈仿真（混频器非理想、滤波器群时延、ADC 量化误差等）。
  - 多比特联合 readout 与串扰校正。

## 3. 输入与输出（I/O）
- 输入：
  - [examples/noise_simulation_tests/task2/device.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/device.yaml)
    - `transmon`
    - `resonator`
    - `readout_line`
    - `jc` / `dispersive` / `readout_feedline` 连接
  - [examples/noise_simulation_tests/task2/pulse.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/pulse.yaml)
    - `readout_drive`
    - `readout_lo`
    - `acquisition`
  - [examples/noise_simulation_tests/task2/solver.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/solver.yaml)
    - `readout_model`
    - `input_output`
    - `iq_discrimination`
    - `noise_analysis`
  - [examples/noise_simulation_tests/task2/task.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/task.yaml)
    - `|1>`、`|+>`、`|->` 制备与测量序列
- 输出：
  - 现有 `trace` 和 `metrics`
  - 新增 `readout_trace` 类产物，至少包含：
    - `a_in(t)`
    - `a_cavity(t)` 或等效腔场代理量
    - `a_out(t)`
    - `I(t)`
    - `Q(t)`
    - integration window 信息
  - 新增 `iq_analysis` 类产物，至少包含：
    - 每次制备的积分 IQ 点
    - centroid
    - classifier config
    - confusion matrix
    - assignment fidelity
    - SNR / cluster separation
  - `task2_spam.ipynb` 可直接读取上述产物作图与分析
- schema / version：
  - 延续 `schema_version: 3.0`
  - 若需新增 artifact schema，采用独立 `v1` JSON 结构并在 `run_manifest` 中注册

## 4. 技术方案
- 方案概述：
  - 第一阶段不把 `readout_line` 作为新的量子 Hilbert 空间自由度塞进 `cqed_jc`。
  - 保持动力学求解主体仍为 `qubit + cavity`，在演化结束后增加一个显式的“经典读出链 stage”。
  - 该 stage 消费腔场相关可观测量与读出配置，生成 `a_out(t)` 与 IQ 产物。
- 关键设计决策：
  - 决策 1：`readout_line` 在 v1 中建模为“经典后处理子系统”，而不是新的量子模。
    - 原因：这样改动面最小，能先让 `task2` 真正可用。
    - 代价：不能声称已经完成“全量子化的传输线自由度”建模。
  - 决策 2：优先实现 input-output 等效关系而不是全新 solver。
    - 原因：用户需求的核心是读出线信号、IQ 判别和 SPAM 跑通。
  - 决策 3：将 `solver.analysis.readout_model`、`pulse.acquisition` 从“占位配置”升级为真实可消费配置。
    - 原因：避免 task2 配置与代码能力长期脱节。
- 具体落点：
  - `workflow/task_io.py`
    - 明确保留 `readout_model` / `iq_discrimination` / `noise_analysis` 配置
  - `backend/model_build.py`
    - 将 `readout_line`、`readout_feedline`、`kappa_ext`、`chi` 等信息归一化到可消费 payload
  - `engines/qutip_engine.py`
    - 暴露腔场相关期望值或足够恢复读出信号的 observable
  - `workflow/stages.py`
    - 新增 readout analysis stage
    - 计算 `a_out(t)`、`I/Q`、积分 IQ 和分类指标
  - `workflow/persistence.py` / `workflow/output.py`
    - 落盘 `analysis_readout.json`、`analysis_iq.json` 或等价工件
  - `examples/noise_simulation_tests/task2_spam.ipynb`
    - 改为直接展示 task2 的读出轨迹、IQ 云图和分类结果
- 可替换点 / 扩展点：
  - 未来若要做严格量子-经典混合求解，可把 readout stage 替换为更底层的 mixed-domain engine。

## 5. 固定流程
1. 先完成代码修改与必要测试。
2. 同步检查并补全相关 `docstring`。
3. 同步更新 `docs/` 下对应文档内容。
4. 若 `docs/site/` 为构建产物，则优先修改 `docs/src/` 或文档源文件，不直接手改生成结果。
5. 提交前确认 issue 中的“文档更新”和“docstring 更新”条目已勾选。

## 6. 任务拆分
1. 复盘 `task2` 当前配置与代码链路，标出哪些字段未被消费。
2. 定义 `readout_line` 在 v1 中的 canonical runtime contract。
3. 扩展 `model_build` 与 engine 输出，获得读出链所需的腔场可观测量。
4. 实现 input-output 读出 stage，生成 `a_out(t)` 和读出时域信号。
5. 实现异频解调、积分窗、IQ 样本与分类。
6. 产出 SPAM/readout 指标并完成持久化。
7. 更新 notebook、示例说明与测试，确保 `task2` 可以端到端复现。

## 7. 验收标准（DoD）
- [ ] `task2` 不再只是“量子部分跑完”，而是能真实产出读出链相关工件
- [ ] `solver.yaml` 中的 `readout_model` / `input_output` 字段被代码实际消费
- [ ] `device.yaml` 中的 `readout_line` 不再只是 metadata，而是参与经典读出链计算
- [ ] 产出 `a_out(t)` 或等价读出输出信号，并能保存为结构化结果
- [ ] 产出 `I(t)` / `Q(t)` 和积分 IQ 样本
- [ ] `|1>`、`|+>`、`|->` 三类制备态可以生成可区分的 IQ 分布或 centroid
- [ ] 可输出 confusion matrix、assignment fidelity、SNR 或 cluster separation
- [ ] `task2_spam.ipynb` 能直接读取工件完成图示与分析
- [ ] 相关 `docstring` 已新增或更新
- [ ] `docs/` 下对应文档已新增或更新

## 8. 测试计划
- 单元测试：
  - input-output 公式实现与参数映射
  - IQ 解调与积分窗口逻辑
  - classifier / confusion matrix 构建逻辑
- 集成测试：
  - `python examples/noise_simulation_tests/task2/run.py`
  - 验证新增工件存在且 schema 正确
  - 验证 `task2` 输出中包含 readout / IQ / classification 结果
- 回归测试：
  - 现有 `qutip` 动力学任务不退化
  - 未启用 readout analysis 的任务路径保持兼容

## 9. 风险与回滚
- 主要风险：
  - 仅基于 `qubit + cavity` 的后处理方案在物理上是“有效近似”，但不是完整读出线动力学。
  - `|+>`、`|->` 在单次标准色散读出下未必天然比 `|0>`、`|1>` 更容易分离，可能需要明确其分析意义是“SPAM 诊断”而非“Z 基直读”。
- 缓解策略：
  - 在文档与结果元数据中明确说明 v1 的物理近似边界。
  - 以 `|1>`、`|+>`、`|->` 作为状态制备与读出响应示例，而不是宣称它们都可直接高保真单次判别。
- 回滚策略：
  - 若新增 readout stage 出现不稳定，可通过配置开关禁用，保留现有 `cqed_jc` 动力学主路径。

## 10. 依赖与阻塞
- 前置依赖：
  - 现有 `task2` 的 `cqed_jc` 路径可稳定运行
  - `task2` YAML 结构保持为当前版本
- 外部依赖（库 / 环境 / 数据）：
  - 当前主要依赖本地 Python / QuTiP 环境，无新增外部运行时强依赖
- 潜在阻塞：
  - 现有 engine 输出未暴露足够的腔场 observable，可能需要补充新的 trace/metadata 通道

## 11. 估时与优先级
- 优先级：P0
- 预计工期：3-5 天
- 负责人：待指派

## 12. 参考
- [examples/noise_simulation_tests/task2/task.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/task.yaml)
- [examples/noise_simulation_tests/task2/device.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/device.yaml)
- [examples/noise_simulation_tests/task2/pulse.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/pulse.yaml)
- [examples/noise_simulation_tests/task2/solver.yaml](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2/solver.yaml)
- [examples/noise_simulation_tests/task2_spam.ipynb](/d:/超导量子计算机噪声抑制/qsim/examples/noise_simulation_tests/task2_spam.ipynb)
- [src/qsim/backend/model_build.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/model_build.py)
- [src/qsim/engines/qutip_engine.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/engines/qutip_engine.py)
- [src/qsim/workflow/stages.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/workflow/stages.py)
