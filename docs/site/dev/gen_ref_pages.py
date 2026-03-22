"""Generate grouped API reference pages from ``src/qsim`` docstrings."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import mkdocs_gen_files


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "qsim"

GROUP_DESCRIPTIONS = {
    "analysis": "观测量、敏感度、误差预算和分析注册器。",
    "backend": "编译、lowering、模型构建与 backend 配置。",
    "circuit": "OpenQASM 导入、导出与电路标准化。",
    "common": "通用 schema、单位字段和底层数据结构。",
    "engines": "QuTiP、Julia 相关引擎与 QEC 分析引擎接口。",
    "pulse": "门到脉冲映射、PulseIR 生成与可视化工具。",
    "qec": "prior、decoder、decoder eval 与逻辑误差汇总。",
    "session": "结果 revision、artifact store 与 session manifest。",
    "ui": "CLI、notebook 辅助函数和结果摘要接口。",
    "workflow": "配置加载、执行计划、主 pipeline 与结果提交。",
}

GROUP_ENTRYPOINTS = {
    "analysis": ["qsim.analysis.AnalysisRegistry", "qsim.analysis.AnalysisRunner"],
    "backend": ["qsim.backend.CompilePipeline", "qsim.backend.DefaultLowering", "qsim.backend.load_backend_config"],
    "circuit": ["qsim.circuit.CircuitAdapter"],
    "engines": [
        "qsim.engines.QuTiPEngine",
        "qsim.engines.QOpticsEngine",
        "qsim.engines.QToolboxEngine",
        "qsim.engines.StimQECAnalysisEngine",
        "qsim.engines.CirqQECAnalysisEngine",
    ],
    "pulse": ["qsim.pulse.PulseCompiler", "qsim.pulse.build_gate_mapping_catalog"],
    "qec": ["qsim.qec.get_decoder", "qsim.qec.build_prior_and_report", "qsim.qec.summarize_logical_error"],
    "session": ["qsim.session.Session"],
    "ui": ["qsim.ui.plot_default"],
    "workflow": [
        "qsim.workflow.run_task",
        "qsim.workflow.run_task_files",
        "qsim.workflow.load_task_config_file",
        "qsim.workflow.load_solver_config_file",
        "qsim.workflow.load_device_config_file",
        "qsim.workflow.load_pulse_config_file",
    ],
}


def _module_name(path: Path) -> str:
    """Return the import path for a source file under ``src/``."""
    rel = path.relative_to(ROOT / "src")
    if path.name == "__init__.py":
        rel = rel.parent
    else:
        rel = rel.with_suffix("")
    return ".".join(rel.parts)


def _is_public_module(path: Path) -> bool:
    """Skip private modules when generating API pages."""
    rel_parts = path.relative_to(ROOT / "src").parts
    if path.name == "__init__.py":
        return not any(part.startswith("_") for part in rel_parts[:-1])
    return not any(part.startswith("_") for part in rel_parts)


modules = sorted(p for p in SRC.rglob("*.py") if _is_public_module(p))
grouped: dict[str, list[str]] = defaultdict(list)
for py_path in modules:
    module = _module_name(py_path)
    if module == "qsim":
        continue
    parts = module.split(".")
    group = parts[1] if len(parts) > 1 else "core"
    grouped[group].append(module)

index_lines = [
    "# API 参考",
    "",
    "本目录由 `src/qsim` 中的源码 docstring 自动生成，并按模块分组组织。",
    "",
    "## 如何阅读",
    "",
    "- 如果你只想知道常用调用入口，请先看每个分组页面顶部的“常用入口”。",
    "- 如果你想查具体函数、类或数据结构，请继续阅读该分组下的自动生成模块条目。",
    "- `docs/wiki` 中的说明书页面负责讲“怎么用”，本目录负责讲“接口是什么”。",
    "",
    "## 模块分组",
    "",
]
for group in sorted(grouped):
    desc = GROUP_DESCRIPTIONS.get(group, "该分组的详细接口。")
    index_lines.append(f"- [{group}](./{group}.md)：{desc}")

with mkdocs_gen_files.open("api/index.md", "w") as fd:
    fd.write("\n".join(index_lines) + "\n")

for group in sorted(grouped):
    package_module = f"qsim.{group}"
    lines = [
        f"# {group}",
        "",
        GROUP_DESCRIPTIONS.get(group, f"`src/qsim/{group}` 下的公开接口。"),
        "",
        "## 常用入口",
        "",
    ]
    entries = GROUP_ENTRYPOINTS.get(group, [])
    if entries:
        for entry in entries:
            lines.append(f"- `{entry}`")
    else:
        lines.append("- 本分组当前没有额外整理的常用入口，请直接查看下方模块列表。")

    lines.extend(
        [
            "",
            "## 包级导出",
            "",
            f"::: {package_module}",
            "",
            "## 模块列表",
            "",
        ]
    )

    for module in sorted(grouped[group]):
        if module == package_module:
            continue
        lines.append(f"## `{module}`")
        lines.append("")
        lines.append(f"::: {module}")
        lines.append("")
    with mkdocs_gen_files.open(f"api/{group}.md", "w") as fd:
        fd.write("\n".join(lines) + "\n")
