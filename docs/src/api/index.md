# API 参考

本目录由源码 docstring 驱动，重点关注：

- `analysis`：观测量、误差预算、敏感度分析
- `schemas`：配置、IR、ModelSpec 和结果 dataclass
- `backend`：配置标准化、pulse/model lowering 和 ModelSpec 构建
- `workflow`：配置加载、执行计划和持久化
- `engines`：QuTiP、Julia 和 QEC engine 接口
- `qec`：prior 构建、解码器、批评估（并行/重试/续跑）
- `ui`：notebook workflow 与结果汇总辅助接口

推荐入口：

- [analysis](analysis.md)
- [schemas](schemas.md)
- [backend](backend.md)
- [workflow](workflow.md)
- [engines](engines.md)
- [qec](qec.md)
- [ui](ui.md)
