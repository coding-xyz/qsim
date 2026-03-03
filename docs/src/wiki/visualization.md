# 可视化

本页说明脉冲可视化模块 `qsim.pulse.visualize` 的推荐用法，包含：

- OpenQASM -> `PulseIR` 翻译
- matplotlib 时序图渲染
- DXF 工程图导出（与 matplotlib 图元一致）
- 脉冲编号 `p1/p2/...` 与参数 JSON 导出

## 主要入口

- `pulse_ir_from_qasm(...)`
- `plot_pulses(...)`
- `auto_fold_long_pulses(...)`
- `reorder_xy_z_channels(...)`

## 一般工作流

1. 准备 QASM 文本和 backend 配置（YAML）。
2. 调用 `pulse_ir_from_qasm(...)` 得到 `PulseIR`。
3. 用 `reorder_xy_z_channels(...)` 调整通道顺序（`XY_0, Z_0, XY_1, Z_1, ...`）。
4. 用 `auto_fold_long_pulses(...)` 生成断点（常用于 `RO` 长脉冲）。
5. 调用 `plot_pulses(..., timing_layout=True, dxf_path=...)` 同时产出 PNG + DXF。

## 关键特性

- 黑白风格与 Times New Roman 字体
- 顶部 `CLK` 方波（100 MHz，可配）
- 断点折叠（所有通道与时间轴一致折叠）
- 载波虚线仅在存在高频脉冲区间绘制
- 每个脉冲可自动打标签：`p1, p2, ...`
- 可导出 `pulse_metadata.json`，记录脉冲参数明细

## `plot_pulses` 关键参数

- `timing_layout=True`：开启时序图模式
- `breaks=[(t0, t1), ...]`：指定折叠区间
- `show_clock=True`, `clock_mhz=100.0`：绘制时钟通道
- `carrier_plot_max_hz=0.5e9`：高频可视化上限
- `dxf_path=...`：导出 DXF
- `dxf_from_figure=True`：从 matplotlib figure 直接抽取图元，保证一致性
- `annotate_pulses=True`：显示 `p1/p2/...`
- `pulse_metadata_path=...`：输出脉冲参数 JSON

## 示例

```python
from pathlib import Path
from qsim.pulse.visualize import (
    auto_fold_long_pulses,
    plot_pulses,
    pulse_ir_from_qasm,
    reorder_xy_z_channels,
)

qasm_text = Path("input.qasm").read_text(encoding="utf-8")
pulse_ir = pulse_ir_from_qasm(
    qasm_text,
    backend_config="backend.yaml",
    hardware={
        "xy_freq_hz": 5.0e9,
        "ro_freq_hz": 8.0e9,
        "gate_duration": 20.0,
        "measure_duration": 2000.0,
    },
)
pulse_ir = reorder_xy_z_channels(pulse_ir)
breaks = auto_fold_long_pulses(pulse_ir, channel_prefixes=("RO",))

fig = plot_pulses(
    pulse_ir,
    timing_layout=True,
    title="SINGLE QUBIT CPMG",
    show_carrier=True,
    show_clock=True,
    breaks=breaks,
    dxf_path="timing_diagram.dxf",
    annotate_pulses=True,
    pulse_metadata_path="pulse_metadata.json",
)
fig.savefig("timing_python.png", dpi=180)
```

## Recent Updates (Timing / Reset / Table Export)

### 1) Denser time ticks

`plot_pulses(..., timing_layout=True)` now accepts `target_ticks`:

```python
fig = plot_pulses(
    pulse_ir,
    timing_layout=True,
    target_ticks=18,  # denser major ticks on the custom time axis
)
```

### 2) Reset pulse semantics

`reset` lowering is measurement-driven and does **not** use pi/2 feedback:

- `RO_*` `reset_measure`
- `RO_*` `reset_deplete`
- latency window
- optional conditional `pi` pulse on `XY_*` (`reset_conditional_pi`)

Control with hardware knob:

```python
hardware = {
    "reset_apply_feedback": True,   # default
    # False -> keep measurement/depletion path only
}
```

### 3) JSON to CSV / XLSX export

Use `export_json_table` to flatten JSON records (including nested dict fields):

```python
from qsim.pulse.visualize import export_json_table

export_json_table(
    "runs/surface code 3/surface_code_3/pulse_metadata.json",
    "runs/surface code 3/surface_code_3/pulse_metadata.csv",
)
```

XLSX is also supported:

```python
export_json_table("pulse_metadata.json", "pulse_metadata.xlsx")
```

(`.xlsx` requires `openpyxl`)
