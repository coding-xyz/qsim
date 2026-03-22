# 可视化

本页说明 `qsim` 当前提供的可视化能力，包括 workflow 自动导出的图像、Notebook 中的默认绘图接口，以及 `qsim.pulse.visualize` 模块中可直接调用的绘图函数。对于需要检查脉冲时序、trace 结果或分析图的用户，这一页可以作为使用说明书。

## 1. 可视化能力概览

`qsim` 当前的可视化主要分为两类：

- workflow 运行结束后自动导出的图像
- Python 中手动调用的绘图函数

它们主要由以下模块提供：

- `src/qsim/workflow/pipeline.py`
- `src/qsim/workflow/persistence.py`
- `src/qsim/pulse/visualize.py`
- `src/qsim/ui/notebook.py`

## 2. workflow 自动导出哪些图像

当 `task.output.export_plots` 或 `task.output.export_dxf` 开启时，workflow 会在结果目录中自动写出常见图像文件。

常见输出包括：

- `pulse_timing.png`
- `trace.png`
- `report.png`
- `timing_diagram.dxf`

这些文件是否生成，取决于：

- 当前任务是否产生了对应的数据对象
- `export_plots` 是否为 `true`
- `export_dxf` 是否为 `true`
- 对应依赖是否已安装

## 3. 图像文件分别表示什么

### `pulse_timing.png`

展示 PulseIR 对应的时序图。  
它适合检查：

- 各通道脉冲是否按预期出现
- readout/reset 区段的时间结构
- 是否存在明显的时序异常

### `trace.png`

展示求解器输出的 trace 相关结果。  
它适合快速观察：

- 时间轴上的状态变化
- 最终激发概率趋势
- 不同任务设置下的整体响应差异

### `report.png`

展示 analysis 阶段生成的报告型图像。  
它更适合在完成 logical error 或 sensitivity 分析后用于结果浏览。

### `timing_diagram.dxf`

将时序图导出为工程绘图格式，适合：

- 后续在 CAD 或工程工具中查看
- 与实验或硬件设计侧对接
- 需要更正式、可编辑的时序图输出

## 4. Notebook 中的默认绘图接口

在 notebook 或脚本中，最方便的默认入口是：

- `qsim.ui.notebook.plot_default(result)`

它接收 `run_task()` 或 `run_task_files()` 的返回结果，并返回一个图对象字典：

- `pulses`
- `trace`
- `report`

典型用法：

```python
from qsim.workflow import run_task_files
from qsim.ui.notebook import plot_default

result = run_task_files(task_config="tasks/simulate_trace.yaml")
figs = plot_default(result)
figs["pulses"].savefig("pulse_timing.png", dpi=180)
```

这个接口适合：

- notebook 中快速查看结果
- 调试某次运行的图像表现
- 在自动化脚本里补充自定义导出

## 5. `qsim.pulse.visualize` 提供的主要函数

当前较常用的函数包括：

- `plot_pulses(...)`
- `plot_trace(...)`
- `plot_report(...)`
- `auto_break_idle_windows(...)`
- `auto_break_long_pulses(...)`
- `make_timing_theme(...)`
- `export_json_table(...)`

这些函数覆盖了从时序图绘制到表格导出的主要可视化流程。

## 6. 时序图的核心特性

当前时序图实现支持以下能力：

- timing layout
- 长空闲区间折叠
- 长 readout / reset 脉冲折叠
- 黑白工程图风格
- DXF 导出
- 脉冲编号标注
- pulse metadata 导出

这些能力使它既适合用于算法侧调试，也适合用于工程展示。

## 7. 手动生成脉冲时序图

如果不想走完整 workflow，也可以直接用 `pulse.visualize` 生成脉冲图。仓库中的 [pulse_timing_visual_check.py](d:\超导量子计算机噪声抑制\qsim\examples\pulse_timing_visual_check.py) 就是一个典型示例。

核心流程大致如下：

1. 准备 QASM 和 backend 配置
2. 调用 `pulse_ir_from_qasm(...)` 生成 `PulseIR`
3. 调整通道顺序
4. 自动识别长脉冲折叠区间
5. 调用 `plot_pulses(...)` 输出 PNG 和 DXF

示例：

```python
from qsim.pulse.visualize import (
    auto_fold_long_pulses,
    make_timing_theme,
    plot_pulses,
    pulse_ir_from_qasm,
    reorder_xy_z_channels,
)

pulse_ir = pulse_ir_from_qasm(
    qasm_text,
    backend_config=backend_path,
    hardware={
        "xy_freq_Hz": 5.0e9,
        "ro_freq_Hz": 8.0e9,
        "gate_duration_ns": 20.0,
        "measure_duration_ns": 2000.0,
    },
)
pulse_ir = reorder_xy_z_channels(pulse_ir)
breaks = auto_fold_long_pulses(pulse_ir, channel_prefixes=("RO",))
theme = make_timing_theme(break_display_gap_ns=16.0)

plot_pulses(
    pulse_ir,
    timing_layout=True,
    title="demo",
    show_clock=True,
    breaks=breaks,
    dxf_path="timing_diagram.dxf",
    png_path="timing_python.png",
    theme=theme,
    pulse_metadata_path="pulse_metadata.json",
)
```

## 8. `plot_pulses(...)` 适合什么时候用

当你关心以下问题时，建议直接看 `plot_pulses(...)`：

- 某个门被 lowering 成了哪些脉冲
- 各个通道的脉冲排列是否合理
- readout / reset 区段是否过长
- 某些脉冲是否需要折叠显示

它最适合做结构检查，不一定用于最终物理结论判断。

## 9. 图像导出之外的表格导出

`export_json_table()` 可以把 JSON 记录展平成 CSV 或 XLSX，适合把脉冲元数据或其他结构化记录导出为表格。

示例：

```python
from qsim.pulse.visualize import export_json_table

export_json_table("pulse_metadata.json", "pulse_metadata.csv")
export_json_table("pulse_metadata.json", "pulse_metadata.xlsx")
```

其中：

- `.csv` 基本不需要额外依赖
- `.xlsx` 需要安装 `openpyxl`

## 10. 推荐使用顺序

如果你是第一次检查图像输出，建议按以下顺序：

1. 先在 workflow 中打开 `export_plots`
2. 查看 `pulse_timing.png`
3. 查看 `trace.png`
4. 需要工程图时再打开 `export_dxf`
5. 需要表格化分析时导出 `pulse_metadata.json` 并转成 CSV/XLSX

这样可以避免一开始就把所有可视化功能同时打开，导致调试成本过高。

## 11. 常见问题

### 为什么没有导出图像

优先检查：

- `task.output.export_plots` 是否为 `true`
- 当前任务是否真的生成了可绘图对象
- matplotlib 等可视化依赖是否已安装

### 为什么没有 DXF

优先检查：

- `task.output.export_dxf` 是否为 `true`
- `ezdxf` 是否已安装

### 为什么时序图里 readout 很长

这通常与 `measure_duration_ns` 等读出参数有关。  
如果只是想让图更容易读，可以配合长脉冲折叠功能一起使用。
