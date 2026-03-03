"""Generate grouped API reference pages from ``src/qsim`` docstrings."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import mkdocs_gen_files


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "qsim"


def _module_name(path: Path) -> str:
    """Return the import path for a source file under ``src/``."""
    rel = path.relative_to(ROOT / "src").with_suffix("")
    return ".".join(rel.parts)


def _is_public_module(path: Path) -> bool:
    """Skip package markers and private modules when generating API pages."""
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

index_lines = [
    "# API Reference",
    "",
    "These pages are generated from `src/qsim` docstrings by `docs/src/scripts/gen_ref_pages.py`.",
    "",
    "## Module Groups",
    "",
]
for group in sorted(grouped):
    index_lines.append(f"- [{group}](./{group}.md)")

with mkdocs_gen_files.open("api/index.md", "w") as fd:
    fd.write("\n".join(index_lines) + "\n")

for group in sorted(grouped):
    lines = [
        f"# API - {group}",
        "",
        f"Modules under `src/qsim/{group}`:",
        "",
    ]
    for module in sorted(grouped[group]):
        lines.append(f"## `{module}`")
        lines.append("")
        lines.append(f"::: {module}")
        lines.append("")
    with mkdocs_gen_files.open(f"api/{group}.md", "w") as fd:
        fd.write("\n".join(lines) + "\n")
