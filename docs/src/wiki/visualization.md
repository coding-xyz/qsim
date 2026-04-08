# 可视化

`qsim` 当前的可视化主要围绕三类对象展开：

- `PulseIR`
- `trajectory`
- 分析报告

## workflow 自动导出

当 `task.output.export_plots` 为 `true` 时，常见图像产物包括：

- `pulse_timing.png`
- `trajectory.png`
- `report.png`

当 `task.output.export_dxf` 为 `true` 且安装了 `ezdxf` 时，还可以导出：

- `timing_diagram.dxf`

## 调试建议

- 看 `pulse` 配置是否生效：优先检查 `pulse_timing.png`
- 看数值演化是否合理：再看 `trajectory.png`
- 看分析阶段产出：最后看 `report.png`

