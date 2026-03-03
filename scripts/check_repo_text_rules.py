from __future__ import annotations

import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".qasm",
    ".stim",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".ipynb",
}


def _is_docs_site_path(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    return len(parts) >= 2 and parts[0] == "docs" and parts[1] == "site"


def _should_check_utf8(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def main(argv: list[str]) -> int:
    errors: list[str] = []
    for raw_name in argv[1:]:
        path = Path(raw_name)
        if _is_docs_site_path(path):
            errors.append(
                f"{path}: do not commit generated docs/site output; update docs/src or the source files instead."
            )
            continue
        if not _should_check_utf8(path):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: file is not valid UTF-8.")
        except OSError as exc:
            errors.append(f"{path}: unable to read file: {exc}")

    if errors:
        for item in errors:
            print(item, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
