# 开发进度

本页按当前 `src/qsim` 实现状态整理，不再保留旧的笼统差距清单。

## 已经具备

### workflow 主线

- 4 文件配置装配：task / solver / device / pulse
- CLI 入口：`qsim run-task`
- Python 入口：`run_task`、`run_task_files`
- target 驱动执行计划
- 结构化产物落盘与 manifest
- session 自动提交

### 电路与编译

- OpenQASM 导入
- 电路标准化
- 编译、lowering、模型构建
- PulseIR 与 executable model 导出

### 求解与分析

- QuTiP 引擎
- Julia 相关引擎接口与配置入口
- sensitivity report
- `error_budget_v2`
- Pauli+ / component ablation
- cross-engine compare

### QEC

- prior 构建
- decoder
- decoder eval
- resume / retry / batch manifest

### 可视化与数据导出

- pulse timing 图
- trace/report 图
- DXF 导出
- JSON -> CSV/XLSX 表格导出

## 当前仍需注意

- `run_workflow` 仍出现在历史生成文件 `src/qsim.egg-info/PKG-INFO` 中，但不是当前源码入口
- 文档里旧的 `hardware_config` 命名已经过时，当前外部接口应统一使用 `device_config`
- Julia 求解路径在代码中已有接口和模板，但实际可用性仍取决于本机 Julia 环境
- 在线实时 QEC 反馈控制目前还没有实现

## 推荐后续补齐方向

1. 清理历史文档与打包产物中的旧入口命名
2. 给 `device` 和 `pulse` 模板补更完整的示例
3. 为 `solver.run`、`device`、`pulse` 字段补字段级 API 文档
4. 明确 Julia 后端的安装与验证流程
