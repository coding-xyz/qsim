"""Low-level artifact store helpers."""

from __future__ import annotations

from pathlib import Path
import json


class ArtifactStore:
    """Filesystem-backed JSON artifact store keyed by kind/revision."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(self, kind: str, rev_id: str, payload: dict) -> Path:
        """Write one JSON artifact and return its full path."""
        out = self.root / kind / f"{rev_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    def get_json(self, kind: str, rev_id: str) -> dict:
        """Load one JSON artifact by kind/revision."""
        src = self.root / kind / f"{rev_id}.json"
        if not src.exists():
            raise FileNotFoundError(src)
        return json.loads(src.read_text(encoding="utf-8"))
