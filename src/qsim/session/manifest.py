"""Session manifest schema helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass
class SessionManifest:
    """In-memory manifest for session revision metadata."""

    session_id: str
    schema_version: str = "1.0"
    revisions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path, session_id: str) -> "SessionManifest":
        """Load manifest from JSON file or create an empty one."""
        p = Path(path)
        if not p.exists():
            return cls(session_id=session_id)
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            session_id=raw.get("session_id", session_id),
            schema_version=raw.get("schema_version", "1.0"),
            revisions=raw.get("revisions", []),
        )

    def save(self, path: str | Path) -> None:
        """Persist manifest to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "revisions": self.revisions,
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
