import json
from pathlib import Path

from qsim.session.session import Session


def test_session_commit_records_hashes(tmp_path: Path):
    s = Session.open(tmp_path / "s1")
    rev = s.commit("circuit", {"schema_version": "1.0", "value": 1}, inputs={"src": "unit"})
    p = s.get(rev)
    assert p.exists()

    manifest = json.loads((tmp_path / "s1" / "session_manifest.json").read_text(encoding="utf-8"))
    entry = manifest["revisions"][0]
    assert entry["rev_id"] == rev
    assert "payload_sha256" in entry
    assert "dependency_fingerprint" in entry
    assert entry["inputs"]["src"] == "unit"