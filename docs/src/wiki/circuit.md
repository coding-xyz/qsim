# 电路层

## 已实现

- 导入：OpenQASM 3 文本、Qiskit 电路
- 导出：OpenQASM 3、Qiskit 电路
- 中间表示：`CircuitIR`、`CircuitGate`
- 编译归一化：`CompilePipeline` + `NormalizePass`

## 当前支持门

- 单比特：`x`、`sx`、`h`、`z`、`rz`
- 双比特：`cx`、`cz`
- 测量：`measure`

## 限制

- 仅支持 OpenQASM 3 的最小可用子集
- 参数化门若无 lowering 映射，不会转成特定物理脉冲
- 当前调度是串行 cursor 推进模型
