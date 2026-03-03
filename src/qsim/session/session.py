"""High-level session API for artifact revisions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import importlib.metadata as ilm
import json

from qsim.session.manifest import SessionManifest
from qsim.session.store import ArtifactStore


class Session:
    """Versioned artifact session with manifest-based indexing.

    Example:
        ```python
        from qsim.session.session import Session

        s = Session.open("runs/session_a")
        rev = s.commit("circuit", {"schema_version": "1.0", "qasm": "OPENQASM 3;"})
        print(s.get(rev))
        ```
    """

    DEFAULT_DEP_PACKAGES = ["numpy", "h5py", "PyYAML", "qutip", "qiskit", "ezdxf"]

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.session_id = self.path.name
        self.store = ArtifactStore(self.path / "artifacts")
        self.manifest_path = self.path / "session_manifest.json"
        self.manifest = SessionManifest.load(self.manifest_path, self.session_id)

    @classmethod
    def open(cls, path: str | Path) -> "Session":
        """Open or initialize a session directory."""
        return cls(path)

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _gather_dependencies(packages: list[str] | None = None) -> dict[str, str]:
        deps: dict[str, str] = {}
        for name in packages or Session.DEFAULT_DEP_PACKAGES:
            try:
                deps[name] = ilm.version(name)
            except ilm.PackageNotFoundError:
                continue
        return deps

    @staticmethod
    def _dependency_fingerprint(deps: dict[str, str]) -> str:
        canonical = json.dumps(deps, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def commit(
        self,
        kind: str,
        payload: dict[str, Any] | Any,
        *,
        inputs: dict[str, str] | None = None,
        dependencies: dict[str, str] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Store an artifact revision and append metadata to session manifest."""
        if not isinstance(payload, dict):
            payload = asdict(payload)

        stamp = datetime.now(timezone.utc).isoformat()
        canonical = self._canonical_json(payload)
        payload_digest = self._sha256_bytes(canonical.encode("utf-8"))
        rev_id = payload_digest[:16]
        artifact_path = self.store.put_json(kind, rev_id, payload)
        file_size = artifact_path.stat().st_size

        deps = dependencies or self._gather_dependencies()
        dep_fp = self._dependency_fingerprint(deps)

        self.manifest.revisions.append(
            {
                "rev_id": rev_id,
                "kind": kind,
                "created_at": stamp,
                "artifact_relpath": str(artifact_path.relative_to(self.path)),
                "payload_sha256": payload_digest,
                "artifact_size": file_size,
                "inputs": inputs or {},
                "dependencies": deps,
                "dependency_fingerprint": dep_fp,
                "tags": tags or [],
            }
        )
        self.manifest.save(self.manifest_path)
        return rev_id

    def get(self, rev_id: str) -> Path:
        """Resolve artifact path by revision ID."""
        for item in self.manifest.revisions:
            if item["rev_id"] == rev_id:
                return self.path / item["artifact_relpath"]
        raise KeyError(f"Unknown rev_id: {rev_id}")
