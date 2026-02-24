* 电路：充分利用 **Qiskit / QASM**（输入输出标准化）
* 脉冲：支持 **Gaussian / Rect / DRAG** 等常用波形
* 可视化：Notebook 友好 + 工程图输出（复用你现有的 `pulse_drawer.py` 风格/接口） 
* 计算引擎：可插拔调用 **QuTiP / QuantumToolbox.jl / QuantumOptics.jl**
* 接口：每一步的输入/输出明确、可版本化、便于后期替换算法

---

## 0. 总体目标：一套“会话驱动 + 可插拔后端 + 可复现产物”的工作流

**核心对象：Project Session（会话）**
每次用户修改电路/配置/分析方法，都产生可追溯的版本；任何计算产物都能从 manifest 复现。

---

## 1. 实体泳道（你最终图里就画这 4 条）

1. **用户（Notebook/CLI/GUI）**
2. **后端 Backend（编译+建模+求解调用+分析+可视化产物生成）**
3. **数据与版本库（Artifacts Store）**
4. **实验系统（可选外循环）**

> “数值运行时/算力池”不单独成泳道：作为 Backend 内部的 `ComputePool.submit()/fetch()` 来画箭头即可。

---

## 2. 统一数据接口与目录（Codex 直接照着建工程）

### 2.1 目录建议（最小但可扩展）

```
qsim/
  src/qsim/
    session/
      session.py
      manifest.py
      store.py
    circuit/
      import_qasm.py
      import_qiskit.py
      normalize.py
      export_qasm.py
    backend/
      config.py
      compile_pipeline.py
      lowering.py
      model_build.py
      pulse_compile.py
    pulse/
      primitives.py
      shapes.py        # rect/gaussian/drag
      sequence.py
      visualize.py     # notebook plotting
      drawer_adapter.py# call pulse_drawer-like exporter
    engines/
      base.py
      qutip_engine.py
      julia_qtoolbox.py
      julia_qoptics.py
    analysis/
      passes.py
      observables.py
      error_budget.py
      registry.py      # user-defined analysis plugins
    ui/
      notebook.py
      cli.py
  examples/
  tests/
  pyproject.toml
```

### 2.2 统一产物（Artifacts）类型：全部带 `schema_version`

所有产物都用 **JSON 头 + NPZ/HDF5 数据**的方式（Notebook 友好、工程可追溯）：

* `circuit.qasm`（或 `circuit.json` 作为内部 IR）
* `backend.yaml`（仿真配置）
* `hardware.json / noise.json`（数字孪生参数）
* `pulse_ir.json`（脉冲描述） + `pulse_samples.npz`（可选采样）
* `model_spec.json`（物理模型描述）
* `trace.h5`（演化结果/轨迹）
* `observables.json`（观测量）
* `report.json`（误差预算/诊断报告）
* `run_manifest.json`（本次运行的全部指纹：版本、hash、依赖、随机种子、输入输出引用）

---

## 3. 工作流（完整步骤 + 输入输出接口 + 可替换点）

下面每一步都给出 **输入/输出**，并标出**后期可替换算法**的接口（你说的“后期加入算法替代老版本”就是靠这些稳定接口）。

---

### Step A：会话创建/加载（User → Backend → Store）

**输入：**

* `task.yaml`（可选）：任务描述（目标门、目标观测量、跑多少点、随机种子策略）

**输出：**

* `session_id`
* `run_ctx`（当前工作上下文：当前电路版本/配置版本/硬件版本/分析管线版本）

**稳定接口：**

* `Session.open(path)->Session`
* `Session.commit(kind, payload)->rev_id`
* `Session.get(rev_id)->artifact_ref`

---

### Step B：电路输入（QASM/Qiskit）与内部表示（User → Backend）

你要求“充分利用 qiskit、qasm”，所以电路层接口定死：

**B1：导入**

* **输入（之一）：**

  * `circuit.qasm`（OpenQASM 2 或 3，优先 3）
  * 或 `qiskit.QuantumCircuit`（Python对象）
* **输出：**

  * `CircuitIR.json`（内部稳定 IR，平台无关）

**稳定接口：**

* `CircuitAdapter.from_qasm(str)->CircuitIR`
* `CircuitAdapter.from_qiskit(qc)->CircuitIR`
* `CircuitAdapter.to_qasm(CircuitIR)->str`

> 你后期替换“解析/规范化/优化算法”，只要 `CircuitIR` schema 不变即可。

---

### Step C：后端配置（User ↔ Backend）

**输入：**

* `backend.yaml`（强烈建议 schema 固化）

最关键字段（建议你就按这个写）：

* `level`: `qubit | cqed | io`
* `noise`: `deterministic | lindblad | sde | tls | hybrid`
* `solver`: `se | me | mcwf | io`
* `analysis_pipeline`: `default | custom:<name>`
* `truncation`: `{ transmon_levels, cavity_nmax, ... }`
* `sweep`: 参数扫描定义（可选）

**输出：**

* `BackendConfig.json`（校验后的结构化配置）

**稳定接口：**

* `BackendConfig.load(yaml_path)->BackendConfig`
* `BackendConfig.validate()->None`

---

### Step D：后端编译流水线（Backend 内部：编译与规划）

这一段你强调应该在后端：✅

#### D1 电路规范化 / 编译 pass pipeline

**输入：**

* `CircuitIR.json`
* `BackendConfig.json`
* （可选）`hardware.json`（如果做硬件相关的映射/路由）

**输出：**

* `NormalizedCircuitIR.json`
* `compile_report.json`（pass记录、门数变化、路由信息）

**可替换点（算法替代）：**

* `ICircuitPass`：`run(CircuitIR, ctx)->CircuitIR`

#### D2 拓扑映射与调度（可选）

**输入：**

* `NormalizedCircuitIR.json`
* `hardware.json`（拓扑/耦合/约束）

**输出：**

* `Schedule.json`（门时序、并行分组、资源占用）

**可替换点：**

* `IScheduler`: `schedule(circuit, hardware, config)->Schedule`

---

### Step E：执行语义映射（Lowering）→ 脉冲与模型骨架（Backend）

你要的“Lowering 不等于配置”，这里明确：Lowering 是把抽象电路绑定到执行语义。

**输入：**

* `Schedule.json`（或 `NormalizedCircuitIR.json`）
* `BackendConfig.json`
* `hardware.json / noise.json`

**输出（两类都要支持）：**

1. **脉冲级：**

   * `pulse_ir.json`（结构化脉冲序列）
2. **模型级：**

   * `ExecutableModel.json`（执行模型骨架：H(t)构造方式、耦合项、噪声项、IO开关等）

**可替换点：**

* `ILowering`: `lower(schedule, hw, cfg)->(PulseIR, ExecutableModel)`

---

## 4. 脉冲波形与序列接口（必须支持 Gaussian/Rect/DRAG）

这里建议你把 `PulseIR` 定成稳定 schema，这样后期换 pulse compiler 不影响上层。

这里波形要仔细设计，最好有专门的类或者模板（我不懂具体的），要能够反映多种波形的参数，比如抖动幅度，量子化台阶，上升沿下降沿这些，让用户可以方便修改或者加入实际情况进行调整。

### 4.1 PulseIR（建议字段）

* `Sequence`

  * `t_end`
  * `channels[]`

    * `name`（XY、Z、RO、CLK…）
    * `pulses[]`

      * `t0, t1`
      * `amp`
      * `shape`: `rect | gaussian | drag | dc | readout`
      * `carrier`: `{freq, phase}`（可选）
      * `params`: shape-specific（例如 drag 的 beta、sigma）

### 4.2 shape 支持（最少集）

* `rect`: 方波（支持 rise/fall 可选）
* `gaussian`: 高斯包络
* `drag`: Gaussian + 导数项（beta 参数）
* `readout`: 通常 rect + carrier（你现有 drawer 支持 envelope+carrier，很合适） 

**稳定接口：**

* `PulseShape.sample(t)->float`
* `PulseCompiler.compile(PulseIR, sample_rate)->WaveformSamples`

---

## 5. 工程图输出与 Notebook 可视化（两条输出线都要）

你要求“输出既要 notebook 友好，也要工程图”，所以分两条线：

### 5.1 Notebook 可视化（Backend → User）

**输入：**

* `pulse_ir.json` 或 `pulse_samples.npz`
* `trace.h5`
* `observables.json`

**输出：**

* matplotlib/plotly 图对象（不落盘也行）
* 或 `figures/` 下的 PNG/SVG

**稳定接口：**

* `viz.plot_pulses(PulseIR, ...)`
* `viz.plot_trace(trace, ...)`

### 5.2 工程图导出模块（类似 pulse_drawer.py）

你已有一个成熟的 DXF 生成器：它的数据模型 `Sequence/Channel/Pulse/Carrier` 与“包络+载波、break marker、baseline、刻度”等都非常工程化。建议直接把它变成后端的一个 exporter 适配器。

**输入：**

* `PulseIR`（转换成 `pulse_drawer.Sequence`）
* 绘图参数（scale、row_gap、breaks、ticks等）

**输出：**

* `timing_diagram.dxf`（可进一步转 SVG/PDF）

**稳定接口：**

* `EngineeringDrawer.export_dxf(PulseIR, path, style)->path`

并且实现层直接复用你这个文件的 `render_sequence_to_dxf()` 逻辑。 

---

## 6. 物理模型构造（Backend）与求解（算力池调用）

### 6.1 model_spec（可执行物理模型描述）

**输入：**

* `ExecutableModel.json`
* `hardware.json / noise.json`
* （可选）`pulse_samples.npz`（如果用离散驱动）

**输出：**

* `model_spec.json` + （可选）矩阵/算符数据（npz/h5）

**可替换点：**

* `IModelBuilder.build(executable, hw, noise)->ModelSpec`

### 6.2 求解提交（Backend 内部的 ComputePool）

**输入：**

* `model_spec.json`

**输出：**

* `trace.h5`（或 `trace_uri`）

**稳定接口（关键，保证可替换引擎）：**

* `Engine.run(model_spec, run_options)->TraceRef`

并行支持这些实现：

* `QuTiP`（Python）：`mesolve/mcsolve/sesolve`
* `QuantumToolbox.jl`（Julia）
* `QuantumOptics.jl`（Julia）

> 后期你替换/新增算法（比如更快的 MCWF、张量网络、surrogate model），只需要实现同一个 `Engine` 接口，保持 `Trace` schema 不变。

---

## 7. 观测量计算、误差预算、用户可插拔分析（Backend + User 交互）

你要求分析阶段允许用户“随时提出新的数据分析方法”，所以设计成 **analysis pass registry**：

### 7.1 默认分析管线（Backend）

**输入：**

* `trace.h5`
* `model_spec.json`
* `BackendConfig.analysis_pipeline`

**输出：**

* `observables.json`
* `report.json`（误差预算/诊断）

### 7.2 用户插拔分析（User ↔ Backend）

**输入：**

* 用户提供 `analysis_pass.py` 或 notebook 中注册的函数
* 以及 `trace_uri`

**输出：**

* 新的 `analysis_rev`（分析管线版本）
* 新的 `report.json`

**稳定接口：**

* `AnalysisRegistry.register(name, callable, schema_in, schema_out)->analysis_rev`
* `AnalysisRunner.run(trace, pipeline)->report`

---

## 8. 一句话版本的完整闭环（给你放在流程图底部）

**用户编辑电路/配置 → 后端编译(规范化/映射/Lowering) → 生成 PulseIR/ModelSpec → 求解引擎(可插拔) → trace → 分析(可插拔) → 可视化/工程图导出 → 用户基于结果继续修改；实验数据可更新硬件/噪声参数进入外循环。**

---

## 9. 你交给 Codex 的“生成代码要求清单”（建议直接粘贴）

1. 建立上述目录结构与模块骨架
2. 定义稳定 schema（dataclass + JSON 序列化）：

   * `CircuitIR`, `BackendConfig`, `PulseIR`, `ExecutableModel`, `ModelSpec`, `Trace`, `Observables`, `Report`, `RunManifest`
3. 电路输入输出：

   * `from_qasm / to_qasm`
   * `from_qiskit / to_qiskit`（可选）
4. 脉冲波形支持：`rect/gaussian/drag/readout`，可采样生成数组
5. 工程图导出：提供 `EngineeringDrawer.export_dxf()`，内部适配并调用现有 `render_sequence_to_dxf()` 
6. 引擎接口 `Engine.run()` + 三个实现：

   * `qutip_engine`
   * `julia_quantumtoolbox`
   * `julia_quantumoptics`
7. 分析接口 `AnalysisPass` + `AnalysisRegistry`，允许用户注册新分析方法并版本化
8. Notebook 可视化：脉冲、trace、report 的基础绘图函数
9. 所有运行必须生成 `run_manifest.json`，记录输入版本、依赖版本、随机种子、产物引用
