from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import mkdocs_gen_files


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "qsim"


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT / "src").with_suffix("")
    return ".".join(rel.parts)


def _is_public_module(path: Path) -> bool:
    if path.name == "__init__.py":
        return False
    return not any(part.startswith("_") for part in path.relative_to(ROOT / "src").parts)


modules = sorted(p for p in SRC.rglob("*.py") if _is_public_module(p))
grouped: dict[str, list[str]] = defaultdict(list)
for py_path in modules:
    module = _module_name(py_path)
    parts = module.split(".")
    group = parts[1] if len(parts) > 2 else "core"
    grouped[group].append(module)

# 1) API 总览页：只放分类导航
index_lines = [
    "# API 参考",
    "",
    "本页与子页由 `docs/scripts/gen_ref_pages.py` 自动生成，内容来自 `src/qsim` 的 docstring。",
    "",
    "## 按目录分类",
    "",
]
for group in sorted(grouped):
    index_lines.append(f"- [{group}](./{group}.md)")

with mkdocs_gen_files.open("api/index.md", "w") as fd:
    fd.write("\n".join(index_lines) + "\n")

# 2) 每个 src 一级目录生成一个分页
for group in sorted(grouped):
    lines = [
        f"# API - {group}",
        "",
        f"`src/qsim/{group}` 下模块：",
        "",
    ]
    for module in sorted(grouped[group]):
        lines.append(f"## `{module}`")
        lines.append("")
        lines.append(f"::: {module}")
        lines.append("")
    with mkdocs_gen_files.open(f"api/{group}.md", "w") as fd:
        fd.write("\n".join(lines) + "\n")
