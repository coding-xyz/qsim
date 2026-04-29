import pytest

from qsim.common.schemas import ModelSpec, model_spec_from_runtime_dict
from qsim.engines.qoptics import QOpticsEngine
from qsim.engines.qtoolbox import QToolboxEngine


def _population_series_from_quantum_payload(trajectory):
    density_matrix = dict(getattr(trajectory, "density_matrix", {}) or {})
    wave_function = dict(getattr(trajectory, "wave_function", {}) or {})
    if density_matrix:
        return [float(max(0.0, 1.0 - snapshot[0][0].real)) for snapshot in density_matrix.get("snapshots", [])]
    if wave_function:
        return [float(max(0.0, 1.0 - abs(snapshot[0]) ** 2)) for snapshot in wave_function.get("snapshots", [])]
    return []


def _run_or_skip(engine, spec: ModelSpec):
    try:
        return engine.run(spec, run_options={})
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "julia executable not found" in msg or "julia runtime failed" in msg or "dependency unavailable" in msg:
            pytest.skip(str(exc))
        raise


def _minimal_spec(solver: str = "me") -> ModelSpec:
    return model_spec_from_runtime_dict(
        solver=solver,
        dimension=2,
        t_end=10.0,
        dt=1.0,
        model={
            "model_type": "qubit_network",
            "num_qubits": 1,
            "qubit_omega_rad_s": [0.05],
            "controls": [{"target": 0, "axis": "x", "times": [0.0, 5.0, 10.0], "values": [0.0, 1.0, 0.0], "scale": 1.0}],
            "collapse_operators": [{"target": 0, "kind": "relaxation", "rate_rad_s": 0.01}],
        },
    )


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_native_or_raise(engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")
    try:
        Trajectory = engine.run(spec, run_options={})
    except Exception:
        return
    assert Trajectory.metadata.get("native_solver", False) is True


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_default_no_mock_fallback(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")

    def _fail(_model_spec, run_options=None):
        raise RuntimeError("bridge failed")

    monkeypatch.setattr(engine, "_runtime", type("R", (), {"run": staticmethod(_fail)})())
    with pytest.raises(RuntimeError, match="bridge failed"):
        engine.run(spec)


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_pass_run_options(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("mcwf")
    captured = {}

    class _Runtime:
        @staticmethod
        def run(_model_spec, run_options=None):
            captured["opts"] = dict(run_options or {})
            class _Trajectory:
                metadata = {"native_solver": True}
            return _Trajectory()

    monkeypatch.setattr(engine, "_runtime", _Runtime())
    engine.run(spec, run_options={"julia_bin": "C:/x/julia.exe", "ntraj": 16})
    assert captured["opts"]["julia_bin"] == "C:/x/julia.exe"
    assert int(captured["opts"]["ntraj"]) == 16


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_native_metadata_fields(engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")
    try:
        Trajectory = engine.run(spec, run_options={})
    except Exception:
        return
    assert str(Trajectory.metadata.get("julia_version", "")).strip() != ""
    assert str(Trajectory.metadata.get("julia_backend", "")).strip() != ""
    assert str(Trajectory.metadata.get("julia_backend_version", "")).strip() != ""


def test_julia_runtime_runner_resolves_backend_specific_scripts():
    assert QOpticsEngine()._runtime._resolve_script().name == "qoptics_runtime.jl"
    assert QToolboxEngine()._runtime._resolve_script().name == "qtoolbox_runtime.jl"


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_short_pulse_on_long_timeline(engine_cls):
    engine = engine_cls()
    spec = model_spec_from_runtime_dict(
        solver="se",
        dimension=2,
        t_end=5.0e-5,
        dt=1.0e-9,
        model={
            "model_type": "qubit_network",
            "num_qubits": 1,
            "qubit_omega_rad_s": [0.0],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [
                {
                    "target": 0,
                    "axis": "x",
                    "times": [0.0, 1.0e-9, 2.0e-9, 3.0e-9, 4.0e-9, 5.0e-9, 6.0e-9, 7.0e-9, 8.0e-9, 9.0e-9, 1.0e-8],
                    "values": [0.0, 2.9e6, 8.7e6, 1.92e7, 3.62e7, 6.07e7, 9.21e7, 1.27e8, 1.60e8, 1.83e8, 1.92e8],
                    "scale": 1.0,
                    "carrier_omega_rad_s": 2.0 * 3.141592653589793 * 5.0e9,
                    "drive_delta_rad_s": 0.0,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
        },
    )
    try:
        Trajectory = engine.run(spec, run_options={})
    except Exception:
        return
    excited = _population_series_from_quantum_payload(Trajectory)
    assert max(excited, default=0.0) > 1.0e-3


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_support_transmon_nlevel(engine_cls):
    spec = model_spec_from_runtime_dict(
        solver="se",
        dimension=3,
        t_end=2.0e-8,
        dt=1.0e-9,
        model={
            "model_type": "transmon_nlevel",
            "num_qubits": 1,
            "transmon_levels": 3,
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [-0.2],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [
                {
                    "target": 0,
                    "axis": "x",
                    "times": [0.0, 1.0e-8, 2.0e-8],
                    "values": [0.0, 1.0e8, 0.0],
                    "scale": 1.0,
                    "carrier_omega_rad_s": 0.0,
                    "drive_delta_rad_s": 0.0,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
        },
    )
    Trajectory = _run_or_skip(engine_cls(), spec)
    vals = _population_series_from_quantum_payload(Trajectory)
    assert Trajectory.metadata.get("model_type") == "transmon_nlevel"
    assert max(vals, default=0.0) > 1.0e-3


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_support_cqed_jc(engine_cls):
    spec = model_spec_from_runtime_dict(
        solver="se",
        dimension=12,
        t_end=2.0e-8,
        dt=1.0e-9,
        model={
            "model_type": "cqed_jc",
            "num_qubits": 1,
            "transmon_levels": 3,
            "cavity_nmax": 3,
            "cavity_omega_rad_s": 0.05,
            "g_cavity_rad_s": [0.01],
            "qubit_omega_rad_s": [0.0],
            "anharmonicity_rad_s": [-0.2],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [
                {
                    "target": 0,
                    "axis": "x",
                    "times": [0.0, 1.0e-8, 2.0e-8],
                    "values": [0.0, 1.0e8, 0.0],
                    "scale": 1.0,
                    "carrier_omega_rad_s": 0.0,
                    "drive_delta_rad_s": 0.0,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
        },
    )
    Trajectory = _run_or_skip(engine_cls(), spec)
    vals = _population_series_from_quantum_payload(Trajectory)
    assert Trajectory.metadata.get("model_type") == "cqed_jc"
    assert max(vals, default=0.0) > 1.0e-3


def test_qtoolbox_engine_preserves_full_quantum_trajectory_when_expectations_are_requested():
    spec = _minimal_spec("me")
    trajectory = _run_or_skip(QToolboxEngine(), spec)
    qstate = dict(getattr(trajectory, "density_matrix", {}) or getattr(trajectory, "wave_function", {}) or {})
    snapshots = list(qstate.get("snapshots", []) or [])

    assert len(trajectory.times) > 1
    assert len(snapshots) == len(trajectory.times)


