import json
import shutil
import uuid
from pathlib import Path

import pytest

from qsim.workflow.engines import canonical_engine_name, select_engine
from qsim.workflow.task_io import load_solver_config_file


def test_engine_selection_rejects_legacy_aliases():
    with pytest.raises(ValueError, match="Unknown engine"):
        select_engine("quantumoptics")
    with pytest.raises(ValueError, match="Unknown engine"):
        select_engine("quantumtoolbox")
    with pytest.raises(ValueError, match="Unknown engine"):
        canonical_engine_name("quantumoptics")
    with pytest.raises(ValueError, match="Unknown engine"):
        canonical_engine_name("quantumtoolbox")


def test_load_solver_config_rejects_legacy_engine_aliases():
    solver_cfg = {
        "schema_version": "1.0",
        "backend": {"level": "qubit", "analysis_pipeline": "default", "truncation": {}},
        "run": {"engine": "quantumoptics", "solver_mode": "me", "julia_bin": "julia"},
    }
    temp_dir = Path("runs") / f"pytest_engine_sel_{uuid.uuid4().hex[:8]}"
    path = temp_dir / "legacy_solver.json"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(solver_cfg), encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported solver.run.engine"):
            load_solver_config_file(path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_solver_config_accepts_canonical_julia_engine_names():
    solver_cfg = {
        "schema_version": "1.0",
        "backend": {"level": "qubit", "analysis_pipeline": "default", "truncation": {}},
        "run": {"engine": "qoptics", "solver_mode": "me", "julia_bin": "julia"},
    }
    temp_dir = Path("runs") / f"pytest_engine_sel_{uuid.uuid4().hex[:8]}"
    path = temp_dir / "solver.json"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(solver_cfg), encoding="utf-8")
        solver = load_solver_config_file(path)
        assert solver.run.engine == "qoptics"
        assert solver.run.julia_bin is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
